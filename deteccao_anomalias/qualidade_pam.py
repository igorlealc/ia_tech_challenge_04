"""Heurísticas exploratórias de episódios de PAM; não confirmam a causa clínica."""
from dataclasses import dataclass, asdict
import math

import numpy as np
import pandas as pd

PAM = 'pressao_media_invasiva_mmhg'
ORIGINAL = 'pressao_media_invasiva_original_mmhg'


@dataclass(frozen=True)
class ParametrosQualidade:
    limite_flush: float = 200.0
    limite_baixo: float = 30.0
    janela_contexto_s: float = 10.0
    duracao_max_flush_s: float = 10.0
    subida_min_flush: float = 50.0
    tolerancia_retorno: float = 15.0
    janela_baixa_s: float = 10.0
    amplitude_max_baixa: float = 2.0
    queda_min_baixa: float = 40.0
    min_observacoes: int = 3
    extensao_min_s: float = 5.0
    lacuna_max_s: float = 5.0
    excluir_flush: bool = False

    def __post_init__(self):
        valores = asdict(self)
        if not all(math.isfinite(v) for k, v in valores.items() if k != 'excluir_flush'):
            raise ValueError('Parâmetros numéricos devem ser finitos.')
        if not 0 <= self.limite_baixo < self.limite_flush:
            raise ValueError('Exigido 0 <= limite baixo < limite flush.')
        if (not isinstance(self.min_observacoes, int) or isinstance(self.min_observacoes, bool)
                or self.min_observacoes < 2):
            raise ValueError('min_observacoes deve ser inteiro >= 2.')
        if not isinstance(self.excluir_flush, bool):
            raise ValueError('excluir_flush deve ser booleano.')
        if any(v <= 0 for k, v in valores.items() if k not in
               ('excluir_flush', 'limite_baixo', 'min_observacoes')):
            raise ValueError('Janelas, durações, lacunas e tolerâncias devem ser positivas.')
        if self.extensao_min_s > min(self.janela_contexto_s, self.janela_baixa_s):
            raise ValueError('Extensão mínima não pode superar as janelas.')


