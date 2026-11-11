"""Transcrição, classificação acústica, PDF e alerta SMTP por arquivo ou microfone."""

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import json
import math
import os
from pathlib import Path
import smtplib
import subprocess
import sys
from tempfile import TemporaryDirectory
import warnings
from xml.sax.saxutils import escape

import joblib
import numpy as np
import opensmile
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from scipy.signal import resample_poly
from sklearn.exceptions import InconsistentVersionWarning
import soundfile as sf

from configuracao import carregar_ambiente, criar_contexto_smtp, obrigatoria
from extrair_atributos_audio import extrair_atributos
from transcrever_audio import criar_configuracao, transcrever
from traduzir_texto import traduzir_textos
from analisar_sentimento import criar_cliente, analisar_sentimento
from azure.core.exceptions import AzureError


RAIZ = Path(__file__).resolve().parent
TARGETS = ('cansaco', 'falta_ar', 'doenca_respiratoria')
NOMES = {'cansaco': 'Cansaço', 'falta_ar': 'Falta de ar', 'doenca_respiratoria': 'Possível risco respiratório associado a tosse'}
LIMITACAO = (
    'Resultado experimental de um modelo treinado com 20 consultas. O rótulo '
    'doenca_respiratoria corresponde ao grupo de tosse fornecido no treinamento. '
    'A margem SVM não é probabilidade nem medida de gravidade. Uma sinalização positiva '
    'não confirma doença, e uma negativa não a exclui. A transcrição não é usada como entrada do SVM.'
)


