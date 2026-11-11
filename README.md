# Tech Challenge — Fase 4

Protótipo acadêmico para análise de vídeos de fisioterapia e áudios de consultas. A parte 1 identifica movimentos que precisam de revisão; a parte 2 treina modelos preditivos e gera relatórios para avaliação médica.

## Preparação

- Python **3.11**, disponível como `python3.11`, Bash e acesso à internet.
- No Apple Silicon, use Python nativo ARM64.
- Disponibilize os arquivos de entrada nas pastas indicadas abaixo.
- Para a parte 2, preencha o `.env` conforme [`.env.example`](.env.example), sem publicar credenciais.

Os dois scripts criam ou reutilizam `trabalho4/.venv` e instalam as dependências do [requirements.txt](requirements.txt) da raiz. Execute os comandos abaixo **dentro de `trabalho4`**. A partir da pasta superior, use `bash trabalho4/parte1.sh` ou `bash trabalho4/parte2.sh` com as mesmas opções.

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

## Limitações

Os resultados são exploratórios e destinados à revisão profissional. Na parte 2, `doenca_respiratoria` representa o grupo de tosse rotulado neste trabalho; não confirma diagnóstico. A ausência de sinalização não exclui doença, e a análise de sentimento descreve o texto, não o estado emocional do paciente.
