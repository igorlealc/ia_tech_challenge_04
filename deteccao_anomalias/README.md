# Detecção de anomalias — scripts, parâmetros e ordem de execução

Foi implementado um fluxo para selecionar casos cirúrgicos do VitalDB, baixar seus registros e extrair sinais vitais para arquivos Parquet. A partir desses dados, o projeto permite analisar retrospectivamente a pressão arterial média invasiva (PAM), identificar episódios suspeitos de problemas no sinal e destacar outliers estatísticos. Também foi desenvolvido um monitor simulado que reproduz a PAM, identifica urgências por limites configurados e gera relatório PDF com envio por e-mail.

A análise usa heurísticas e IQR; não há treinamento de modelo de machine learning neste fluxo. Os resultados são exploratórios e não constituem diagnóstico clínico.

## Arquivos em ordem de execução

| Ordem | Arquivo | Função |
| --- | --- | --- |
| 1 | [vitaldb/casos.py](vitaldb/casos.py) | Seleciona os casos, salva metadados e pode baixar os arquivos completos. |
| 2 | [vitaldb/baixar_sinais.py](vitaldb/baixar_sinais.py) | Baixa arquivos faltantes e extrai os sinais para Parquet. |
| 3A | [analisar_pressao_invasiva.ipynb](analisar_pressao_invasiva.ipynb) | Inspeciona, unifica e analisa os sinais; exporta classificações e gráficos. |
| Dentro de 3A | [qualidade_pam.py](qualidade_pam.py) | Avalia a qualidade dos episódios, chamado pelo notebook. |
| 3B | [simular_monitor_pam.py](simular_monitor_pam.py) | Reproduz um caso e avalia urgências pelas faixas configuradas. |
| Dentro de 3B | [relatorio_pam.py](relatorio_pam.py) | Gera e envia o relatório quando acionado pelo monitor. |

```text
casos.py → baixar_sinais.py → Parquets
                                ├── analisar_pressao_invasiva.ipynb
                                │       └── qualidade_pam.py
                                └── simular_monitor_pam.py
                                        └── relatorio_pam.py (quando há alerta)

```

As etapas 3A e 3B são independentes: o monitor pode executar diretamente sobre os Parquets extraídos, sem executar o notebook. Os módulos auxiliares não possuem execução própria por linha de comando.

## Preparação

Os comandos deste guia partem da pasta `trabalho4`, com Python 3.11 e o ambiente virtual ativado:

```bash
python -m pip install -r requirements.txt
```

O notebook requer um ambiente Jupyter com esse mesmo ambiente Python como kernel. O monitor com janela requer interface gráfica e suporte Matplotlib nativo, como Tk ou Qt. A seleção e os downloads exigem internet.

## Organização obrigatória dos dados do VitalDB

Todos os dados baixados do VitalDB devem ficar dentro de `deteccao_anomalias/vitaldb/outputs`. Os exemplos também mantêm os sinais extraídos e a análise exploratória nessa estrutura, separados por seleção:

```text
 deteccao_anomalias/vitaldb/outputs/
 ├── vitaldb_200/
 │   ├── casos_selecionados.csv
 │   ├── clinical_data_200.csv
 │   ├── caso_XXXX.vital
 │   ├── sinais/
 │   │   └── caso_XXXX.parquet
 │   └── analise_exploratoria/
 └── vitaldb_50/
     ├── DICIONARIO_DADOS.md
     └── DICIONARIO_SINAIS_PARQUET.md
```

Os caminhos padrão ainda presentes nos scripts são indicados nas tabelas como referência do comportamento atual. Use os caminhos explícitos dos comandos abaixo para atender à organização definida. Para outra amostra, altere o nome da subpasta, mantendo-a dentro de `vitaldb/outputs`.

Os PDFs e eventos produzidos pelo monitor ficam em `deteccao_anomalias/outputs`; são saídas do monitor, não downloads do VitalDB.

## 1. vitaldb/casos.py — selecionar os casos

Consulta as tabelas clínicas e de trilhas do VitalDB. Filtra por idade, sexo registrado e presença de todos os sinais solicitados; depois sorteia os casos sem repetição, com uma semente reproduzível. Um caso cirúrgico não equivale necessariamente a um paciente distinto.