def carregar_modelos(pasta):
    manifesto = json.loads((pasta / 'manifesto.json').read_text(encoding='utf-8'))
    modelos = {}
    for target in TARGETS:
        info = manifesto['modelos'][target]
        nome = info['arquivo']
        if Path(nome).name != nome:
            raise ValueError('O nome do modelo no manifesto deve ser apenas um nome de arquivo.')
        arquivo = pasta / nome
        if hashlib.sha256(arquivo.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError(f'Hash inválido para {nome}; use o modelo e manifesto da mesma exportação.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', InconsistentVersionWarning)
            modelos[target] = joblib.load(arquivo)
        if list(modelos[target].named_steps['atributos'].features) != manifesto['features_entrada']:
            raise ValueError(f'Esquema de entrada divergente para {target}.')
    return modelos, manifesto


def gravar_microfone(destino, duracao, dispositivo=None):
    import sounddevice as sd

    print(f'Gravando o microfone por {duracao} segundos...')
    taxa = 16000
    with sf.SoundFile(destino, mode='w', samplerate=taxa, channels=1, subtype='PCM_16') as arquivo:
        with sd.InputStream(samplerate=taxa, channels=1, dtype='int16', device=dispositivo) as fluxo:
            restantes = duracao * taxa
            while restantes:
                tamanho = min(taxa, restantes)
                amostras, overflow = fluxo.read(tamanho)
                if overflow:
                    raise RuntimeError('Perda de amostras no microfone; repita a gravação.')
                arquivo.write(amostras)
                restantes -= tamanho
    return destino


def preparar_audio(origem, pasta_temporaria):
    """Preserva o áudio de análise; só a cópia para Azure é convertida para 16 kHz."""
    with origem.open('rb') as f:
        if f.read(80).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError('A entrada é um ponteiro Git LFS; obtenha o áudio real.')
    analise = origem
    try:
        sf.info(analise)
    except sf.LibsndfileError:
        analise = pasta_temporaria / 'audio_decodificado.wav'
        try:
            subprocess.run([
                'ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(origem),
                '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le', str(analise),
            ], check=True, capture_output=True)
        except FileNotFoundError as erro:
            raise ValueError('Formato não suportado pelo SoundFile. Instale FFmpeg ou forneça WAV/FLAC.') from erro
        except subprocess.CalledProcessError as erro:
            raise ValueError('Não foi possível decodificar o arquivo de áudio com FFmpeg.') from erro
    destino = pasta_temporaria / 'audio_azure.wav'
    energia, amostras = 0.0, 0
    with sf.SoundFile(analise) as entrada:
        if len(entrada) == 0:
            raise ValueError('O áudio está vazio.')
        info = {'duracao_s': len(entrada) / entrada.samplerate,
                'taxa_amostragem_hz': entrada.samplerate, 'canais': entrada.channels}
        divisor = math.gcd(entrada.samplerate, 16000)
        with sf.SoundFile(destino, mode='w', samplerate=16000, channels=1, subtype='PCM_16') as saida:
            for bloco in entrada.blocks(blocksize=entrada.samplerate * 30, dtype='float32', always_2d=True):
                mono = bloco.mean(axis=1)
                if not np.isfinite(mono).all():
                    raise ValueError('O áudio contém amostras não finitas.')
                energia += float(np.square(mono.astype(np.float64)).sum())
                amostras += len(mono)
                if entrada.samplerate != 16000:
                    mono = resample_poly(mono, 16000 // divisor, entrada.samplerate // divisor)
                saida.write(np.clip(mono, -1.0, 1.0))
    if energia == 0 or amostras == 0:
        raise ValueError('O áudio contém apenas silêncio digital; não será classificado.')
    return analise, destino, info


def classificar_atributos(modelos, atributos):
    resultados = {}
    for target, modelo in modelos.items():
        margens = np.asarray(modelo.decision_function(atributos), dtype=float)
        if not np.isfinite(margens).all():
            raise ValueError(f'O modelo {target} produziu margens inválidas.')
        media = float(margens.mean())
        resultados[target] = {
            'positivo': bool(media > 0), 'margem_media': media,
            'segmentos_positivos': int((margens > 0).sum()), 'total_segmentos': len(margens),
            'segmentos': [
                {'parte': int(linha.parte), 'inicio_s': float(linha.inicio_s),
                 'fim_s': float(linha.fim_s), 'margem': float(margem), 'positivo': bool(margem > 0)}
                for linha, margem in zip(atributos.itertuples(index=False), margens)
            ],
        }
    return resultados


AVISO_MEDICO = (
    'Esta sinalização apoia a avaliação médica e não confirma um diagnóstico. '
    'A ausência de sinalização não exclui a presença de sintomas ou doença.'
)


def sinais_positivos(resultado):
    return [target for target in TARGETS if resultado['classificacoes'][target]['positivo']]


def resumo_medico(resultado):
    sinais = sinais_positivos(resultado)
    if not sinais:
        return 'Nossos modelos preditivos não sinalizaram cansaço, falta de ar ou risco respiratório nesta análise.'
    resumo = (
        'Nossos modelos preditivos sinalizaram os seguintes aspectos para avaliação: '
        + ', '.join(NOMES[target] for target in sinais) + '. '
        'Solicitamos avaliação médica para verificar esses sinais no contexto clínico do paciente.'
    )
    if 'cansaco' in sinais:
        resumo += (
            ' Em caso de cansaço, considerar também a possibilidade de atenção psicológica, '
            'com avaliação da necessidade de terapia psicológica para investigar possível desmotivação. '
            'A sinalização de cansaço, por si só, não permite concluir que haja desmotivação.'
        )
    return resumo


def analisar_relato(textos, idioma):
    idioma_texto = idioma.lower().split('-')[0]
    if not any(texto.strip() for texto in textos):
        return {'status': 'sem_texto', 'idioma': idioma_texto, 'trechos': []}
    try:
        with criar_cliente() as cliente:
            return analisar_sentimento(cliente, textos, idioma_texto)
    except (ValueError, AzureError) as erro:
        return {'status': 'erro', 'idioma': idioma_texto, 'trechos': [], 'erro': type(erro).__name__}


def resumo_sentimento(analise):
    if not analise or analise['status'] == 'erro':
        return 'A análise de sentimento do relato não está disponível nesta avaliação.'
    if analise['status'] == 'sem_texto':
        return 'Não foi possível obter um relato transcrito para a análise de sentimento.'
    nomes = {'positive': 'positivo', 'neutral': 'neutro', 'negative': 'negativo', 'mixed': 'misto'}
    sentimentos = {trecho.get('sentimento') for trecho in analise['trechos'] if 'erro' not in trecho}
    descricoes = [nome for chave, nome in nomes.items() if chave in sentimentos]
    if not descricoes:
        return 'A análise de sentimento do relato não está disponível nesta avaliação.'
    if len(descricoes) == 1:
        return f'A análise identificou conteúdo de caráter {descricoes[0]} no relato.'
    lista = ', '.join(descricoes[:-1]) + ' e ' + descricoes[-1]
    return f'Ao longo do relato, foram identificados conteúdos de caráter {lista}.'


def gerar_relatorio(resultado, destino):
    estilos = getSampleStyleSheet()
    paragrafo = lambda texto, estilo='BodyText': Paragraph(escape(str(texto)), estilos[estilo])
    positivo = bool(sinais_positivos(resultado))
    titulo = 'Alerta para avaliação médica' if positivo else 'Relatório para avaliação médica'
    data = datetime.fromisoformat(resultado['data_utc']).strftime('%d/%m/%Y às %H:%M (UTC)')
    conteudo = [paragrafo(titulo, 'Title'),
                paragrafo(f"Paciente: {resultado.get('paciente') or 'Não informado'}", 'Heading2'),
                paragrafo(f'Data da análise: {data}'), Spacer(1, 12),
                paragrafo(resumo_medico(resultado)), Spacer(1, 16),
                paragrafo('Sinais indicados para avaliação', 'Heading2')]
    linhas = [[paragrafo('Aspecto avaliado'), paragrafo('Indicação dos modelos preditivos')]]
    for target in TARGETS:
        sinalizado = resultado['classificacoes'][target]['positivo']
        linhas.append([
            paragrafo(NOMES[target]),
            paragrafo('Sinalizado para avaliação médica' if sinalizado else 'Não sinalizado nesta análise'),
        ])
    tabela = Table(linhas, colWidths=[200, 250], repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef5')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    conteudo.extend([tabela, Spacer(1, 18), paragrafo(AVISO_MEDICO)])
    conteudo.extend([PageBreak(), paragrafo('Transcrição original da consulta', 'Title')])
    conteudo.append(paragrafo(f"Idioma original: {resultado.get('idioma', 'Não informado')}"))
    for texto in resultado.get('transcricao', []) or ['Não foi possível reconhecer fala nesta gravação.']:
        conteudo.extend([paragrafo(texto), Spacer(1, 8)])
    traducao = resultado.get('traducao', {'status': 'nao_solicitada'})
    if traducao['status'] == 'concluida':
        conteudo.extend([PageBreak(), paragrafo('Tradução da consulta para português', 'Title')])
        for texto in traducao['textos']:
            conteudo.extend([paragrafo(texto), Spacer(1, 8)])
    else:
        mensagens = {
            'nao_necessaria': 'O relato original já está em português; não foi necessária tradução.',
            'nao_solicitada': 'A tradução para português não foi solicitada nesta avaliação.',
            'sem_texto': 'Não houve fala reconhecida para tradução.',
            'erro': 'A tradução para português não está disponível nesta avaliação. O relato original foi preservado.',
        }
        conteudo.extend([Spacer(1, 12), paragrafo(mensagens[traducao['status']])])
    conteudo.extend([
        PageBreak(), paragrafo('Análise de sentimento do relato', 'Title'),
        paragrafo(f"Paciente: {resultado.get('paciente') or 'Não informado'}", 'Heading2'),
        paragrafo(resumo_sentimento(resultado.get('analise_sentimento'))), Spacer(1, 12),
        paragrafo('Essa leitura se refere ao conteúdo do relato e não caracteriza o estado '
                  'emocional do paciente. Deve ser considerada em conjunto com a avaliação médica.'),
    ])
    SimpleDocTemplate(str(destino), title='Relatório para avaliação médica').build(conteudo)


def endereco_email(nome):
    valor = obrigatoria(nome)
    _, endereco = parseaddr(valor)
    if '\n' in valor or '\r' in valor or endereco != valor or '@' not in endereco:
        raise ValueError(f'{nome} deve conter um único endereço de e-mail, sem nome de exibição.')
    return endereco


def enviar_email(resultado, pdf):
    host = obrigatoria('SMTP_HOST')
    porta = int(obrigatoria('SMTP_PORT'))
    seguranca = obrigatoria('SMTP_SECURITY').lower()
    if seguranca not in {'starttls', 'ssl'}:
        raise ValueError('SMTP_SECURITY deve ser starttls ou ssl.')
    usuario = obrigatoria('SMTP_USERNAME')
    obrigatoria('SMTP_PASSWORD')
    remetente, destinatario = endereco_email('EMAIL_FROM'), endereco_email('EMAIL_TO')
    timeout = float(os.getenv('SMTP_TIMEOUT', '30'))
    if not math.isfinite(timeout) or timeout <= 0 or not 1 <= porta <= 65535:
        raise ValueError('SMTP_TIMEOUT ou SMTP_PORT inválido.')
    mensagem = EmailMessage()
    mensagem['Subject'] = 'Alerta para avaliação médica: ' + ', '.join(
        NOMES[target] for target in sinais_positivos(resultado)
    )
    mensagem['From'], mensagem['To'] = remetente, destinatario
    paciente = resultado.get('paciente') or 'Não informado'
    mensagem.set_content(
        f'Prezado(a) médico(a),\n\nPaciente: {paciente}\n\n'
        f'{resumo_medico(resultado)}\n\n'
        f"Análise de sentimento do relato: {resumo_sentimento(resultado.get('analise_sentimento'))}\n\n"
        'O relatório com os sinais indicados para avaliação segue em anexo.\n\n'
        f'{AVISO_MEDICO}\n'
    )
    mensagem.add_attachment(pdf.read_bytes(), maintype='application', subtype='pdf', filename=pdf.name)
    contexto = criar_contexto_smtp()
    if seguranca == 'ssl':
        conexao = smtplib.SMTP_SSL(host, porta, timeout=timeout, context=contexto)
    else:
        conexao = smtplib.SMTP(host, porta, timeout=timeout)
    with conexao as smtp:
        smtp.ehlo()
        if seguranca == 'starttls':
            smtp.starttls(context=contexto)
            smtp.ehlo()
        smtp.login(usuario, os.environ['SMTP_PASSWORD'])
        recusados = smtp.send_message(mensagem)
        if recusados:
            raise RuntimeError('O servidor recusou o destinatário do alerta.')
    return destinatario


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    entrada = parser.add_mutually_exclusive_group(required=True)
    entrada.add_argument('--audio', type=Path, help='Arquivo de áudio (WAV, FLAC ou formato decodificável).')
    entrada.add_argument('--microfone', action='store_true', help='Gravar uma vez e analisar a mesma gravação.')
    parser.add_argument('--duracao', type=int, default=3600, help='Segundos de captura do microfone (padrão: 3600).')
    parser.add_argument('--dispositivo', help='Nome do dispositivo de entrada do microfone.')
    parser.add_argument('--paciente', help='Nome ou identificador do paciente no relatório e no e-mail.')
    parser.add_argument('--idioma', default='pt-BR', help='Idioma da fala para o Azure (padrão: pt-BR).')
    parser.add_argument('--traduzir', action='store_true', default=True,
                        help='Mantido por compatibilidade: a tradução para português já é automática para outros idiomas.')
    parser.add_argument('--output', '-o', required=True, type=Path, help='Caminho do relatório PDF.')
    parser.add_argument('--modelos', type=Path, default=RAIZ / 'outputs/svm/modelos', help='Pasta dos modelos exportados.')
    parser.add_argument('--env', type=Path, help='Arquivo .env (padrão: trabalho4/.env).')
    parser.add_argument('--sem-email', action='store_true', help='Gerar resultados sem enviar alerta por e-mail.')
    args = parser.parse_args()
    if args.microfone and args.duracao <= 0:
        parser.error('--duracao deve ser maior que zero.')
    if args.output.suffix.lower() != '.pdf':
        parser.error('--output deve terminar em .pdf.')
    if args.audio and not args.audio.is_file():
        parser.error(f'Áudio não encontrado: {args.audio}')
    return args


def main():
    args = argumentos()
    carregar_ambiente(args.env)
    modelos, manifesto = carregar_modelos(args.modelos.resolve())
    configuracao = criar_configuracao(args.idioma)
    pdf = args.output.expanduser().resolve()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    origem = args.audio.resolve() if args.audio else pdf.with_suffix('.audio.wav')
    if args.microfone:
        gravar_microfone(origem, args.duracao, args.dispositivo)
    with TemporaryDirectory(prefix='avaliacao_audio_') as temporaria:
        audio_analise, audio_azure, info = preparar_audio(origem, Path(temporaria))
        print('Transcrevendo com Azure Speech...')
        textos = transcrever(configuracao, str(audio_azure), args.duracao)
        # Preserva o original antes de qualquer chamada de tradução.
        pdf.with_suffix('.transcricao.txt').write_text('\n'.join(textos), encoding='utf-8')
        traducao = {'status': 'nao_solicitada', 'idioma': 'pt', 'textos': []}
        if not any(texto.strip() for texto in textos):
            traducao['status'] = 'sem_texto'
        elif args.idioma.lower().split('-')[0] == 'pt':
            traducao['status'] = 'nao_necessaria'
        elif args.traduzir:
            print('Traduzindo a transcrição para português...')
            try:
                traducao['textos'] = traduzir_textos(textos, args.idioma)
                traducao['status'] = 'concluida'
            except (ValueError, RuntimeError) as erro:
                traducao['status'] = 'erro'
                traducao['tipo_erro'] = type(erro).__name__
                print('Não foi possível traduzir o relato. Confira as configurações TRANSLATOR_ no .env. '
                      'O relatório será gerado com a transcrição original.', file=sys.stderr)
        print('Analisando o sentimento do relato com Azure Text Analytics...')
        texto_sentimento = traducao['textos'] if traducao['status'] == 'concluida' else textos
        idioma_sentimento = 'pt' if traducao['status'] == 'concluida' else args.idioma
        sentimento = analisar_relato(texto_sentimento, idioma_sentimento)
        if sentimento['status'] == 'erro':
            print('A análise de sentimento não foi concluída. Confira TEXT_ANALYTICS_ENDPOINT, '
                  'TEXT_ANALYTICS_KEY e a conexão. A avaliação respiratória será preservada.', file=sys.stderr)
        print('Extraindo atributos eGeMAPSv02 e classificando...')
        extrator = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                                   feature_level=opensmile.FeatureLevel.Functionals)
        atributos = pd.concat(extrair_atributos(
            extrator, audio_analise, incluir_rotulos=False
        ), ignore_index=True)
        atributos['arquivo'] = origem.name
        classificacoes = classificar_atributos(modelos, atributos)
    atributos.to_parquet(pdf.with_suffix('.atributos.parquet'), index=False)
    risco = classificacoes['doenca_respiratoria']['positivo']
    alerta = any(classificacoes[target]['positivo'] for target in TARGETS)
    resultado = {
        'paciente': args.paciente.strip() if args.paciente else None,
        'origem': 'Microfone' if args.microfone else origem.name,
        'data_utc': datetime.now(timezone.utc).isoformat(), 'idioma': args.idioma,
        'audio': info, 'modo_analise': 'audio_inteiro',
        'risco_respiratorio_sinalizado': risco, 'classificacoes': classificacoes,
        'alerta_sinalizado': alerta,
        'transcricao': textos, 'traducao': traducao, 'analise_sentimento': sentimento, 'limitacao': LIMITACAO,
        'sha256_modelo_respiratorio': manifesto['modelos']['doenca_respiratoria']['sha256'],
        'email': {'status': 'desativado' if args.sem_email else ('pendente' if alerta else 'nao_acionado')},
    }
    gerar_relatorio(resultado, pdf)
    json_path = pdf.with_suffix('.json')
    def salvar_resultado():
        json_path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    salvar_resultado()
    print(f'PDF gerado: {pdf}')
    for target in TARGETS:
        print(f'{NOMES[target]}:', 'POSITIVA' if classificacoes[target]['positivo'] else 'NEGATIVA')
    if alerta and not args.sem_email:
        try:
            destinatario = enviar_email(resultado, pdf)
        except Exception as erro:
            resultado['email'] = {'status': 'falha', 'tipo_erro': type(erro).__name__}
            salvar_resultado()
            print(f'Falha ao enviar e-mail ({type(erro).__name__}). O PDF foi preservado. '
                  'Confira as configurações SMTP no .env e a conexão.', file=sys.stderr)
            return 2
        resultado['email'] = {'status': 'aceito_pelo_servidor_smtp', 'destinatario': destinatario}
        salvar_resultado()
        print(f'Alerta aceito pelo servidor SMTP para {destinatario}.')
    elif args.sem_email:
        print('Envio de e-mail desativado por --sem-email.')
    else:
        print('E-mail não acionado: nenhum dos três modelos sinalizou positivo.')
    return 2 if sentimento['status'] == 'erro' or traducao['status'] == 'erro' else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nExecução interrompida.', file=sys.stderr)
        sys.exit(130)
    except Exception as erro:
        print(f'Erro: {erro}', file=sys.stderr)
        sys.exit(1)
