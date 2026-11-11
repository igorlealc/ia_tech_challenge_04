"""Análise de sentimento da transcrição com Azure Text Analytics."""

from urllib.parse import urlparse

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError

from configuracao import obrigatoria


def criar_cliente():
    endpoint = obrigatoria('TEXT_ANALYTICS_ENDPOINT')
    url = urlparse(endpoint)
    if url.scheme != 'https' or not url.netloc or url.username or url.password:
        raise ValueError('TEXT_ANALYTICS_ENDPOINT deve ser o endpoint HTTPS do recurso Azure Language.')
    return TextAnalyticsClient(
        endpoint=endpoint, credential=AzureKeyCredential(obrigatoria('TEXT_ANALYTICS_KEY')),
        connection_timeout=15, read_timeout=60,
    )


def dividir_texto(texto, limite=4000):
    """Divide texto abaixo do limite síncrono, preferindo fronteiras de palavras."""
    partes = []
    restante = texto.strip()
    while len(restante) > limite:
        corte = restante.rfind(' ', 0, limite + 1)
        if corte < limite // 2:
            corte = limite
        partes.append(restante[:corte])
        restante = restante[corte:].strip()
    if restante:
        partes.append(restante)
    return partes


def analisar_sentimento(cliente, textos, idioma):
    partes = dividir_texto(' '.join(textos))
    analise = {'idioma': idioma, 'trechos': [], 'status': 'sem_texto' if not partes else 'ok'}
    # A API síncrona aceita até 10 documentos por chamada.
    for inicio in range(0, len(partes), 10):
        lote = partes[inicio:inicio + 10]
        documentos = [
            {'id': str(inicio + i + 1), 'language': idioma, 'text': texto}
            for i, texto in enumerate(lote)
        ]
        try:
            respostas = cliente.analyze_sentiment(documentos, disable_service_logs=True)
        except AzureError as erro:
            # Preserva a transcrição; não apresenta uma falha como sentimento neutro.
            analise['status'] = 'erro'
            for documento in documentos:
                analise['trechos'].append({
                    'parte': int(documento['id']), 'caracteres': len(documento['text']),
                    'erro': type(erro).__name__,
                })
            continue
        por_id = {str(resposta.id): resposta for resposta in respostas}
        for documento in documentos:
            resposta = por_id.get(documento['id'])
            trecho = {'parte': int(documento['id']), 'caracteres': len(documento['text'])}
            if resposta is None or resposta.is_error:
                analise['status'] = 'erro'
                trecho['erro'] = 'RespostaAusente' if resposta is None else str(resposta.error.code)
            else:
                trecho.update({
                    'sentimento': resposta.sentiment,
                    'positivo': float(resposta.confidence_scores.positive),
                    'neutro': float(resposta.confidence_scores.neutral),
                    'negativo': float(resposta.confidence_scores.negative),
                })
            analise['trechos'].append(trecho)
    return analise
