import argparse
import sys
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
from threading import Event
from xml.sax.saxutils import escape
import azure.cognitiveservices.speech as speechsdk
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from configuracao import carregar_ambiente, obrigatoria
from analisar_sentimento import criar_cliente, analisar_sentimento


def criar_configuracao(idioma='pt-BR', traduzir=False):
    tipo = speechsdk.translation.SpeechTranslationConfig if traduzir else speechsdk.SpeechConfig
    configuracao = tipo(subscription=obrigatoria('SPEECH_KEY'), region=obrigatoria('SPEECH_REGION'))
    configuracao.speech_recognition_language = idioma
    if traduzir:
        configuracao.add_target_language('pt')
    return configuracao


def transcrever(configuracao, caminho, duracao, traduzir=False, originais=None):
    if caminho:
        audio = speechsdk.audio.AudioConfig(filename=caminho)
    else:
        audio = speechsdk.audio.AudioConfig(use_default_microphone=True)
        print(f'Ouvindo o microfone por {duracao} segundos...')

    if traduzir:
        reconhecedor = speechsdk.translation.TranslationRecognizer(translation_config=configuracao, audio_config=audio)
    else:
        reconhecedor = speechsdk.SpeechRecognizer(speech_config=configuracao, audio_config=audio)
    textos = []
    erros = []
    terminou = Event()

    def reconhecer(evento):
        if traduzir and evento.result.reason == speechsdk.ResultReason.TranslatedSpeech:
            texto = evento.result.translations.get('pt')
            if texto is None:
                erros.append('O Azure Speech não retornou a tradução para português.')
                return
            print(f'Original: {evento.result.text}')
            print(f'Tradução: {texto}')
        elif not traduzir and evento.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            texto = evento.result.text
            print(texto)
        else:
            return
        textos.append(texto)
        if originais is not None:
            originais.append(evento.result.text)

    def cancelar(evento):
        if evento.reason == speechsdk.CancellationReason.Error:
            erros.append(evento.error_details)
        terminou.set()

    reconhecedor.recognized.connect(reconhecer)
    reconhecedor.canceled.connect(cancelar)
    reconhecedor.session_stopped.connect(lambda evento: terminou.set())
    reconhecedor.start_continuous_recognition_async().get()
    try:
        terminou.wait(timeout=None if caminho else duracao)
    finally:
        reconhecedor.stop_continuous_recognition_async().get()
    if erros:
        raise RuntimeError('\n'.join(erros))
    return textos


