"""Gera PDFs das avaliações em JSON, convertendo frames em tempos pelo FPS."""
import argparse
import json
import math
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent


def validar_fps(valor):
    if isinstance(valor, bool):
        raise ValueError('FPS deve ser um número positivo e finito.')
    try:
        fps = float(valor)
    except (ValueError, TypeError):
        raise ValueError('FPS deve ser um número positivo e finito.') from None
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('FPS deve ser um número positivo e finito.')
    return fps


def fps_video(caminho):
    import cv2
    cap = cv2.VideoCapture(str(caminho))
    try:
        if not cap.isOpened():
            raise ValueError(f'Não foi possível abrir o vídeo: {caminho}')
        return validar_fps(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()


def carregar(caminho, fps=None):
    with caminho.open(encoding='utf-8-sig') as arquivo:
        dados = json.load(arquivo)
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        raise ValueError('O JSON deve conter uma lista de objetos ou um objeto.')
    trechos = []
    for indice, item in enumerate(dados, 1):
        if not isinstance(item, dict):
            raise ValueError(f'Trecho {indice}: esperado um objeto.')
        inicio, fim, correto = (item.get(k) for k in ('frame_inicio', 'frame_fim', 'correto'))
        if type(inicio) is not int or type(fim) is not int or inicio < 0 or fim < inicio:
            raise ValueError(f'Trecho {indice}: frames devem ser inteiros, com 0 <= início <= fim.')
        if type(correto) is not bool:
            raise ValueError(f'Trecho {indice}: correto deve ser true ou false.')
        taxa = fps if fps is not None else item.get('fps')
        if taxa is None:
            raise ValueError(f'Trecho {indice}: informe --fps, --video ou fps no JSON.')
        trechos.append((inicio, fim, correto, validar_fps(taxa)))
    return sorted(trechos, key=lambda t: (t[0], t[1]))


def tempo(segundos):
    milissegundos = round(segundos * 1000)
    segundos, ms = divmod(milissegundos, 1000)
    minutos, s = divmod(segundos, 60)
    h, m = divmod(minutos, 60)
    return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'


def gerar_pdf(origem, destino, trechos):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

    estilos = getSampleStyleSheet()
    conteudo = []
    def texto(valor, estilo='BodyText'):
        conteudo.append(Paragraph(valor, estilos[estilo]))
    texto('Relatório de acompanhamento dos exercícios', 'Title')
    texto('Avaliação automática dos movimentos durante a sessão de fisioterapia.')
    texto('Este relatório mostra os momentos do vídeo em que a execução foi considerada correta ou precisa de revisão, para apoiar a conversa entre paciente e fisioterapeuta.')
    total = len(trechos)
    corretos = sum(t[2] for t in trechos)
    conteudo.append(Spacer(1, 12))
    texto('Resumo da avaliação', 'Heading2')
    if total:
        texto(f'Foram avaliados {total} trechos do vídeo.')
        texto(f'Execução correta: {corretos} trecho(s).<br/>Execução a revisar: {total - corretos} trecho(s).')
        percentual = f'{100 * corretos / total:.1f}'.replace('.', ',')
        texto(f'A execução foi considerada correta em {percentual}% dos trechos avaliados. Esse percentual se refere aos trechos analisados, não ao tempo total da sessão.')
        if corretos < total:
            texto('Os trechos destacados na tabela foram classificados como execução incorreta pela análise automática. Eles ajudam a localizar os movimentos para revisão com o fisioterapeuta.')
        else:
            texto('Todos os trechos avaliados foram classificados como execução correta pela análise automática.')
    else:
        texto('Não há trechos avaliados disponíveis para esta sessão. Por isso, não é possível apresentar um resultado sobre a execução dos exercícios.')
    texto('A avaliação abrange apenas os trechos listados. Ela não informa o motivo de uma execução incorreta nem sua gravidade.')
    conteudo.append(Spacer(1, 12))
    if total:
        texto('Momentos avaliados no vídeo', 'Heading2')
        texto('Use os horários de início e fim para encontrar cada trecho no vídeo. Os horários são contados desde o início da gravação, em horas, minutos e segundos; os três dígitos após o ponto indicam frações de segundo.')
        conteudo.append(Spacer(1, 8))
        linhas = [['Trecho', 'Início no vídeo', 'Fim no vídeo', 'Resultado']]
        for i, (inicio, fim, correto, fps) in enumerate(trechos, 1):
            linhas.append([str(i), tempo(inicio / fps), tempo(fim / fps), 'Execução correta' if correto else 'Execução a revisar'])
        tabela = LongTable(linhas, repeatRows=1, colWidths=[45, 130, 130, 170])
        regras = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#23445c')),
                  ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                  ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                  ('FONTSIZE', (0, 0), (-1, -1), 9),
                  ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                  ('TOPPADDING', (0, 0), (-1, -1), 8),
                  ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                  ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.lightgrey)]
        for i, trecho in enumerate(trechos, 1):
            if not trecho[2]:
                regras.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fce4e4')))
        tabela.setStyle(TableStyle(regras))
        conteudo.append(tabela)
    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.drawRightString(A4[0] - 48, 25, f'Página {doc.page}')
        canvas.restoreState()
    destino.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(destino), pagesize=A4, rightMargin=48, leftMargin=48,
                      topMargin=40, bottomMargin=45).build(conteudo, onFirstPage=rodape, onLaterPages=rodape)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    entrada = parser.add_mutually_exclusive_group()
    entrada.add_argument('--json', type=Path, help='Gerar relatório de um único JSON.')
    entrada.add_argument('--input-dir', type=Path, default=BASE / 'outputs', help='Pasta de JSONs (padrão: outputs ao lado do script).')
    parser.add_argument('--output', type=Path, help='Caminho do PDF; somente com --json.')
    parser.add_argument('--output-dir', type=Path, help='Pasta dos PDFs; padrão: mesma pasta de cada JSON.')
    parser.add_argument('--fps', type=validar_fps, help='FPS aplicado a todos os trechos; precede vídeo e JSON.')
    parser.add_argument('--video', type=Path, help='Vídeo de origem para consultar o FPS com OpenCV.')
    args = parser.parse_args()
    if args.output and (not args.json or args.output_dir):
        parser.error('--output exige --json e não pode ser combinado com --output-dir.')
    try:
        fps = args.fps if args.fps is not None else fps_video(args.video) if args.video else None
        arquivos = [args.json] if args.json else sorted(args.input_dir.glob('*.json'))
        if not arquivos:
            raise ValueError(f'Nenhum JSON encontrado em {args.input_dir}')
        falhas = 0
        for origem in arquivos:
            try:
                destino = args.output or (args.output_dir or origem.parent) / f'{origem.stem}.pdf'
                if destino.suffix.lower() != '.pdf':
                    raise ValueError('O arquivo de saída deve ter extensão .pdf.')
                gerar_pdf(origem, destino, carregar(origem, fps))
                print(f'Relatório gerado: {destino}')
            except (ValueError, OSError) as erro:
                falhas += 1
                print(f'Erro em {origem}: {erro}', file=sys.stderr)
        return int(falhas > 0)
    except (ValueError, OSError, ImportError) as erro:
        print(f'Erro: {erro}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
