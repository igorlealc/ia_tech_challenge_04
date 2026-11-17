"""Reproduz PAM de um caso Parquet em um monitor Matplotlib (simulação local)."""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

PAM = 'pressao_media_invasiva_mmhg'
CORES = {'urgente_baixa': 'red', 'atencao_baixa': 'darkorange', 'normal': 'blue',
         'atencao_alta': 'darkorange', 'urgente_alta': 'red', 'sem_dado': 'gray'}
ROTULOS = {'urgente_baixa': 'URGENTE — MUITO BAIXA', 'atencao_baixa': 'ATENÇÃO — BAIXA',
           'normal': 'NORMAL NA FAIXA CONFIGURADA', 'atencao_alta': 'ATENÇÃO — ALTA',
           'urgente_alta': 'URGENTE — MUITO ALTA', 'sem_dado': 'SEM MEDIÇÃO VÁLIDA'}


@dataclass(frozen=True)
class Referencias:
    urgente_baixa: float
    normal_min: float
    normal_max: float
    urgente_alta: float

    def __post_init__(self):
        limites = (self.urgente_baixa, self.normal_min, self.normal_max, self.urgente_alta)
        if not all(math.isfinite(v) for v in limites) or not all(a < b for a, b in zip(limites, limites[1:])):
            raise ValueError('Limites finitos em ordem: urgente-baixa < normal-min < normal-max < urgente-alta.')

    def classificar(self, pam: float) -> str:
        if not math.isfinite(pam):
            return 'sem_dado'
        if pam < self.urgente_baixa:
            return 'urgente_baixa'
        if pam < self.normal_min:
            return 'atencao_baixa'
        if pam <= self.normal_max:
            return 'normal'
        if pam <= self.urgente_alta:
            return 'atencao_alta'
        return 'urgente_alta'


def carregar_caso(pasta: Path, caso: int, absoluto: bool = True, intervalo: int = 0) -> pd.DataFrame:
    """Lê somente três colunas e filtra caseid no scanner Parquet."""
    if caso <= 0 or intervalo < 0:
        raise ValueError('Caso deve ser positivo e intervalo não negativo.')
    arquivos = sorted(pasta.glob('*.parquet'))
    if not arquivos:
        raise ValueError(f'Nenhum Parquet diretamente em {pasta}.')
    dataset = ds.dataset([str(p) for p in arquivos], format='parquet')
    colunas = ['caseid', 'tempo_s', PAM]
    if not set(colunas) <= set(dataset.schema.names):
        raise ValueError(f'O dataset deve conter {colunas}.')
    dados = dataset.to_table(columns=colunas, filter=ds.field('caseid') == caso).to_pandas()
    if dados.empty:
        raise ValueError(f'Caso {caso} não encontrado.')
    if not np.isfinite(dados.tempo_s).all() or dados.tempo_s.lt(0).any() or dados.tempo_s.duplicated().any():
        raise ValueError('Tempos devem ser finitos, não negativos e únicos por caso. Não misture bases derivadas na pasta.')
    dados = dados.sort_values('tempo_s').reset_index(drop=True)
    dados['pam_original'] = dados[PAM]
    dados['negativos_convertidos'] = (np.isfinite(dados[PAM]) & dados[PAM].lt(0)).astype(int) if absoluto else 0
    if absoluto:
        dados[PAM] = dados[PAM].abs()
    dados[PAM] = dados[PAM].where(np.isfinite(dados[PAM]))
    dados['n_validas'] = dados[PAM].notna().astype(int)
    if intervalo:
        dados['bloco'] = np.floor(dados.tempo_s / intervalo).astype('int64')
        agrupado = dados.groupby('bloco').agg(
            **{PAM: (PAM, 'mean'), 'n_validas': ('n_validas', 'sum'),
               'negativos_convertidos': ('negativos_convertidos', 'sum')})
        agrupado = agrupado.reindex(range(int(dados.bloco.min()), int(dados.bloco.max()) + 1))
        agrupado[['n_validas', 'negativos_convertidos']] = agrupado[['n_validas', 'negativos_convertidos']].fillna(0).astype(int)
        # Disponível somente ao fechar [início, fim). O último bloco é finalizado no fim da gravação.
        agrupado['tempo_s'] = (agrupado.index + 1) * intervalo
        dados = agrupado.reset_index(drop=True)
    return dados


def selecionar_inicio(dados: pd.DataFrame, inicio_segundos: float) -> pd.DataFrame:
    """Começa na primeira leitura com tempo >= início, preservando os tempos originais."""
    if not math.isfinite(inicio_segundos) or inicio_segundos < 0:
        raise ValueError('O início em segundos deve ser finito e não negativo.')
    trecho = dados.loc[dados.tempo_s >= inicio_segundos].copy().reset_index(drop=True)
    if trecho.empty:
        raise ValueError(f'Não há leituras a partir de {inicio_segundos:g}s neste caso.')
    return trecho


