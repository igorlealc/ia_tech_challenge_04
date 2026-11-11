"""Configuração compartilhada dos scripts de áudio."""

import os
import ssl
from pathlib import Path

from dotenv import load_dotenv
import certifi


ENV_PADRAO = Path(__file__).resolve().parents[1] / '.env'


def criar_contexto_smtp():
    """Complementa certificados do sistema com as autoridades do certifi."""
    contexto = ssl.create_default_context()
    contexto.load_verify_locations(cafile=certifi.where())
    return contexto


def carregar_ambiente(caminho=None):
    arquivo = Path(caminho).expanduser().resolve() if caminho else ENV_PADRAO
    if caminho and not arquivo.is_file():
        raise FileNotFoundError(f'Arquivo de configuração não encontrado: {arquivo}')
    load_dotenv(arquivo, override=False)
    return arquivo


def obrigatoria(nome):
    valor = os.getenv(nome, '').strip()
    if not valor:
        raise ValueError(f'Preencha {nome} no arquivo .env.')
    return valor
