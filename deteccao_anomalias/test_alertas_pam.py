"""Validação de urgências e e-mail sem acesso ao SMTP real."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from simular_monitor_pam import MotorAlertas, Referencias
import relatorio_pam


class AlertasTest(unittest.TestCase):
    def motor(self, notificador=None):
        return MotorAlertas(Referencias(40, 60, 100, 120), 1341, notificador or Mock())

    def test_limite_e_envio_unico_mesmo_em_novo_episodio(self):
        motor = self.motor()
        for t in range(11):
            motor.receber(t, 130)
        motor.notificador.assert_not_called()
        motor.receber(11, 130)
        motor.receber(12, 80)
        for t in range(13, 30):
            motor.receber(t, 30)
        motor.notificador.assert_called_once()
        self.assertEqual(motor.eventos[0]['duracao_urgencia_s'], 11)
        self.assertEqual(motor.eventos[0]['caseid'], 1341)

    def test_recuperacao_reinicia(self):
        motor = self.motor()
        for t in range(10):
            motor.receber(t, 130)
        motor.receber(10, 80)
        for t in range(11, 22):
            motor.receber(t, 130)
        motor.notificador.assert_not_called()
        motor.receber(22, 130)
        motor.notificador.assert_called_once()

    def test_ausencias_curtas_preservam_sem_disparar(self):
        motor = self.motor()
        for t in range(12):
            motor.receber(t, 130 if t % 2 == 0 else float('nan'))
        motor.notificador.assert_not_called()
        motor.receber(12, 130)
        motor.notificador.assert_called_once()

    def test_lacuna_longa_reinicia_com_ou_sem_nan(self):
        for com_nan in (True, False):
            motor = self.motor()
            for t in range(10):
                motor.receber(t, 130)
            if com_nan:
                motor.receber(15, float('nan'))
            for t in range(16, 27):
                motor.receber(t, 130)
            motor.notificador.assert_not_called()
            motor.receber(27, 130)
            motor.notificador.assert_called_once()

    def test_troca_de_urgencia_continua(self):
        motor = self.motor()
        for t in range(12):
            motor.receber(t, 30 if t < 6 else 130)
        motor.notificador.assert_called_once()

    def test_trecho_caso_1341(self):
        motor = self.motor()
        valores = [65, 116, 116, 142, 142, 145, 145, 180, 180, 195]
        for t, pam in zip(range(516, 535, 2), valores):
            motor.receber(t, pam)
            motor.receber(t + 1, float('nan'))
        motor.notificador.assert_called_once()
        self.assertEqual(motor.eventos[0]['inicio_urgencia_s'], 522)
        self.assertEqual(motor.eventos[0]['tempo_s'], 534)

    def test_falha_nao_repete(self):
        motor = self.motor(Mock(side_effect=RuntimeError('falha SMTP')))
        for t in range(30):
            motor.receber(t, 30)
        motor.notificador.assert_called_once()
        self.assertEqual(motor.eventos[0]['envio'], 'falha')

    def test_pdf_e_anexo_smtp(self):
        motor = self.motor()
        for t in range(12):
            motor.receber(t, 130)
        evento = motor.eventos[0]
        env = dict(SMTP_HOST='smtp.example.com', SMTP_PORT='587', SMTP_SECURITY='starttls',
                   SMTP_USERNAME='teste', SMTP_PASSWORD='teste', EMAIL_FROM='a@example.com',
                   EMAIL_TO='b@example.com', SMTP_TIMEOUT='10')
        with TemporaryDirectory() as pasta:
            pdf = Path(pasta) / 'relatorio.pdf'
            relatorio_pam.gerar_pdf(evento, pdf)
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
            for seguranca in ('starttls', 'ssl'):
                env['SMTP_SECURITY'] = seguranca
                with patch.dict(os.environ, env), patch.object(relatorio_pam, 'carregar_ambiente'), \
                     patch.object(relatorio_pam.smtplib, 'SMTP') as smtp, \
                     patch.object(relatorio_pam.smtplib, 'SMTP_SSL') as smtp_ssl:
                    fabrica = smtp if seguranca == 'starttls' else smtp_ssl
                    conexao = fabrica.return_value.__enter__.return_value
                    conexao.send_message.return_value = {}
                    relatorio_pam.enviar_email(evento, pdf)
                    mensagem = conexao.send_message.call_args.args[0]
                    self.assertIn('1341', mensagem['Subject'])
                    self.assertIn(evento['motivo'], mensagem.get_body().get_content())
                    self.assertEqual(list(mensagem.iter_attachments())[0].get_payload(decode=True), pdf.read_bytes())
                    conexao.send_message.assert_called_once()
                    if seguranca == 'starttls':
                        conexao.starttls.assert_called_once()
                    else:
                        smtp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