def notificar_medico(evento: dict) -> None:
    if __package__:
        from .relatorio_pam import notificar_medico as enviar
    else:
        from relatorio_pam import notificar_medico as enviar
    enviar(evento)


class MotorAlertas:
    def __init__(self, referencias: Referencias, caso: int, notificador=notificar_medico, lacuna_alerta_s=5):
        if not math.isfinite(lacuna_alerta_s) or lacuna_alerta_s <= 0:
            raise ValueError("A lacuna de alerta deve ser finita e positiva.")
        self.lacuna_alerta_s = lacuna_alerta_s
        self.ultimo_tempo_valido = None
        self.referencias = referencias
        self.caso = caso
        self.notificador = notificador
        self.ultimo_estado_valido = None
        self.eventos = []
        self.inicio_urgencia = None
        self.envio_tentado = False

    def receber(self, tempo_s: float, pam: float, negativos: int = 0, n_validas: int = 1) -> str:
        estado = self.referencias.classificar(pam)
        if (self.ultimo_tempo_valido is not None
                and tempo_s - self.ultimo_tempo_valido > self.lacuna_alerta_s):
            self.inicio_urgencia = None
        if estado == 'sem_dado':
            return estado
        self.ultimo_tempo_valido = float(tempo_s)
        if not estado.startswith('urgente'):
            self.inicio_urgencia = None
        else:
            if self.inicio_urgencia is None:
                self.inicio_urgencia = float(tempo_s)
            duracao = float(tempo_s) - self.inicio_urgencia
            if duracao > 10 and not self.envio_tentado:
                # Reserva antes do envio para evitar duplicação mesmo se o SMTP falhar.
                self.envio_tentado = True
                limite = (self.referencias.urgente_baixa if estado == 'urgente_baixa'
                          else self.referencias.urgente_alta)
                direcao = 'abaixo' if estado == 'urgente_baixa' else 'acima'
                evento = {'caseid': self.caso, 'tempo_s': float(tempo_s), 'pam_mmhg': float(pam),
                          'situacao': estado, 'negativos_convertidos': int(negativos),
                          'n_medicoes_validas': int(n_validas), 'envio': 'pendente',
                          'inicio_urgencia_s': self.inicio_urgencia, 'duracao_urgencia_s': duracao,
                          'lacuna_alerta_s': self.lacuna_alerta_s,
                          'limite_baixo_mmhg': self.referencias.urgente_baixa,
                          'limite_alto_mmhg': self.referencias.urgente_alta,
                          'motivo': f'PAM em urgência por mais de 10 segundos entre medições válidas, '
                                    f'com lacunas de até {self.lacuna_alerta_s:g}s; '
                                    f'leitura atual {direcao} do limite de {limite:g} mmHg.'}
                self.eventos.append(evento)
                try:
                    self.notificador(evento)
                    evento['envio'] = 'aceito_smtp'
                    print(f'Alerta do caso {self.caso} aceito pelo servidor SMTP.', flush=True)
                except Exception as erro:
                    evento['envio'] = 'falha'
                    evento['erro'] = type(erro).__name__
                    print(f'Falha ao gerar/enviar alerta do caso {self.caso}: '
                          f'{type(erro).__name__}. Sem nova tentativa nesta execução.', file=sys.stderr)

        self.ultimo_estado_valido = estado
        return estado


def segmentos_trajetoria(historico, lacuna_max_s):
    """Conecta leituras finitas próximas; cor do segmento segue a leitura de chegada.

    Linhas entre amostras são somente representação visual: não preenchem o dataset
    e não participam da classificação de alertas.
    """
    validos = [(t, v, estado) for t, v, estado in historico if math.isfinite(v)]
    segmentos, cores = [], []
    for anterior, atual in zip(validos, validos[1:]):
        if 0 < atual[0] - anterior[0] <= lacuna_max_s:
            segmentos.append([[anterior[0], anterior[1]], [atual[0], atual[1]]])
            cores.append(CORES[atual[2]])
    return np.asarray(segmentos, dtype=float).reshape(-1, 2, 2), cores


