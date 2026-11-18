# Tech Challenge — Fase 4

Protótipo acadêmico para análise de vídeos de fisioterapia, áudios de consultas e sinais vitais. A parte 1 identifica movimentos que precisam de revisão; a parte 2 treina modelos preditivos e gera relatórios para avaliação médica; a parte 3 analisa anomalias na pressão arterial média invasiva (PAM) e reproduz um monitor com alertas de urgência.

## Preparação

- Python **3.11**, disponível como `python3.11`, Bash e acesso à internet.
- No Apple Silicon, use Python nativo ARM64.
- Disponibilize os arquivos de entrada nas pastas indicadas abaixo.
- Para a parte 2 e o envio de alertas da parte 3, preencha o `.env` conforme [`.env.example`](.env.example), sem publicar credenciais.

Os scripts `parte1.sh`, `parte2.sh` e `parte3.sh` criam ou reutilizam `trabalho4/.venv` e instalam as dependências do [requirements.txt](requirements.txt) da raiz. Execute os comandos abaixo **dentro de `trabalho4`**. A partir da pasta superior, use `bash trabalho4/parte1.sh`, `bash trabalho4/parte2.sh` ou `bash trabalho4/parte3.sh` com as mesmas opções.

O `parte3.sh` utiliza diretamente o Python de seu ambiente virtual, sem exigir ativação manual, e executa seleção, extração, análise e monitoramento. As opções `--sem-instalar` e `--reutilizar-dados` permitem reutilizar o ambiente e os dados já preparados.

## Parte 1 — Análise de vídeo de fisioterapia

O [parte1.sh](parte1.sh) processa o vídeo com MediaPipe, classifica trechos do movimento do braço e gera um vídeo anotado, um JSON e um relatório PDF.

**Entrada:** `analise_video/inputs/movies/PM_012-Camera17-30fps.mp4`.

```bash
bash parte1.sh
```

É necessário um ambiente gráfico para a janela do OpenCV. Aguarde o processamento terminar; pressionar `q` pode deixar o vídeo de saída incompleto. Para trocar o vídeo ou os parâmetros do exercício, edite `parte1.sh`.

**Saídas em `analise_video/outputs/`:** `avaliacao.json`, `resultado.mp4` e `avaliacao.pdf`.

### Fonte dos vídeos — REHAB24-6

