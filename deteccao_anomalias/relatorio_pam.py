"""Relatório PDF de urgência de PAM e envio pelo SMTP configurado no .env."""
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import math
import os
from pathlib import Path
import smtplib
import sys
from uuid import uuid4
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from analise_audio.configuracao import carregar_ambiente, criar_contexto_smtp, obrigatoria


def gerar_pdf(evento, destino):
    # Mesmo padrão ReportLab usado em analise_video/gerar_relatorio.py.
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    estilos = getSampleStyleSheet()
    linhas = [
        ('Relatório de urgência de PAM', 'Title'),
        (f"Identificação do caso: {evento['caseid']}", 'Heading2'),
        (f"Gerado em: {datetime.now(timezone.utc).isoformat()}", 'BodyText'),
        (f"Motivo: {evento['motivo']}", 'BodyText'),
        (f"Início da urgência: {evento['inicio_urgencia_s']:g}s; "
         f"detecção: {evento['tempo_s']:g}s; duração: {evento['duracao_urgencia_s']:g}s.", 'BodyText'),
        (f"PAM na detecção: {evento['pam_mmhg']:g} mmHg.", 'BodyText'),
        (f"Limites configurados: abaixo de {evento['limite_baixo_mmhg']:g} mmHg "
         f"ou acima de {evento['limite_alto_mmhg']:g} mmHg.", 'BodyText'),
        ('Simulação com limites configurados pelo usuário. A classificação não identifica a causa clínica. '
         'A PAM pode ter sido convertida para valor absoluto conforme a configuração do monitor.', 'BodyText'),
    ]
    conteudo = []
    for valor, estilo in linhas:
        conteudo.extend([Paragraph(escape(valor), estilos[estilo]), Spacer(1, 12)])
    destino.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(destino), pagesize=A4, rightMargin=48, leftMargin=48,
                      topMargin=40, bottomMargin=45).build(conteudo)


def enviar_email(evento, pdf):
    carregar_ambiente()
    host, usuario, senha = (obrigatoria(k) for k in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD'))
    porta = int(obrigatoria('SMTP_PORT'))
    seguranca = obrigatoria('SMTP_SECURITY').lower()
    timeout = float(os.getenv('SMTP_TIMEOUT', '30'))
    if seguranca not in {'ssl', 'starttls'}:
        raise ValueError('SMTP_SECURITY deve ser starttls ou ssl.')
    if not 1 <= porta <= 65535 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('SMTP_PORT ou SMTP_TIMEOUT inválido.')
    mensagem = EmailMessage()
    for cabecalho, chave in [('From', 'EMAIL_FROM'), ('To', 'EMAIL_TO')]:
        valor = obrigatoria(chave)
        if '\n' in valor or '\r' in valor or parseaddr(valor)[1] != valor or '@' not in valor:
            raise ValueError(f'{chave} deve conter um único endereço de e-mail.')
        mensagem[cabecalho] = valor
    mensagem['Subject'] = f"Alerta de PAM — caso {evento['caseid']}"
    mensagem.set_content(f"Caso: {evento['caseid']}\nMotivo: {evento['motivo']}\n"
                         f"Duração: {evento['duracao_urgencia_s']:g}s\nRelatório em anexo.")
    mensagem.add_attachment(pdf.read_bytes(), maintype='application', subtype='pdf', filename=pdf.name)
    contexto = criar_contexto_smtp()
    conexao = (smtplib.SMTP_SSL(host, porta, timeout=timeout, context=contexto)
               if seguranca == 'ssl' else smtplib.SMTP(host, porta, timeout=timeout))
    with conexao as smtp:
        smtp.ehlo()
        if seguranca == 'starttls':
            smtp.starttls(context=contexto)
            smtp.ehlo()
        smtp.login(usuario, senha)
        if smtp.send_message(mensagem):
            raise RuntimeError('O servidor recusou o destinatário.')


def notificar_medico(evento):
    destino = RAIZ / 'deteccao_anomalias' / 'outputs' / f"urgencia_caso_{evento['caseid']}_{uuid4().hex}.pdf"
    gerar_pdf(evento, destino)
    evento['relatorio_pdf'] = str(destino)
    enviar_email(evento, destino)