**Saídas:** `casos_selecionados.csv`, `clinical_data_<quantidade>.csv` e, quando solicitado, arquivos `caso_XXXX.vital`.

| Parâmetro | Padrão | O que faz |
| --- | --- | --- |
| `--quantidade` | `200` | Quantidade de casos; inteiro positivo. |
| `--idade-minima` | `45` | Idade mínima inclusiva, em anos; inteiro não negativo. |
| `--idade-maxima` | `55` | Idade máxima inclusiva; deve ser maior ou igual à mínima. |
| `--sexo` | `F` | Sexo registrado: `F` ou `M`; aceita letras minúsculas. |
| `--semente` | `42` | Semente do sorteio. |
| `--sinais` | `pressao_invasiva` | Lista de sinais obrigatórios, separados por espaços. |
| `--pasta` | `vitaldb/vitaldb_200`, dentro de `deteccao_anomalias` | Destino dos CSVs e arquivos completos. |
| `--somente-lista` | Desativado | Gera somente os CSVs; deixa o download para a próxima etapa. |
| `-h`, `--help` | — | Exibe a ajuda. |

Valores aceitos em `--sinais`: `pressao_invasiva`, `pressao_nao_invasiva`, `frequencia_cardiaca`, `spo2`, `frequencia_respiratoria`, `frequencia_respiratoria_co2`, `temperatura` e `etco2`.

O padrão de `--pasta` no código ainda está fora de `outputs`; informe esse parâmetro explicitamente. Para compatibilidade com o extrator e a análise de PAM invasiva, selecione pressão invasiva, frequência cardíaca e SpO₂:

```bash
python deteccao_anomalias/vitaldb/casos.py \
  --idade-minima 45 --idade-maxima 55 --sexo F \
  --quantidade 200 --semente 42 \
  --sinais pressao_invasiva frequencia_cardiaca spo2 \
  --pasta deteccao_anomalias/vitaldb/outputs/vitaldb_200 \
  --somente-lista
```

Os CSVs são sobrescritos em novas execuções. Arquivos `.vital` existentes e não vazios são reutilizados. A presença das trilhas não garante cobertura nem qualidade das medições.

## 2. vitaldb/baixar_sinais.py — extrair os sinais

Lê a lista de casos sem refazer o sorteio. Reutiliza os arquivos `.vital` disponíveis ou baixa os faltantes, valida sua integridade e exporta um Parquet por caso, com compressão Snappy.

O extrator exige frequência cardíaca, SpO₂ e pelo menos uma pressão média. Exporta `caseid`, `tempo_s`, `frequencia_cardiaca_bpm`, `spo2_percentual`, `pressao_media_invasiva_mmhg` e `pressao_media_nao_invasiva_mmhg`. Uma pressão ausente permanece como coluna nula. Não exporta os demais sinais que podem ser usados na seleção.

| Parâmetro | Padrão | O que faz |
| --- | --- | --- |
| `--casos` | `vitaldb_50/casos_selecionados.csv`, ao lado do script | CSV de entrada com a coluna `caseid`. |
| `--pasta-vital` | `vitaldb_50`, ao lado do script | Pasta dos arquivos completos. |
| `--saida` | `vitaldb_50/sinais`, ao lado do script | Pasta dos Parquets gerados. |
| `--intervalo` | `1.0` | Passo da grade temporal em segundos; finito e positivo. |
| `--limite` | Sem limite | Processa somente os primeiros N casos da lista. |
| `-h`, `--help` | — | Exibe a ajuda. |

Os padrões deste script ainda apontam para `vitaldb_50` fora de `outputs`. Para cumprir a organização definida, informe os três caminhos explicitamente:

```bash
python deteccao_anomalias/vitaldb/baixar_sinais.py \
  --casos deteccao_anomalias/vitaldb/outputs/vitaldb_200/casos_selecionados.csv \
  --pasta-vital deteccao_anomalias/vitaldb/outputs/vitaldb_200 \
  --saida deteccao_anomalias/vitaldb/outputs/vitaldb_200/sinais \
  --intervalo 1
```