def exibir(dados, motor, args):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from matplotlib.lines import Line2D
    from matplotlib.collections import LineCollection

    fig, ax = plt.subplots(figsize=(13, 6))
    fig.canvas.manager.set_window_title(f'Monitor de PAM — caso {args.caso}')
    fig.subplots_adjust(top=0.75, bottom=0.18)
    ax.set(xlabel='Tempo desde o início da gravação (segundos)', ylabel='PAM (mmHg)')
    ax.grid(alpha=0.2)
    refs = motor.referencias
    for limite, cor in [(refs.urgente_baixa, 'red'), (refs.normal_min, 'darkorange'),
                        (refs.normal_max, 'darkorange'), (refs.urgente_alta, 'red')]:
        ax.axhline(limite, color=cor, linestyle='--', alpha=0.65)
        ax.text(1.005, limite, f'{limite:g}', transform=ax.get_yaxis_transform(), va='center', color=cor)
    trajetoria = LineCollection([], linewidths=1.8, capstyle='round', joinstyle='round')
    ax.add_collection(trajetoria)
    ax.legend(handles=[Line2D([], [], color=c, label=t) for c, t in
                       [('blue', 'Normal'), ('darkorange', 'Atenção'), ('red', 'Urgente')]], loc='upper right')
    titulo = fig.text(0.08, 0.93, f'Caso {args.caso} | aguardando primeira leitura', fontsize=17, weight='bold')
    detalhe = fig.text(0.08, 0.86, '', fontsize=10)
    modo = f'média em blocos de {args.intervalo}s' if args.intervalo else 'medições individuais'
    fig.text(0.08, 0.04, f'SIMULAÇÃO • {modo} • início em {dados.tempo_s.iloc[0]:g}s • 1 leitura a cada {1 / args.velocidade:g}s • e-mail após >10s de urgência; uma tentativa por execução', fontsize=10)
    tempos = dados.tempo_s.to_numpy(dtype=float)
    valores = dados[PAM].to_numpy(dtype=float)
    negativos = dados.negativos_convertidos.to_numpy()
    validas = dados.n_validas.to_numpy()
    historico = deque()
    cursor = 0
    ultimo_estado = 'sem_dado'
    ultimo_valor = np.nan

    def consumir(indice):
        nonlocal cursor, ultimo_estado, ultimo_valor
        # Uma chamada consome exatamente um registro, sem recuperar vários frames de uma vez.
        if indice != cursor:
            raise ValueError('Reprodução deve consumir cada registro uma única vez e em ordem.')
        t, v = tempos[indice], valores[indice]
        ultimo_estado = motor.receber(t, v, negativos[indice], validas[indice])
        historico.append((t, v, ultimo_estado))
        ultimo_valor = v
        cursor += 1

    def renderizar():
        agora = tempos[cursor - 1]
        esquerda = max(tempos[0], agora - args.janela)
        while historico and historico[0][0] < esquerda:
            historico.popleft()
        if historico:
            y = np.array([r[1] for r in historico])
            segmentos, cores = segmentos_trajetoria(historico, args.lacuna_max)
            trajetoria.set_segments(segmentos)
            trajetoria.set_color(cores)
            finitos = y[np.isfinite(y)]
        else:
            finitos = np.array([])
        extremos = np.r_[finitos, refs.urgente_baixa, refs.urgente_alta]
        margem = max(5, float(np.ptp(extremos)) * 0.1)
        ax.set_ylim(float(extremos.min()) - margem, float(extremos.max()) + margem)
        ax.set_xlim(esquerda, max(tempos[0] + args.janela, agora + args.janela * 0.02))
        estado_tela = ultimo_estado
        leitura = f'{ultimo_valor:.1f} mmHg' if estado_tela != 'sem_dado' else '—'
        titulo.set_text(f'Caso {args.caso} | PAM {leitura} | {ROTULOS[estado_tela]}')
        titulo.set_color(CORES[estado_tela])
        fim = ' | FIM DA REPRODUÇÃO' if cursor == len(tempos) else ''
        detalhe.set_text(f't = {agora:.1f}s | {cursor}/{len(tempos)} leituras | urgências registradas: {len(motor.eventos)}{fim}\n'
                         + ('PAM em valor absoluto; negativos convertidos não são clinicamente validados.'
                            if not args.manter_sinal_original else 'PAM com sinal original preservado.'))
        return [trajetoria, titulo, detalhe]

    def atualizar(indice):
        consumir(indice)
        return renderizar()

    def inicializar():
        # Redesenhos da janela não avançam os dados nem repetem alertas.
        return [trajetoria, titulo, detalhe]

    if args.sem_interface:
        for indice in range(len(tempos)):
            consumir(indice)
        renderizar()
    else:
        # Mantém a referência viva até fechar a janela. Sem repeat: não reinicia o caso.
        animacao = FuncAnimation(
            fig, atualizar, frames=range(len(tempos)), init_func=inicializar,
            interval=1000 / args.velocidade, repeat=False, blit=False, cache_frame_data=False)
        plt.show(block=True)
    if args.saida_figura:
        args.saida_figura.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.saida_figura, dpi=150, bbox_inches='tight')
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--pasta', type=Path, required=True, help='Pasta contendo os Parquets de sinais, sem misturar cópias derivadas.')
    parser.add_argument('--caso', type=int, required=True, help='caseid a reproduzir.')
    parser.add_argument('--urgente-baixa', type=float, required=True, help='PAM abaixo deste valor: urgente muito baixa.')
    parser.add_argument('--normal-min', type=float, required=True, help='Início inclusivo da faixa normal; abaixo: atenção baixa.')
    parser.add_argument('--normal-max', type=float, required=True, help='Fim inclusivo da faixa normal; acima: atenção alta.')
    parser.add_argument('--urgente-alta', type=float, required=True, help='PAM acima deste valor: urgente muito alta.')
    parser.add_argument('--inicio-segundos', type=float, default=0, help='Tempo inicial inclusivo da gravação. Começa na primeira leitura em ou após esse tempo; não é uma espera.')
    parser.add_argument('--intervalo', type=int, default=0, help='0: cada registro; inteiro positivo: média da PAM por bloco de N segundos.')
    parser.add_argument('--velocidade', type=float, default=1, help='Registros exibidos por segundo real. Padrão 1: um registro a cada 1 segundo.')
    parser.add_argument('--janela', type=float, default=120, help='Largura visível do gráfico, em segundos.')
    parser.add_argument('--lacuna-max', type=float, default=5, help='Máximo de segundos entre leituras válidas conectadas pela linha; não interpola os dados.')
    parser.add_argument('--lacuna-alerta', type=float, default=5, help='Maior intervalo entre medições válidas que preserva a contagem de urgência, em segundos. Ausências nunca disparam envio.')
    parser.add_argument('--manter-sinal-original', action='store_true', help='Desativa abs(PAM), habilitado por padrão conforme os notebooks.')
    parser.add_argument('--sem-interface', action='store_true', help='Reproduz tudo sem espera e salva a figura; útil para validação em servidor.')
    parser.add_argument('--saida-figura', type=Path, help='PNG da tela ao encerrar.')
    parser.add_argument('--saida-eventos', type=Path, help='JSON com alerta, relatório e status do envio.')
    args = parser.parse_args(argv)
    if any(not math.isfinite(v) or v <= 0 for v in [args.velocidade, args.janela, args.lacuna_max, args.lacuna_alerta]):
        parser.error('Velocidade, janela e lacuna máxima devem ser finitas e positivas.')
    if not math.isfinite(args.inicio_segundos) or args.inicio_segundos < 0:
        parser.error('--inicio-segundos deve ser finito e não negativo.')
    if args.sem_interface and not args.saida_figura:
        parser.error('--sem-interface requer --saida-figura.')
    try:
        referencias = Referencias(args.urgente_baixa, args.normal_min, args.normal_max, args.urgente_alta)
        dados = carregar_caso(args.pasta, args.caso, not args.manter_sinal_original, args.intervalo)
        dados = selecionar_inicio(dados, args.inicio_segundos)
    except (ValueError, OSError, TypeError) as erro:
        parser.error(str(erro))
    import matplotlib
    if args.sem_interface:
        matplotlib.use('Agg')
    else:
        # Backends inline/web/Agg não abrem uma janela nativa do sistema operacional.
        nativos = {'tkagg', 'tkcairo', 'qtagg', 'qt5agg', 'qtcairo', 'qt5cairo', 'macosx', 'wxagg', 'gtk3agg', 'gtk4agg'}
        if matplotlib.get_backend().lower() not in nativos:
            if any(importlib.util.find_spec(nome) is not None for nome in ('PySide6', 'PyQt6', 'PyQt5')):
                matplotlib.use('QtAgg')
            elif importlib.util.find_spec('tkinter') is not None:
                matplotlib.use('TkAgg')
            elif sys.platform == 'darwin':
                matplotlib.use('MacOSX')
            else:
                parser.error('A janela requer suporte gráfico. Instale com python -m pip install PySide6 '
                             'e execute no terminal do computador com interface gráfica. '
                             'Em servidor sem tela, use --sem-interface --saida-figura tela.png.')
    print(f'Caso {args.caso}: {len(dados)} leituras, início em {dados.tempo_s.iloc[0]:g}s. Limites configurados pelo usuário; não representam validação clínica.')
    motor = MotorAlertas(referencias, args.caso, lacuna_alerta_s=args.lacuna_alerta)
    try:
        exibir(dados, motor, args)
    except ImportError as erro:
        parser.error(f'Não foi possível abrir a janela gráfica: {erro}. '
                     'Execute em um desktop com Tk/Qt instalado (python -m pip install PySide6).')
    if args.saida_eventos:
        args.saida_eventos.parent.mkdir(parents=True, exist_ok=True)
        args.saida_eventos.write_text(json.dumps(motor.eventos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Reprodução encerrada; {len(motor.eventos)} alertas registrados; no máximo uma tentativa de envio por execução.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
