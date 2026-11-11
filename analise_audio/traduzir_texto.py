"""Tradução de texto já transcrito usando Azure Translator."""

import os
from urllib.parse import urlparse

import requests

from analisar_sentimento import dividir_texto
from configuracao import obrigatoria


def traduzir_textos(textos, idioma):
    origem = idioma.lower().split('-')[0]
    if origem == 'pt' or not any(texto.strip() for texto in textos):
        return list(textos)
    endpoint = os.getenv('TRANSLATOR_ENDPOINT', '').strip() or 'https://api.cognitive.microsofttranslator.com'
    url = urlparse(endpoint)
    if url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError('TRANSLATOR_ENDPOINT deve ser a URL base HTTPS do Azure Translator.')
    headers = {'Ocp-Apim-Subscription-Key': obrigatoria('TRANSLATOR_KEY')}
    regiao = os.getenv('TRANSLATOR_REGION', '').strip()
    if regiao:
        headers['Ocp-Apim-Subscription-Region'] = regiao
    partes = [parte for texto in textos for parte in dividir_texto(texto)]
    traduzidos = []
    with requests.Session() as sessao:
        # No máximo 20 mil caracteres Python por requisição, para um único destino.
        for inicio in range(0, len(partes), 5):
            lote = partes[inicio:inicio + 5]
            try:
                resposta = sessao.post(
                    endpoint.rstrip('/') + '/translate',
                    params={'api-version': '3.0', 'from': origem, 'to': 'pt'},
                    headers=headers, json=[{'text': texto} for texto in lote],
                    timeout=(15, 60), allow_redirects=False,
                )
                if not 200 <= resposta.status_code < 300:
                    raise RuntimeError(f'Azure Translator retornou HTTP {resposta.status_code}. Confira o recurso e suas credenciais.')
                resultados = resposta.json()
            except requests.RequestException as erro:
                raise RuntimeError(f'Falha de conexão com Azure Translator ({type(erro).__name__}).') from None
            except ValueError:
                raise RuntimeError('Azure Translator retornou uma resposta inválida.') from None
            if not isinstance(resultados, list) or len(resultados) != len(lote):
                raise RuntimeError('Azure Translator retornou quantidade inesperada de traduções.')
            for item in resultados:
                traducoes = item.get('translations', []) if isinstance(item, dict) else []
                texto = next((t.get('text') for t in traducoes if t.get('to') == 'pt'), None)
                if not isinstance(texto, str) or not texto.strip():
                    raise RuntimeError('Azure Translator não retornou a tradução para português.')
                traduzidos.append(texto)
    return traduzidos