A grade não implica novas medições a cada segundo. O script não interpola nem preenche lacunas com zero. Parquets existentes são regenerados; falhas por caso são informadas e não impedem o processamento dos demais.

## 3A. analisar_pressao_invasiva.ipynb — análise exploratória

Abra o notebook e execute as células de cima para baixo. Ele:

1. Inspeciona os Parquets e gera dicionários e inventário dos dados.
2. Unifica os sinais, preservando a PAM original e criando uma versão absoluta para análise.
3. Chama `qualidade_pam.py` para anotar episódios suspeitos e aplicar a configuração de exclusão.
4. Calcula outliers globais por IQR e produz distribuição, boxplot, resumo por caso e série temporal.
5. Exporta resultados e manifesto de rastreabilidade.

Não recebe argumentos de terminal. A configuração fica na primeira célula de código:

| Configuração | Valor a usar neste fluxo | O que faz |
| --- | --- | --- |
| `RAIZ_CONFIG` | Não definido; descoberta automática | Pode ser definido antes da primeira célula para apontar à pasta `deteccao_anomalias`. |
| `BASE` | `RAIZ / 'vitaldb/outputs/vitaldb_200'` | Pasta da seleção, tabela clínica e sinais. |
| `REFERENCIA` | `RAIZ / 'vitaldb/outputs/vitaldb_50'` | Pasta dos dicionários usados como referência semântica. |
| `SAIDA` | `BASE / 'analise_exploratoria'` | Destino dos resultados. |
| `FIGURAS` | `SAIDA / 'figuras'` | Destino dos gráficos PNG. |
| `FATOR_IQR` | `1.5` | Multiplicador do intervalo interquartil; finito e positivo. |
| `CASO_GRAFICO` | `None` | Seleciona automaticamente o caso com maior taxa de outliers; aceita um identificador para seleção manual. |
| Parâmetros de qualidade | Tabela da próxima seção | Controlam a classificação de episódios e a exclusão opcional. |

A pasta de referência precisa conter `DICIONARIO_DADOS.md` e `DICIONARIO_SINAIS_PARQUET.md`. O notebook ainda contém caminhos antigos no código. Antes de executá-lo, ajuste a busca automática de `vitaldb/vitaldb_200/sinais` para `vitaldb/outputs/vitaldb_200/sinais` e substitua as definições na primeira célula:

```python
BASE = RAIZ / 'vitaldb/outputs/vitaldb_200'
REFERENCIA = RAIZ / 'vitaldb/outputs/vitaldb_50'
```

Mantenha `SAIDA = BASE / 'analise_exploratoria'` e `FIGURAS = SAIDA / 'figuras'` após essas definições. Como alternativa à busca automática, defina `RAIZ_CONFIG` com o caminho absoluto de `deteccao_anomalias` antes da primeira célula; isso não substitui o ajuste de `BASE` e `REFERENCIA`.

**A configuração atual do notebook é `EXCLUIR_POSSIVEL_FLUSH = True`.** Assim, possíveis flushes são excluídos da PAM analítica, preservando as linhas e o sinal original. Para apenas anotar os episódios, altere para `False`. Esse valor difere do padrão `False` da classe auxiliar.

Principais saídas: `sinais_unificados.parquet`, `pam_tratada.parquet`, `episodios_qualidade_pam.csv/.parquet`, `resumo_qualidade_pam.csv`, `registros_excluidos_artefatos.parquet`, `pam_classificada_iqr.parquet`, `outliers_pam_iqr.parquet`, `resumo_outliers_por_caso.csv`, dicionários, inventário, figuras e manifesto JSON. Novas execuções substituem as saídas derivadas.

## Dentro de 3A. qualidade_pam.py — avaliar episódios

Módulo importado pelo notebook, sem parâmetros de terminal. A função `avaliar_episodios(registros, parametros=None)` recebe um DataFrame e uma instância opcional de `ParametrosQualidade`; retorna os registros anotados e uma tabela de episódios, sem alterar a entrada.

A avaliação usa a PAM original com sinal. Procura possíveis flushes pela subida, duração e retorno da pressão e suspeitas de sinal baixo pela queda e estabilidade. Contexto insuficiente produz classificação inconclusiva. O flush depende de contexto futuro, portanto a anotação é retrospectiva.

