"""Envia uma mensagem de teste usando a configuração SMTP do .env."""

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
import math
import os
import smtplib
import ssl
import sys

from configuracao import carregar_ambiente, criar_contexto_smtp, obrigatoria


def endereco(nome):
    valor = obrigatoria(nome)
    if '\r' in valor or '\n' in valor or parseaddr(valor)[1] != valor or '@' not in valor:
        raise ValueError(f'{nome} deve conter um único endereço de e-mail sem nome de exibição.')
    return valor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', help='Caminho do .env (padrão: trabalho4/.env).')
    args = parser.parse_args()
    carregar_ambiente(args.env)

    host = obrigatoria('SMTP_HOST')
    porta = int(obrigatoria('SMTP_PORT'))
    seguranca = obrigatoria('SMTP_SECURITY').lower()
    usuario = obrigatoria('SMTP_USERNAME')
    obrigatoria('SMTP_PASSWORD')
    timeout = float(os.getenv('SMTP_TIMEOUT', '30'))
    if seguranca not in {'starttls', 'ssl'}:
        raise ValueError('SMTP_SECURITY deve ser starttls ou ssl.')
    if not 1 <= porta <= 65535 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('SMTP_PORT ou SMTP_TIMEOUT inválido.')

    mensagem = EmailMessage()
    mensagem['From'] = endereco('EMAIL_FROM')
    mensagem['To'] = endereco('EMAIL_TO')
    mensagem['Subject'] = 'Teste de envio de e-mail — Trabalho 4'
    mensagem['Date'] = format_datetime(datetime.now(timezone.utc))
    mensagem['Message-ID'] = make_msgid()
    mensagem.set_content(
        'Esta é uma mensagem de teste da configuração de e-mail do Trabalho 4.\n\n'
        'Se você recebeu esta mensagem, o envio SMTP chegou a este endereço.\n'
        'Nenhuma análise de áudio foi executada e não há anexos.\n'
    )

    contexto = criar_contexto_smtp()
    conexao = (
        smtplib.SMTP_SSL(host, porta, timeout=timeout, context=contexto)
        if seguranca == 'ssl' else smtplib.SMTP(host, porta, timeout=timeout)
    )
    with conexao as smtp:
        smtp.ehlo()
        if seguranca == 'starttls':
            smtp.starttls(context=contexto)
            smtp.ehlo()
        smtp.login(usuario, os.environ['SMTP_PASSWORD'])
        if smtp.send_message(mensagem):
            raise RuntimeError('O servidor recusou o destinatário.')
    print(f'Mensagem de teste aceita pelo servidor SMTP para {mensagem["To"]}.')
    print('Confira a caixa de entrada e a pasta de spam para confirmar o recebimento.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ssl.SSLCertVerificationError:
        print('Não foi possível validar o certificado SMTP. Atualize certifi com '
              'python -m pip install --upgrade certifi. Se persistir, confira a cadeia '
              'de certificados da conexão/rede.', file=sys.stderr)
        sys.exit(1)
    except smtplib.SMTPAuthenticationError:
        print('Falha de autenticação. Confira SMTP_USERNAME e SMTP_PASSWORD no .env.', file=sys.stderr)
        sys.exit(1)
    except (ValueError, FileNotFoundError) as erro:
        print(f'Configuração inválida: {erro}', file=sys.stderr)
        sys.exit(1)
    except (OSError, smtplib.SMTPException, RuntimeError) as erro:
        print(f'Falha no envio ({type(erro).__name__}). Confira servidor, porta, TLS e destinatário.', file=sys.stderr)
        sys.exit(1)
