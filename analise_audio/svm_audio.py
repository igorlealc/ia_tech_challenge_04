"""Transformador importável para os pipelines do notebook treinar_svm_audio.ipynb."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted


class PreprocessamentoCorrelacao(TransformerMixin, BaseEstimator):
    """Imputa mediana e elimina constantes/redundância somente durante fit.

    Prioriza maior |correlação de Pearson com y|; dentre atributos redundantes,
    mantém o primeiro dessa ordenação. limiar=1 desativa o filtro de redundância.
    Colunas inteiramente ausentes no treino recebem mediana zero e são constantes.
    Recebe DataFrame com os atributos acústicos; ignora quaisquer colunas extras.
    """

    def __init__(self, features, limiar=0.95):
        self.features = features
        self.limiar = limiar

    def _numericos(self, X):
        if not isinstance(X, pd.DataFrame):
            raise TypeError('Forneça um DataFrame com os nomes dos atributos acústicos.')
        if X.columns.duplicated().any():
            raise ValueError('Há nomes de colunas duplicados.')
        faltantes = sorted(set(self.features) - set(X.columns))
        if faltantes:
            raise ValueError(f'Atributos obrigatórios ausentes: {faltantes}')
        return X.loc[:, self.features].astype(float).replace([np.inf, -np.inf], np.nan)

    def fit(self, X, y):
        if not 0 < self.limiar <= 1:
            raise ValueError('limiar deve estar no intervalo (0, 1].')
        numeros = self._numericos(X)
        self.feature_names_in_ = np.asarray(self.features, dtype=object)
        self.n_features_in_ = len(self.features)
        self.medianas_ = numeros.median().fillna(0.0)
        completos = numeros.fillna(self.medianas_)
        self.constantes_ = completos.columns[completos.nunique() <= 1].tolist()
        variaveis = completos.drop(columns=self.constantes_)
        if variaveis.empty:
            raise ValueError('Não restam atributos variáveis neste conjunto de treino.')
        alvo = pd.Series(np.asarray(y), index=X.index)
        self.correlacao_target_ = variaveis.corrwith(alvo).fillna(0.0)
        ordem = self.correlacao_target_.abs().sort_values(
            ascending=False, kind='stable'
        ).index
        correlacoes = variaveis.corr().abs().fillna(0.0)
        self.selecionadas_ = []
        self.removidas_ = []
        for coluna in ordem:
            redundantes = [
                outra for outra in self.selecionadas_
                if self.limiar < 1 and correlacoes.loc[coluna, outra] > self.limiar
            ]
            if redundantes:
                mantida = max(redundantes, key=lambda outra: correlacoes.loc[coluna, outra])
                self.removidas_.append({
                    'removida': coluna,
                    'mantida': mantida,
                    'correlacao_absoluta': float(correlacoes.loc[coluna, mantida]),
                })
            else:
                self.selecionadas_.append(coluna)
        return self

    def transform(self, X):
        check_is_fitted(self, 'selecionadas_')
        return self._numericos(X).fillna(self.medianas_).loc[:, self.selecionadas_]

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, 'selecionadas_')
        return np.asarray(self.selecionadas_, dtype=object)