| Parâmetro em `ParametrosQualidade` | Configuração no notebook | Padrão da classe | Significado |
| --- | --- | --- | --- |
| `limite_flush` | `LIMITE_FLUSH_MMHG` | `200.0` | Corte superior para candidatos a flush, em mmHg. |
| `limite_baixo` | `LIMITE_BAIXO_MMHG` | `30.0` | Corte para candidatos de sinal baixo, em mmHg. |
| `janela_contexto_s` | `JANELA_CONTEXTO_S` | `10.0` | Janela de contexto anterior e posterior, em segundos. |
| `duracao_max_flush_s` | `DURACAO_MAX_FLUSH_S` | `10.0` | Duração observada máxima de possível flush. |
| `subida_min_flush` | `SUBIDA_MIN_FLUSH_MMHG` | `50.0` | Subida mínima sobre a mediana anterior, em mmHg. |
| `tolerancia_retorno` | `TOLERANCIA_RETORNO_MMHG` | `15.0` | Tolerância do retorno à mediana anterior, em mmHg. |
| `janela_baixa_s` | `JANELA_BAIXA_S` | `10.0` | Janela móvel de avaliação do sinal baixo. |
| `amplitude_max_baixa` | `AMPLITUDE_MAX_BAIXA_MMHG` | `2.0` | Amplitude máxima no trecho baixo, em mmHg. |
| `queda_min_baixa` | `QUEDA_MIN_BAIXA_MMHG` | `40.0` | Queda mínima em relação ao contexto anterior, em mmHg. |
| `min_observacoes` | `MIN_OBSERVACOES_CONTEXTO` | `3` | Mínimo de observações no contexto. |
| `extensao_min_s` | `EXTENSAO_MIN_CONTEXTO_S` | `5.0` | Extensão temporal mínima do contexto. |
| `lacuna_max_s` | `LACUNA_MAX_S` | `5.0` | Maior lacuna tolerada entre medições no contexto. |
| `excluir_flush` | `EXCLUIR_POSSIVEL_FLUSH` | `False` | Exclui possíveis flushes da PAM analítica; no notebook está `True`. |

Os demais valores atuais do notebook coincidem com os padrões da classe. Suspeitas de sinal baixo e episódios inconclusivos não são excluídos automaticamente. A decisão deve respeitar o instante de disponibilidade registrado nas anotações.

## 3B. simular_monitor_pam.py — reproduzir o monitor

Lê os Parquets, seleciona um caso e reproduz suas medições em um gráfico Matplotlib. Por padrão, aplica valor absoluto à PAM e apresenta um registro por segundo real. O eixo temporal mantém `tempo_s` da gravação. Pode substituir registros por médias em blocos de tempo.

| Parâmetro | Padrão | O que faz |
| --- | --- | --- |
| `--pasta` | Obrigatório | Pasta dos Parquets, contendo uma única versão dos sinais. |
| `--caso` | Obrigatório | Identificador `caseid` a reproduzir. |
| `--urgente-baixa` | Obrigatório | PAM abaixo deste limite é urgência baixa. |
| `--normal-min` | Obrigatório | Início inclusivo da faixa normal configurada. |
| `--normal-max` | Obrigatório | Fim inclusivo da faixa normal configurada. |
| `--urgente-alta` | Obrigatório | PAM acima deste limite é urgência alta. |
| `--inicio-segundos` | `0` | Começa na primeira entrada com tempo igual ou maior; não é atraso de abertura. |
| `--intervalo` | `0` | `0`: registros individuais; inteiro positivo: médias por blocos de N segundos. |
| `--velocidade` | `1` | Registros apresentados por segundo real. |
| `--janela` | `120` | Largura temporal visível do gráfico, em segundos. |
| `--lacuna-max` | `5` | Maior intervalo, em segundos, para conectar visualmente leituras válidas. |
| `--lacuna-alerta` | `5` | Maior intervalo entre medições válidas que preserva a contagem de urgência. |
| `--manter-sinal-original` | Desativado | Desativa a conversão da PAM para valor absoluto. |
| `--sem-interface` | Desativado | Processa sem janela e sem espera; exige `--saida-figura`. |
| `--saida-figura` | Sem saída | Caminho da imagem PNG ao encerrar. |
| `--saida-eventos` | Sem saída | Caminho do JSON de eventos, incluindo relatório e status de envio. |
| `-h`, `--help` | — | Exibe a ajuda. |