def avaliar_episodios(registros, parametros=None):
    """Usa ORIGINAL; retorna registros anotados e tabela de episódios, sem alterar a entrada.

    A anotação por episódio é retrospectiva. instante_decisao_s indica quando as
    evidências estariam disponíveis; não se deve retroagir alertas para inicio_s.
    """
    p = parametros or ParametrosQualidade()
    if registros.duplicated(['caseid', 'tempo_s']).any():
        raise ValueError('Chave (caseid, tempo_s) duplicada.')
    if (registros['caseid'].isna().any() or not np.isfinite(registros['tempo_s']).all()
            or registros['tempo_s'].lt(0).any()):
        raise ValueError('Caso ausente ou tempo inválido.')
    resultado = registros.copy().reset_index(drop=True)
    resultado['pam_antes_filtro_mmhg'] = resultado[PAM]
    resultado['episodio_id'] = pd.Series(pd.NA, index=resultado.index, dtype='Int64')
    resultado['qualidade_pam'] = np.where(np.isfinite(resultado[ORIGINAL]), 'sem_indicio', 'sem_medicao')
    resultado['instante_decisao_qualidade_s'] = np.nan
    resultado['excluido_artefato'] = False
    episodios = []

    def contexto(t, v, inicio, fim, ancora, lado):
        # Fechado nos limites; chamadas anteriores usam < início e posteriores > fim.
        n = len(t)
        extensao = float(t[-1] - t[0]) if n else 0.0
        gap = float(np.diff(t).max()) if n > 1 else np.nan
        borda = float(ancora - t[-1] if lado == 'antes' else t[0] - ancora) if n else np.nan
        suficiente = (n >= p.min_observacoes and extensao >= p.extensao_min_s
                      and gap <= p.lacuna_max_s and borda <= p.lacuna_max_s)
        return {'n': n, 'extensao_s': extensao, 'lacuna_max_s': gap,
                'distancia_borda_s': borda, 'suficiente': bool(suficiente),
                'mediana': float(np.median(v)) if n else np.nan,
                'amplitude': float(np.ptp(v)) if n else np.nan}

    for caso, grupo in resultado.groupby('caseid', sort=True):
        grupo = grupo.sort_values('tempo_s')
        fim_caso = float(grupo.tempo_s.max())
        finitos = grupo[np.isfinite(grupo[ORIGINAL])]
        t = finitos.tempo_s.to_numpy(dtype=float)
        v = finitos[ORIGINAL].to_numpy(dtype=float)
        ids = finitos.index.to_numpy()
        tipos = np.where(v > p.limite_flush, 1, np.where(v < p.limite_baixo, -1, 0))
        i = 0
        while i < len(t):
            tipo = tipos[i]
            if tipo == 0:
                i += 1
                continue
            j = i + 1
            while j < len(t) and tipos[j] == tipo and t[j] - t[j-1] <= p.lacuna_max_s:
                j += 1
            inicio, fim = t[i], t[j-1]
            pre_a = np.searchsorted(t, inicio - p.janela_contexto_s, side='left')
            pre = contexto(t[pre_a:i], v[pre_a:i], inicio-p.janela_contexto_s, inicio, inicio, 'antes')
            pos_b = np.searchsorted(t, fim + p.janela_contexto_s, side='right')
            pos = contexto(t[j:pos_b], v[j:pos_b], fim, fim+p.janela_contexto_s, fim, 'depois')
            janela_pos_completa = fim_caso >= fim + p.janela_contexto_s
            status = 'extremo_preservado'
            decisao = np.nan
            subida = float(v[i:j].max() - pre['mediana'])
            retorno = abs(pos['mediana'] - pre['mediana'])
            baixa_metricas = None
            if tipo == 1:
                # Um episódio sustentado não é rotulado como flush breve.
                if fim - inicio > p.duracao_max_flush_s:
                    status = 'extremo_preservado'
                elif not (pre['suficiente'] and pos['suficiente'] and janela_pos_completa):
                    status = 'inconclusivo'
                elif subida >= p.subida_min_flush and retorno <= p.tolerancia_retorno:
                    status = 'possivel_flush'
                if janela_pos_completa:
                    decisao = fim + p.janela_contexto_s
            else:
                # Procura a primeira janela suficiente usando apenas dados já recebidos.
                status = 'inconclusivo'
                for k in range(i, j):
                    a = max(i, np.searchsorted(t, t[k] - p.janela_baixa_s, side='left'))
                    recente = contexto(t[a:k+1], v[a:k+1], t[k]-p.janela_baixa_s, t[k], t[k], 'antes')
                    if pre['suficiente'] and recente['suficiente']:
                        status = 'extremo_preservado'
                        baixa_metricas = recente
                        decisao = t[k]
                        if (recente['mediana'] < p.limite_baixo
                                and recente['amplitude'] <= p.amplitude_max_baixa
                                and pre['mediana'] - recente['mediana'] >= p.queda_min_baixa):
                            status = 'suspeita_sinal_baixo_constante'
                            break
            numero = len(episodios) + 1
            episodio = {'episodio_id': numero, 'caseid': int(caso), 'tipo': 'alto' if tipo == 1 else 'baixo',
                        'inicio_s': float(inicio), 'fim_s': float(fim),
                        'duracao_observada_s': float(fim-inicio), 'n_observacoes': j-i,
                        'minimo_mmhg': float(v[i:j].min()), 'pico_mmhg': float(v[i:j].max()),
                        'subida_mmhg': subida, 'diferenca_retorno_mmhg': retorno,
                        'janela_posterior_completa': bool(janela_pos_completa),
                        'classificacao': status, 'instante_decisao_s': float(decisao),
                        'excluido': bool(p.excluir_flush and status == 'possivel_flush')}
            for prefixo, medidas in [('antes', pre), ('depois', pos)]:
                episodio.update({f'{prefixo}_{chave}': valor for chave, valor in medidas.items()})
            episodio['mediana_baixa_mmhg'] = baixa_metricas['mediana'] if baixa_metricas else np.nan
            episodio['amplitude_baixa_mmhg'] = baixa_metricas['amplitude'] if baixa_metricas else np.nan
            episodio['queda_mmhg'] = pre['mediana'] - episodio['mediana_baixa_mmhg']
            episodios.append(episodio)
            resultado.loc[ids[i:j], 'episodio_id'] = numero
            resultado.loc[ids[i:j], 'qualidade_pam'] = status
            resultado.loc[ids[i:j], 'instante_decisao_qualidade_s'] = decisao
            if episodio['excluido']:
                resultado.loc[ids[i:j], 'excluido_artefato'] = True
                resultado.loc[ids[i:j], PAM] = np.nan
            i = j
    # Esquema mínimo estável mesmo quando não existe extremo algum.
    colunas = ['episodio_id', 'caseid', 'tipo', 'inicio_s', 'fim_s', 'duracao_observada_s',
               'n_observacoes', 'classificacao', 'instante_decisao_s', 'excluido']
    tabela = pd.DataFrame(episodios) if episodios else pd.DataFrame(columns=colunas)
    return resultado, tabela