Os vídeos são provenientes do **REHAB24-6**, que disponibiliza gravações de exercícios, dados de movimento e anotações de execução. [Fonte e condições de uso no Zenodo](https://zenodo.org/records/13305826) · [DOI do conjunto de dados](https://doi.org/10.5281/zenodo.13305826).

**Conjunto de dados:** Černek, A.; Sedmidubsky, J.; Budikova, P.; Jánošová, M.; Katzer, L.; Procházka, M. (2024). *REHAB24-6: A multi-modal dataset of physical rehabilitation exercises*, v1. Zenodo.

**Artigo solicitado para citação pelos autores:** Černek, A.; Sedmidubsky, J.; Budikova, P. (2024). *REHAB24-6: Physical Therapy Dataset for Analyzing Pose Estimation Methods*. 17th International Conference on Similarity Search and Applications (SISAP), Springer.

O uso dos dados deve observar as condições de pesquisa não comercial indicadas no registro. Neste trabalho, utilizamos um vídeo selecionado e produzimos classificações e anotações próprias; elas não substituem as anotações originais.

Mais informações: [README da análise de vídeo](analise_video/README.md).

## Parte 2 — Treinamento SVM e avaliação de consultas por áudio

O [parte2.sh](parte2.sh) executa, nesta ordem:

1. Extrai atributos acústicos dos WAVs classificados de `analise_audio/inputs/training`, em segmentos de até 120 segundos.
2. Executa o [notebook SVM](analise_audio/treinar_svm_audio.ipynb), analisa correlações e exporta os modelos de `cansaco`, `falta_ar` e `doenca_respiratoria`.
3. Avalia os WAVs de `analise_audio/inputs/patients` com os modelos recém-treinados.
4. Transcreve, traduz para português quando necessário, analisa o sentimento e gera o PDF. Quando há sinalização respiratória, envia o relatório por e-mail.

### Entradas e configuração

| Pasta | Conteúdo |
| --- | --- |
| `analise_audio/inputs/training/` | WAVs com prefixos `consulta_cansaco_`, `consulta_falta_ar_`, `consulta_doenca_respiratoria_` ou `consulta_sem_relacao_`. |
| `analise_audio/inputs/patients/` | WAVs de consultas para avaliação, separados da massa de treinamento. |

A seleção atual tem 20 consultas de treinamento, cinco por categoria. O notebook separa treino e teste por consulta, mantendo seus segmentos juntos. Os áudios de `patients` não participam do treinamento. Ambas as pastas são lidas sem percorrer subpastas.

Configure no `.env`:

| Serviço | Variáveis |
| --- | --- |
| Azure Speech | `SPEECH_KEY`, `SPEECH_REGION` |
| Azure Translator | `TRANSLATOR_ENDPOINT`, `TRANSLATOR_KEY`, `TRANSLATOR_REGION` quando exigida pelo recurso |
| Azure Text Analytics | `TEXT_ANALYTICS_ENDPOINT`, `TEXT_ANALYTICS_KEY` |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`, `SMTP_TIMEOUT` |

### Execução

Treinar e gerar o relatório **sem enviar e-mail**:

```bash
bash parte2.sh --idioma en-US
```

Para identificar o paciente e habilitar o alerta por e-mail, quando houver um único WAV em `patients`:

```bash
bash parte2.sh --idioma en-US --paciente "Paciente 001"
```

O idioma padrão é `en-US`. Informe a língua **falada no áudio**, não a desejada no relatório; para consultas em português, use `--idioma pt-BR`. A avaliação traduz automaticamente os demais idiomas para português. Todos os áudios de uma execução devem usar o idioma informado.

`--sem-instalar` evita reinstalar dependências, mas mantém a extração e o treinamento. Consulte `bash parte2.sh --help` para outras opções. Sem `--sem-email`, cada nova avaliação positiva pode gerar um novo envio.

### Resultados

Saídas em `analise_audio/outputs/parte2/`:

| Caminho | Conteúdo |
| --- | --- |
| `atributos_treinamento.parquet` | Atributos e rótulos extraídos de `training`. |
| `svm/modelos/` | Três pipelines `.joblib`, manifesto, módulo e versões para reutilização. |
| `svm/treinamento_executado.ipynb`, CSVs e figuras | Treinamento executado, correlações e métricas. |
| `avaliacoes/<audio>.pdf` | Resumo médico, transcrição original, tradução e análise de sentimento. |
| `avaliacoes/<audio>.json`, `.transcricao.txt` e `.atributos.parquet` | Resultados detalhados, texto original e atributos da consulta. |

O PDF é salvo antes do envio de e-mail e permanece disponível se o envio falhar. Falhas de tradução ou sentimento são informadas no relatório. Se o treinamento falhar, a avaliação não começa. Novas execuções substituem saídas de mesmo nome.

Mais informações: [README da análise de áudio](analise_audio/README.md).

### Fonte dos áudios — PriMock57

Os áudios são provenientes do [PriMock57, disponibilizado pela Babylon Health](https://github.com/babylonhealth/primock57), um conjunto de **57 consultas simuladas de atenção primária**, com gravações, transcrições e notas de consulta. Os dados são disponibilizados sob [Creative Commons Attribution 4.0 — CC BY 4.0](https://github.com/babylonhealth/primock57/blob/main/LICENSE.md).

Neste projeto, selecionamos gravações dos participantes no papel de pacientes, renomeamos arquivos e atribuímos rótulos para os grupos estudados. A segmentação, os atributos extraídos, as transcrições e traduções automáticas e as previsões são derivados produzidos por este trabalho; os rótulos não são apresentados como classificações oficiais do PriMock57.

Os WAVs do repositório de origem usam **Git LFS**. Instale-o antes de clonar e execute `git lfs pull` no repositório PriMock57 para obter os áudios reais.

**Citações:** as duas entradas abaixo são preservadas conforme fornecidas na [seção de citação do PriMock57](https://github.com/babylonhealth/primock57#citing), incluindo a indicação original “in press”.

```bibtex
@inproceedings{korfiatis2022primock57,
  title={(in press): PriMock57: A Dataset Of Primary Care Mock Consultations},
  author={Papadopoulos Korfiatis, Alex and Moramarco, Francesco and Sarac, Radmila and Savkov, Aleksandar},
  booktitle={Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics},
  year={2022}
}

@inproceedings{moramarco2022human,
  title={(In press): Human Evaluation and Correlation with Automatic Metrics in Consultation Note Generation},
  author={Moramarco, Francesco and Papadopoulos Korfiatis, Alex and Perera, Mark and Juric, Damir and Flann, Jack and Reiter, Ehud and Belz, Anya and Savkov, Aleksandar},
  booktitle={Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics},
  year={2022}
}
```

## Parte 3 — Detecção de anomalias e monitor simulado de PAM

O [parte3.sh](parte3.sh) prepara o ambiente virtual e executa os componentes existentes do módulo [deteccao_anomalias](deteccao_anomalias/README.md), nesta ordem:

1. Seleciona **200 casos do sexo registrado feminino, entre 45 e 55 anos**, com semente **42**, usando `vitaldb/casos.py`. Exige pressão invasiva, frequência cardíaca e SpO₂ e grava a lista e os metadados com `--somente-lista`.
2. Baixa os arquivos completos faltantes e extrai os sinais com `vitaldb/baixar_sinais.py`, em uma grade de **1 segundo**.
3. Executa uma cópia do [notebook de análise](deteccao_anomalias/analisar_pressao_invasiva.ipynb), que unifica os dados, avalia episódios suspeitos com `qualidade_pam.py` e calcula outliers por IQR.
4. Reproduz o **caso 1341** com `simular_monitor_pam.py`; quando há urgência persistente, `relatorio_pam.py` gera o PDF e solicita o envio por e-mail.

O shell interrompe a execução se a seleção, a extração ou a análise falhar. Os scripts Python e o notebook original são preservados. Esta parte utiliza regras temporais e métodos estatísticos; não treina um modelo de machine learning.

### Entradas e configuração

**Todos os dados baixados do VitalDB ficam em `deteccao_anomalias/vitaldb/outputs/`.** Os caminhos utilizados pelo shell são:

| Pasta | Conteúdo |
| --- | --- |
| `deteccao_anomalias/vitaldb/outputs/vitaldb_200/` | Lista de casos, tabela clínica e arquivos completos `.vital`. |
| `deteccao_anomalias/vitaldb/outputs/vitaldb_200/sinais/` | Um Parquet de sinais por caso. |
| `deteccao_anomalias/vitaldb/outputs/vitaldb_200/analise_exploratoria/` | Notebook executado, tabelas, classificações, gráficos e manifesto. |
| `deteccao_anomalias/vitaldb/outputs/vitaldb_50/` | Dicionários da amostra anterior usados como referência pelo notebook. |
| `deteccao_anomalias/outputs/` | PDF de urgência, eventos do monitor e figura final. |

Antes de iniciar, disponibilize `DICIONARIO_DADOS.md` e `DICIONARIO_SINAIS_PARQUET.md` na pasta `vitaldb/outputs/vitaldb_50`. O shell verifica esses arquivos; eles não são gerados pelo download dos casos. Casos cirúrgicos não correspondem necessariamente a pacientes distintos.

Para o envio dos alertas, configure no `.env`:

| Serviço | Variáveis |
| --- | --- |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` e, opcionalmente, `SMTP_TIMEOUT` |

`SMTP_SECURITY` aceita `ssl` ou `starttls`; o tempo limite padrão é 30 segundos. Esta parte não utiliza os serviços Azure de transcrição, tradução ou sentimento.

### Execução

Para executar o fluxo completo, dentro de `trabalho4`:

```bash
bash parte3.sh
```

O shell cria ou reutiliza `.venv`, verifica Python 3.11 e instala as dependências de `requirements.txt`. Não é necessário ativar o ambiente manualmente. Para utilizar outro ambiente virtual:

```bash
PARTE3_VENV="/caminho/para/ambiente" bash parte3.sh --sem-instalar
```

Se a pasta do ambiente existir, mas seu Python não funcionar, o shell encerra com uma mensagem de erro; recrie o ambiente localmente ou informe `PARTE3_VENV`.

As opções disponíveis são:

| Opção | Comportamento |
| --- | --- |
| `--sem-instalar` | Pula a instalação de dependências, mantendo a verificação do Python e as etapas do fluxo. |
| `--reutilizar-dados` | Pula a seleção, o download e a extração. Usa os CSVs e Parquets existentes e executa novamente a análise. |
| `--sem-interface` | Executa o monitor sem janela e sem espera, salvando o PNG. Mantém o envio de alerta já implementado. |
| `--sem-monitor` | Encerra após a análise retrospectiva; não abre o monitor nem aciona suas notificações. |
| `--help`, `-h` | Exibe a ajuda e encerra. |

Para reutilizar os dados e as dependências já instaladas:

```bash
bash parte3.sh --sem-instalar --reutilizar-dados
```

Para executar a análise e o monitor em um ambiente sem tela:

```bash
bash parte3.sh --sem-instalar --reutilizar-dados --sem-interface
```

Para executar somente a análise dos dados já preparados, sem monitoramento:

```bash
bash parte3.sh --sem-instalar --reutilizar-dados --sem-monitor
```

`--reutilizar-dados` exige `casos_selecionados.csv`, `clinical_data_200.csv` e os Parquets correspondentes em `vitaldb/outputs/vitaldb_200`. O notebook verifica a consistência entre os casos dos três conjuntos. A opção não recupera arquivos faltantes; nesse caso, execute o fluxo completo.

A análise é executada por NBClient no mesmo Python do shell, com limite de **600 segundos por célula**. Somente a cópia executada recebe os caminhos ajustados para `vitaldb/outputs` e a configuração da raiz do módulo. Assim, não é necessário editar o notebook original para executar `parte3.sh`. A cópia é salva em `analise_exploratoria/analise_executada.ipynb`, inclusive se uma célula falhar, para permitir a inspeção do erro.

O shell mantém os parâmetros analíticos do notebook. Na versão atual, `EXCLUIR_POSSIVEL_FLUSH = True` exclui possíveis flushes da PAM analítica, preservando as linhas e o sinal original. Os parâmetros e a execução manual estão descritos no [guia de detecção de anomalias](deteccao_anomalias/README.md).

### Parâmetros do monitor

| Parâmetro | Valor utilizado por `parte3.sh` |
| --- | --- |
| `--caso` | `1341` |
| `--inicio-segundos` | `500` segundos da gravação |
| `--velocidade` | `3` registros por segundo real |
| `--intervalo` | `0`: registros individuais, sem agregação |
| `--urgente-baixa` | `40` mmHg |
| `--normal-min` | `60` mmHg |
| `--normal-max` | `100` mmHg |
| `--urgente-alta` | `120` mmHg |
| `--saida-eventos` | `deteccao_anomalias/outputs/eventos_pam.json` |
| `--saida-figura` | `deteccao_anomalias/outputs/monitor_pam.png` |

**Os limites são exemplos de funcionamento, não recomendações clínicas.** O caso 1341 deve existir na seleção e conter registros a partir de 500 segundos. Para alterar esses valores, edite a chamada do monitor em `parte3.sh` ou execute o script Python diretamente, conforme o guia do módulo. O shell não aceita esses parâmetros como opções próprias.

A janela requer ambiente gráfico e suporte Matplotlib nativo, como Tk ou Qt. Por padrão, o monitor utiliza o valor absoluto da PAM e os limites de lacuna definidos no próprio script.

O relatório é acionado quando a urgência ultrapassa **10 segundos do tempo da série**, e não do tempo real da animação. Leituras válidas fora da urgência reiniciam a contagem. Lacunas de até cinco segundos entre medições válidas são toleradas por padrão; lacunas maiores reiniciam a contagem. Ausências não disparam envio. Há **no máximo uma tentativa de notificação por execução**, inclusive em caso de falha.

O modo `--sem-interface` também pode enviar o alerta por e-mail. Não há opção `--sem-email` no fluxo atual. Para executar somente a análise, sem acionar o monitor, utilize `--sem-monitor`.

### Resultados

Os caminhos da tabela são relativos a `deteccao_anomalias`:

| Caminho | Conteúdo |
| --- | --- |
| `vitaldb/outputs/vitaldb_200/casos_selecionados.csv` e `clinical_data_200.csv` | Identificadores selecionados e metadados clínicos. |
| `vitaldb/outputs/vitaldb_200/caso_XXXX.vital` | Registro completo baixado do VitalDB. |
| `vitaldb/outputs/vitaldb_200/sinais/caso_XXXX.parquet` | Sinais extraídos com identificação do caso e tempo relativo. |
| `vitaldb/outputs/vitaldb_200/analise_exploratoria/analise_executada.ipynb` | Cópia do notebook com parâmetros de caminho e saídas das células. |
| `vitaldb/outputs/vitaldb_200/analise_exploratoria/` | Base unificada, PAM tratada, episódios suspeitos, outliers por IQR, resumos, dicionários, figuras e manifesto. |
| `outputs/urgencia_caso_<caseid>_<identificador>.pdf` | Relatório gerado quando o monitor identifica uma urgência persistente. |
| `outputs/eventos_pam.json` e `outputs/monitor_pam.png` | Eventos e figura final, solicitados automaticamente pelo shell ao executar o monitor. |

Em falha de envio, o monitor continua e preserva o PDF se já tiver sido gerado. Novas extrações regeneram os Parquets; novas análises e execuções do monitor substituem saídas de mesmo nome. Com `--sem-monitor`, os arquivos de monitoramento existentes não são atualizados e podem pertencer a execuções anteriores.

Na execução documentada, a análise reuniu **200 casos de 193 pacientes**, com **2.455.052 linhas**, e identificou **88.778 outliers** entre **1.124.019 observações finitas após o tratamento** (7,90%). No caso 1341, o PDF registra uma urgência iniciada em 522 s e detectada em 534 s, com PAM de 195 mmHg. Esses resultados e suas limitações estão detalhados no [relatório técnico em HTML](RELATORIO_TECNICO.html).

Mais informações: [README da detecção de anomalias](deteccao_anomalias/README.md) e [README de seleção e extração do VitalDB](deteccao_anomalias/vitaldb/README.md).

### Fonte dos sinais e referências da Parte 3

Os registros são obtidos da API pública do **VitalDB**, descrito por **Lee et al. (2022)** em *VitalDB, a high-fidelity multi-parameter vital signs database in surgical patients*. [Artigo e autores](https://www.nature.com/articles/s41597-022-01411-5.pdf) · [DOI](https://doi.org/10.1038/s41597-022-01411-5).

A lista de casos e a tabela clínica permitem relacionar as séries por `caseid`; `subjectid` identifica o paciente nos metadados. Os Parquets preservam as lacunas dos sinais e não contêm rótulos clínicos de anomalia. Uma linha por segundo não implica uma nova medição a cada segundo. Os arquivos `.vital` devem ser preservados para consulta aos registros originais.

A regra estatística de 1,5 × IQR é descrita no [NIST/SEMATECH e-Handbook — Box Plot](https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm). Os gráficos utilizam [Matplotlib, de Hunter (2007)](https://matplotlib.org/stable/project/citing.html); a execução do notebook utiliza [NBClient, do Project Jupyter](https://nbclient.readthedocs.io/en/latest/); os PDFs utilizam [ReportLab](https://docs.reportlab.com/). As heurísticas temporais de qualidade e os limites demonstrativos do monitor são implementações deste projeto, sem validação clínica atribuída a essas referências.

## Limitações

Os resultados são exploratórios e destinados à revisão profissional. Na parte 2, `doenca_respiratoria` representa o grupo de tosse rotulado neste trabalho; não confirma diagnóstico. A ausência de sinalização não exclui doença, e a análise de sentimento descreve o texto, não o estado emocional do paciente.

Na parte 3, outliers por IQR e suspeitas de artefato não confirmam alterações clínicas. O IQR é retrospectivo e usa a base completa; os limites do monitor são informados pelo usuário. As heurísticas de qualidade não são aplicadas automaticamente pelo monitor, e a conversão da PAM para valor absoluto não valida medições negativas. As três partes processam bases distintas, sem fusão automática das modalidades em um diagnóstico único.

## Referências

Referências externas dos conjuntos de dados, métodos, serviços e ferramentas apresentados nas três partes. Autores e dados bibliográficos conferidos nas fontes indicadas; documentação técnica consultada em 18 de novembro de 2026.

1. **ČERNEK, Andrej; SEDMIDUBSKY, Jan; BUDIKOVA, Petra; JÁNOŠOVÁ, Miriama; KATZER, Lukáš; PROCHÁZKA, Michal.** *REHAB24-6: A multi-modal dataset of physical rehabilitation exercises*. Versão 1. Zenodo, 2024. Conjunto de dados. [Acessar a referência](https://doi.org/10.5281/zenodo.13305826). Aplicação no trabalho: Fonte dos vídeos de reabilitação.

2. **ČERNEK, Andrej; SEDMIDUBSKY, Jan; BUDIKOVA, Petra.** *REHAB24-6: Physical Therapy Dataset for Analyzing Pose Estimation Methods*. In: Similarity Search and Applications — SISAP 2024. Lecture Notes in Computer Science, v. 15268. Cham: Springer, 2025, p. 18–33. Publicação on-line em 25 out. 2024; ano bibliográfico conforme a editora. [Acessar a referência](https://doi.org/10.1007/978-3-031-75823-2_2). Aplicação no trabalho: Artigo associado ao conjunto REHAB24-6.

3. **LUGARESI, Camillo; TANG, Jiuqiang; NASH, Hadon; McCLANAHAN, Chris; UBOWEJA, Esha; HAYS, Michael; ZHANG, Fan; CHANG, Chuo-Ling; YONG, Ming Guang; LEE, Juhyun; CHANG, Wan-Teh; HUA, Wei; GEORG, Manfred; GRUNDMANN, Matthias.** *MediaPipe: A Framework for Building Perception Pipelines*. arXiv:1906.08172, 2019. [Acessar a referência](https://arxiv.org/abs/1906.08172). Aplicação no trabalho: Framework utilizado na análise de vídeo.

4. **BAZAREVSKY, Valentin; GRISHCHENKO, Ivan; RAVEENDRAN, Karthik; ZHU, Tyler; ZHANG, Fan; GRUNDMANN, Matthias.** *BlazePose: On-device Real-time Body Pose tracking*. arXiv:2006.10204, 2020. [Acessar a referência](https://arxiv.org/abs/2006.10204). Aplicação no trabalho: Referência da abordagem de estimativa de pose corporal associada ao MediaPipe Pose.

5. **OPENCV TEAM.** *OpenCV: Introduction*. Documentação técnica da biblioteca Open Source Computer Vision. Sem data de publicação indicada. [Acessar a referência](https://docs.opencv.org/4.x/d1/dfb/intro.html). Aplicação no trabalho: Leitura, processamento, anotação e gravação de vídeo.

6. **PAPADOPOULOS KORFIATIS, Alex; MORAMARCO, Francesco; SARAC, Radmila; SAVKOV, Aleksandar.** *PriMock57: A Dataset Of Primary Care Mock Consultations*. In: Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics, v. 2: Short Papers. Dublin: ACL, 2022, p. 588–598. DOI: 10.18653/v1/2022.acl-short.65. [Acessar a referência](https://aclanthology.org/2022.acl-short.65/). Aplicação no trabalho: Fonte das consultas simuladas utilizadas na análise de áudio.

7. **MORAMARCO, Francesco; PAPADOPOULOS KORFIATIS, Alex; PERERA, Mark; JURIC, Damir; FLANN, Jack; REITER, Ehud; BELZ, Anya; SAVKOV, Aleksandar.** *Human Evaluation and Correlation with Automatic Metrics in Consultation Note Generation*. In: Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics, v. 1: Long Papers. Dublin: ACL, 2022, p. 5739–5754. DOI: 10.18653/v1/2022.acl-long.394. [Acessar a referência](https://aclanthology.org/2022.acl-long.394/). Aplicação no trabalho: Trabalho associado ao PriMock57, citado na documentação da base; seu protocolo de avaliação humana não foi reproduzido neste projeto.

8. **EYBEN, Florian; WÖLLMER, Martin; SCHULLER, Björn.** *openSMILE — The Munich Versatile and Fast Open-Source Audio Feature Extractor*. In: Proceedings of the 18th ACM International Conference on Multimedia. Firenze: ACM, 2010, p. 1459–1462. [Acessar a referência](https://audeering.github.io/opensmile-python/#citing). [Documentação de eGeMAPSv02](https://audeering.github.io/opensmile-python/). Aplicação no trabalho: Referência bibliográfica oficial do extrator acústico. A documentação também descreve a implementação eGeMAPSv02/Functionals.

9. **EYBEN, Florian; SCHERER, Klaus; SCHULLER, Björn; SUNDBERG, Johan; ANDRÉ, Elisabeth; BUSSO, Carlos; DEVILLERS, Laurence; EPPS, Julien; LAUKKA, Petri; NARAYANAN, Shrikanth; TRUONG, Khiet.** *The Geneva Minimalistic Acoustic Parameter Set (GeMAPS) for Voice Research and Affective Computing*. IEEE Transactions on Affective Computing. Publicação antecipada, 2015. DOI: 10.1109/TAFFC.2015.2457417. [Acessar a referência](https://sail.usc.edu/publications/files/eyben-preprinttaffc-2015.pdf). Aplicação no trabalho: Fundamentação dos conjuntos GeMAPS e eGeMAPS; a variante de software utilizada no projeto é eGeMAPSv02.

10. **PEDREGOSA, Fabian; VAROQUAUX, Gaël; GRAMFORT, Alexandre; MICHEL, Vincent; THIRION, Bertrand; GRISEL, Olivier; BLONDEL, Mathieu; PRETTENHOFER, Peter; WEISS, Ron; DUBOURG, Vincent; VANDERPLAS, Jake; PASSOS, Alexandre; COURNAPEAU, David; BRUCHER, Matthieu; PERROT, Matthieu; DUCHESNAY, Édouard.** *Scikit-learn: Machine Learning in Python*. Journal of Machine Learning Research, v. 12, p. 2825–2830, 2011. [Acessar a referência](https://www.jmlr.org/papers/v12/pedregosa11a.html). Aplicação no trabalho: Biblioteca utilizada na padronização, validação cruzada, busca de hiperparâmetros e classificação SVM.

11. **FAN, Rong-En; CHANG, Kai-Wei; HSIEH, Cho-Jui; WANG, Xiang-Rui; LIN, Chih-Jen.** *LIBLINEAR: A Library for Large Linear Classification*. Journal of Machine Learning Research, v. 9, p. 1871–1874, 2008. [Acessar a referência](https://www.jmlr.org/papers/v9/fan08a.html). [Documentação de LinearSVC](https://scikit-learn.org/stable/modules/generated/sklearn.svm.LinearSVC.html). Aplicação no trabalho: Biblioteca que fundamenta a implementação de LinearSVC utilizada pelo scikit-learn.

12. **MICROSOFT.** *Speech to text e Speech translation*. Microsoft Learn. Documentação técnica dos serviços de reconhecimento e tradução de fala. Sem data bibliográfica fixada. [Acessar a referência](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text). [Documentação de Speech translation](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-translation). Aplicação no trabalho: Transcrição contínua e tradução de fala disponibilizadas nos scripts de áudio.

13. **MICROSOFT.** *Azure Translator — Text translation overview*. Microsoft Learn. Documentação técnica do serviço de tradução textual. Sem data bibliográfica fixada. [Acessar a referência](https://learn.microsoft.com/en-us/azure/ai-services/translator/text-translation/overview). Aplicação no trabalho: Tradução posterior à transcrição no fluxo de avaliação de consultas.

14. **MICROSOFT.** *What are sentiment analysis and opinion mining?*. Microsoft Learn. Documentação técnica do Azure Language. Sem data bibliográfica fixada. [Acessar a referência](https://learn.microsoft.com/en-us/azure/ai-services/language-service/sentiment-opinion-mining/overview). Aplicação no trabalho: Classificação do sentimento dos textos transcritos ou traduzidos.

15. **LEE, Hyung-Chul; PARK, Yoonsang; YOON, Soo Bin; YANG, Seong Mi; PARK, Dongnyeok; JUNG, Chul-Woo.** *VitalDB, a high-fidelity multi-parameter vital signs database in surgical patients*. Scientific Data, v. 9, artigo 279, 2022. DOI: 10.1038/s41597-022-01411-5. [Acessar a referência](https://www.nature.com/articles/s41597-022-01411-5.pdf). Aplicação no trabalho: Fonte dos registros cirúrgicos e sinais vitais utilizados na análise de PAM.

16. **NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY (NIST); SEMATECH.** *Box Plot*. NIST/SEMATECH e-Handbook of Statistical Methods, seção 1.3.3.7. Sem data de publicação indicada. [Acessar a referência](https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm). Aplicação no trabalho: Referência para quartis, intervalo interquartil e limites de 1,5 × IQR.

17. **HUNTER, John D.** *Matplotlib: A 2D Graphics Environment*. Computing in Science & Engineering, v. 9, n. 3, p. 90–95, 2007. DOI: 10.1109/MCSE.2007.55. [Acessar a referência](https://matplotlib.org/stable/project/citing.html). Aplicação no trabalho: Produção dos gráficos exploratórios, do monitor de PAM e das figuras deste relatório.

18. **REPORTLAB.** *ReportLab Documentation*. Documentação técnica da biblioteca de geração de documentos PDF. Sem data de publicação indicada. [Acessar a referência](https://docs.reportlab.com/). Aplicação no trabalho: Geração dos relatórios de vídeo, áudio e urgência de PAM.

19. **PROJECT JUPYTER.** *NBClient: a client library for programmatic notebook execution*. Documentação técnica. Sem data bibliográfica fixada. [Acessar a referência](https://nbclient.readthedocs.io/en/latest/). Aplicação no trabalho: Execução programática dos notebooks usados nos fluxos do projeto.