Os quatro limites devem ser finitos e estritamente crescentes. Entre urgência baixa e normal há atenção baixa; entre normal e urgência alta há atenção alta. Ausentes e infinitos são tratados como ausência de medição válida.

Exemplo com limites demonstrativos, sem caráter de recomendação clínica; escolha um `caseid` presente nos seus Parquets:

```bash
python deteccao_anomalias/simular_monitor_pam.py \
  --pasta deteccao_anomalias/vitaldb/outputs/vitaldb_200/sinais \
  --caso 1341 \
  --urgente-baixa 40 --normal-min 60 --normal-max 100 --urgente-alta 120 \
  --inicio-segundos 500 --intervalo 0 --velocidade 3 \
  --saida-eventos deteccao_anomalias/outputs/eventos_pam.json
```

O caso precisa conter registros a partir do início solicitado. O script `../parte3.sh` também usa `vitaldb/outputs/vitaldb_200/sinais`, em conformidade com este fluxo.

O monitor aciona o relatório quando a urgência ultrapassa 10 segundos do tempo da série. Exatamente 10 segundos não dispara. Leituras válidas fora da urgência e lacunas acima da tolerância reiniciam a contagem; ausências não disparam envio. Mudanças entre urgência baixa e alta mantêm a contagem. Há no máximo uma tentativa de notificação por execução, inclusive com `--sem-interface`.

As faixas do monitor não são os limites IQR do notebook. O monitor também não aplica automaticamente as heurísticas de `qualidade_pam.py`.

## Dentro de 3B. relatorio_pam.py — gerar PDF e enviar e-mail

Módulo chamado pelo monitor, sem argumentos de terminal. Gera um PDF com identificação do caso, motivo, pressão, limites e duração do episódio; depois anexa o documento a um e-mail.

| Função | Parâmetros | O que faz |
| --- | --- | --- |
| `gerar_pdf(evento, destino)` | Dicionário do evento e caminho de saída | Cria o PDF. |
| `enviar_email(evento, pdf)` | Dicionário do evento e caminho do PDF | Envia o documento pelo SMTP configurado. |
| `notificar_medico(evento)` | Dicionário do evento | Gera o PDF, registra seu caminho no evento e solicita o envio. |

O evento produzido pelo monitor contém `caseid`, `motivo`, `inicio_urgencia_s`, `tempo_s`, `duracao_urgencia_s`, `pam_mmhg`, `limite_baixo_mmhg` e `limite_alto_mmhg`.

A configuração de e-mail é carregada de `trabalho4/.env`, com apoio de `analise_audio/configuracao.py`:

| Variável | Obrigatória / padrão | Finalidade |
| --- | --- | --- |
| `SMTP_HOST` | Obrigatória | Servidor SMTP. |
| `SMTP_PORT` | Obrigatória | Porta entre 1 e 65535. |
| `SMTP_SECURITY` | Obrigatória | `ssl` ou `starttls`. |
| `SMTP_USERNAME` | Obrigatória | Usuário para autenticação. |
| `SMTP_PASSWORD` | Obrigatória | Senha para autenticação. |
| `EMAIL_FROM` | Obrigatória | Endereço único do remetente. |
| `EMAIL_TO` | Obrigatória | Endereço único do destinatário. |
| `SMTP_TIMEOUT` | `30` | Tempo limite em segundos; finito e positivo. |

Os PDFs são gravados em `deteccao_anomalias/outputs/urgencia_caso_<caseid>_<identificador>.pdf`. Em falha de notificação, o monitor continua, registra o erro no evento e preserva o PDF se já tiver sido gerado. Não há nova tentativa na mesma execução.

## Escopo deste guia

Este guia descreve os cinco arquivos `.py` e o notebook presentes na pasta. Para detalhes da aquisição, consulte também [vitaldb/README.md](vitaldb/README.md).