def gerar_pdf(transcricoes, output, analises):
    if len(transcricoes) != len(analises):
        raise ValueError('Cada transcrição deve ter uma análise de sentimento correspondente.')
    estilos = getSampleStyleSheet()
    conteudo = [Paragraph('Transcrição de áudio', estilos['Title'])]
    for origem, textos in transcricoes:
        conteudo.append(Paragraph(escape(origem), estilos['Heading2']))
        for texto in textos or ['Nenhuma fala reconhecida.']:
            conteudo.append(Paragraph(escape(texto), estilos['BodyText']))
            conteudo.append(Spacer(1, 8))
    conteudo.extend([
        PageBreak(),
        Paragraph('Análise de sentimento — Azure Text Analytics', estilos['Title']),
        Paragraph(
            'A análise considera o conteúdo textual transcrito, não a entonação da voz. '
            'Os índices de confiança referem-se às classes de sentimento; não representam '
            'risco de doença nem diagnóstico psicológico.', estilos['BodyText']
        ),
        Spacer(1, 12),
    ])
    nomes = {'positive': 'Positivo', 'neutral': 'Neutro', 'negative': 'Negativo', 'mixed': 'Misto'}
    for (origem, _), analise in zip(transcricoes, analises):
        conteudo.append(Paragraph(escape(origem), estilos['Heading2']))
        conteudo.append(Paragraph(f"Idioma do texto analisado: {escape(analise['idioma'])}", estilos['BodyText']))
        if analise['status'] == 'sem_texto':
            conteudo.append(Paragraph('Sem fala reconhecida: análise de sentimento não realizada.', estilos['BodyText']))
            continue
        if analise['status'] == 'erro':
            conteudo.append(Paragraph(
                'Não foi possível analisar todos os trechos. As falhas estão indicadas abaixo; '
                'a transcrição foi preservada.', estilos['BodyText']
            ))
        if len(analise['trechos']) > 1:
            conteudo.append(Paragraph(
                'O texto foi dividido em trechos para respeitar os limites do serviço. '
                'Cada linha mostra o resultado do Azure para aquele trecho; '
                'não foi calculado um sentimento global por média.', estilos['BodyText']
            ))
        linhas = [['Trecho', 'Caracteres', 'Sentimento', 'Positivo', 'Neutro', 'Negativo']]
        for trecho in analise['trechos']:
            if 'erro' in trecho:
                linhas.append([str(trecho['parte']), str(trecho['caracteres']), 'Não analisado', '-', '-', '-'])
            else:
                linhas.append([
                    str(trecho['parte']), str(trecho['caracteres']),
                    nomes.get(trecho['sentimento'], trecho['sentimento']),
                    f"{trecho['positivo']:.1%}", f"{trecho['neutro']:.1%}", f"{trecho['negativo']:.1%}",
                ])
        tabela = Table(linhas, colWidths=[45, 65, 100, 75, 75, 75], repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef5')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        conteudo.extend([Spacer(1, 8), tabela, Spacer(1, 8)])
        for trecho in analise['trechos']:
            if 'erro' in trecho:
                conteudo.append(Paragraph(
                    f"Trecho {trecho['parte']}: {escape(trecho['erro'])}. "
                    'Confira o recurso Azure Language, as credenciais, o idioma e a conexão.',
                    estilos['BodyText'],
                ))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(output).build(conteudo)
    print(f'PDF gerado: {output}')


def listar_videos(pasta):
    extensoes = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.mpeg', '.mpg', '.wmv'}
    videos = sorted(p for p in Path(pasta).iterdir() if p.is_file() and p.suffix.lower() in extensoes)
    if not videos:
        raise ValueError(f'Nenhum vídeo encontrado em {pasta}')
    return videos


def extrair_audio(video, destino):
    subprocess.run([
        'ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(video.resolve()),
        '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destino),
    ], check=True)


def argumentos():
    parser = argparse.ArgumentParser(description='Transcrever áudio, analisar sentimento no Azure e gerar PDF.')
    entrada = parser.add_mutually_exclusive_group(required=True)
    entrada.add_argument('-a', '--audio', nargs='+', help='Caminhos dos arquivos WAV.')
    entrada.add_argument('--pasta', help='Pasta de vídeos (sem percorrer subpastas).')
    entrada.add_argument('-m', '--microfone', action='store_true', help='Usar o microfone do notebook.')
    parser.add_argument('-o', '--output', required=True, help='Caminho do PDF ou, com --pasta, pasta dos PDFs.')
    parser.add_argument('--duracao', type=int, default=60, help='Segundos de captura do microfone.')
    parser.add_argument('--idioma', default='pt-BR', help='Idioma do áudio.')
    parser.add_argument('--traduzir', action='store_true', help='Transcrever e traduzir para português em tempo real com Azure Speech Translation.')
    parser.add_argument('--env', help='Caminho do .env (padrão: trabalho4/.env).')
    args = parser.parse_args()
    if args.duracao <= 0:
        parser.error('--duracao deve ser maior que zero.')
    return args


def main():
    args = argumentos()
    carregar_ambiente(args.env)
    traduzir = args.traduzir and args.idioma.lower().split('-')[0] != 'pt'
    configuracao = criar_configuracao(args.idioma, traduzir)
    idioma_texto = 'pt' if traduzir else args.idioma.lower().split('-')[0]
    # Valida a configuração local de sentimento antes de iniciar a transcrição.
    with criar_cliente() as cliente:
        return processar(args, configuracao, traduzir, idioma_texto, cliente)


def salvar_original(transcricoes, output):
    destino = Path(output).with_suffix('.transcricao_original.txt')
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('\n\n'.join(
        origem + '\n' + '\n'.join(textos or ['Nenhuma fala reconhecida.'])
        for origem, textos in transcricoes
    ), encoding='utf-8')
    print(f'Transcrição original salva: {destino}')


def processar(args, configuracao, traduzir, idioma_texto, cliente):
    houve_erro = False
    if args.pasta:
        for video in listar_videos(args.pasta):
            print(f'Processando: {video.name}')
            with TemporaryDirectory() as pasta_temporaria:
                audio = Path(pasta_temporaria) / 'audio.wav'
                extrair_audio(video, audio)
                textos_originais = []
                textos = transcrever(configuracao, str(audio), args.duracao, traduzir, textos_originais)
            titulo = f'{video.name} — Tradução para português' if traduzir else video.name
            destino = Path(args.output) / f'{video.name}.pdf'
            salvar_original([(video.name, textos_originais)], destino)
            analise = analisar_sentimento(cliente, textos, idioma_texto)
            houve_erro |= analise['status'] == 'erro'
            gerar_pdf([(titulo, textos)], str(destino), [analise])
        if houve_erro:
            print('Uma ou mais análises de sentimento falharam; consulte os PDFs.', file=sys.stderr)
        return 2 if houve_erro else 0
    transcricoes = []
    originais = []
    for caminho in args.audio or [None]:
        textos_originais = []
        textos = transcrever(configuracao, caminho, args.duracao, traduzir, textos_originais)
        titulo = caminho or 'Microfone'
        originais.append((titulo, textos_originais))
        salvar_original(originais, args.output)
        if traduzir:
            titulo += ' — Tradução para português'
        transcricoes.append((titulo, textos))
    analises = [analisar_sentimento(cliente, textos, idioma_texto) for _, textos in transcricoes]
    gerar_pdf(transcricoes, args.output, analises)
    if any(analise['status'] == 'erro' for analise in analises):
        print('Análise de sentimento incompleta; a transcrição foi preservada no PDF.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
