# Tech Challenge — Fase 4

Este diretório reúne os arquivos do trabalho descrito em [IADT — Fase 4 — Tech Challenge](IADT%20-%20Fase%204%20-%20Tech%20challenge.pdf). O desafio propõe o uso de dados médicos de vídeo, áudio e texto para identificar situações fora do padrão esperado.

Este README documenta a **parte 1 — Análise de Vídeo**, implementada para demonstrar a capacidade de utilizar visão computacional na identificação de execuções corretas e incorretas de um exercício de fisioterapia.

## Parte 1 — Análise de vídeo de fisioterapia

A solução processa uma gravação de um exercício, identifica pontos corporais com MediaPipe e acompanha o movimento do braço direito. A partir das posições do ombro e do pulso, calcula uma orientação angular e verifica a passagem pelas faixas esperadas durante a ida e a volta do movimento.

Os trechos identificados são classificados e utilizados para gerar:

- Um JSON com os intervalos e as classificações.
- Um vídeo anotado com os resultados da avaliação.
- Um relatório PDF para leitura por fisioterapeutas e pacientes, com resumo e horários dos trechos avaliados.

O fluxo demonstra os três requisitos da parte 1: processamento de um vídeo de fisioterapia, detecção de movimentos fora do padrão esperado e geração automática de relatório indicando os trechos que precisam de revisão.

### Origem dos vídeos — REHAB24-6

Os vídeos utilizados neste trabalho vieram do **REHAB24-6: A multi-modal dataset of physical rehabilitation exercises**, disponibilizado publicamente no Zenodo. O conjunto fornece vídeos de exercícios de reabilitação, dados de movimento, segmentação das repetições e rótulos de execução correta ou incorreta.

- [Acessar o REHAB24-6 e baixar os arquivos no Zenodo](https://zenodo.org/records/13305826).
- [Referência permanente — DOI: 10.5281/zenodo.13305826](https://doi.org/10.5281/zenodo.13305826).

Referência: Černek, A.; Sedmidubsky, J.; Budikova, P.; Jánošová, M.; Katzer, L.; Procházka, M. (2024). *REHAB24-6: A multi-modal dataset of physical rehabilitation exercises* (v1) [Conjunto de dados]. Zenodo.

### Escopo e referência da demonstração

O objetivo é apresentar um protótipo demonstrativo para o vídeo e o exercício selecionados. Os parâmetros estão ajustados para esse cenário; o resultado não representa uma validação para qualquer exercício ou enquadramento de câmera.

Segundo a comparação informada pela equipe, o vídeo já foi avaliado em outro trabalho técnico desenvolvido com profissionais de TI e saúde, e os resultados coincidiram quanto às repetições corretas e incorretas. Essa concordância se refere ao vídeo utilizado na demonstração. A identificação bibliográfica do trabalho de referência e a comparação dos resultados devem acompanhar o relatório técnico da entrega.

## Pré-requisitos

- Bash para executar `parte1.sh`.
- Python **3.11**, disponível pelo comando `python3.11`, com suporte a ambientes virtuais (`venv`).
- Acesso à internet para instalação das dependências.
- Ambiente com interface gráfica, pois o processamento exibe o vídeo em uma janela do OpenCV.
- Vídeo de entrada em `analise_video/inputs/movies/PM_012-Camera17-30fps.mp4`.

No Apple Silicon, utilize Python nativo ARM64, conforme indicado em `requirements.txt`.

As dependências incluem MediaPipe, OpenCV, pandas, tqdm e ReportLab. O script instala essas bibliotecas automaticamente no ambiente virtual `trabalho4/.venv`.

## Como executar `parte1.sh`

A partir da raiz do repositório:

```bash
bash trabalho4/parte1.sh
```

Ou, dentro da pasta `trabalho4`:

```bash
bash parte1.sh
```

Os caminhos dos scripts, do vídeo e das saídas são definidos a partir da localização de `parte1.sh`, permitindo executá-lo a partir de outros diretórios.

O script realiza as seguintes etapas:

1. Verifica a disponibilidade do Python 3.11.
2. Cria ou reutiliza o ambiente virtual `trabalho4/.venv`.
3. Atualiza o pip e instala as dependências de `trabalho4/requirements.txt`.
4. Cria a pasta de saída, caso necessário.
5. Executa `avaliacao_video.py`, que analisa o vídeo, grava o JSON e produz o vídeo anotado.
6. Executa `gerar_relatorio.py`, utilizando o JSON gerado e consultando o FPS do mesmo vídeo de entrada para calcular os horários do relatório.

Aguarde o processamento e a geração do vídeo anotado terminarem para obter o PDF. Pressionar `q` na janela do vídeo encerra antecipadamente a geração do vídeo anotado, deixando esse arquivo incompleto.

É possível informar um arquivo alternativo de dependências como primeiro argumento:

```bash
bash trabalho4/parte1.sh /caminho/requirements.txt
```

Esse argumento altera apenas o arquivo de dependências, não o vídeo analisado.

## Resultados gerados

Os arquivos são gravados em `trabalho4/analise_video/outputs/`:

| Arquivo | Conteúdo |
| --- | --- |
| `avaliacao_sem_base.json` | Intervalos de frames, FPS e classificação de cada trecho identificado. |
| `resultado.mp4` | Vídeo com pontos corporais, ângulo e indicação de execução certa ou errada nos trechos classificados. |
| `avaliacao_sem_base.pdf` | Resumo da avaliação e tabela com início, fim e resultado dos trechos. |

Uma nova execução utiliza os mesmos nomes e substitui os resultados anteriores.

Exemplo da estrutura de uma avaliação:

```json
{
  "frame_inicio": 192,
  "frame_fim": 346,
  "fps": 30.0,
  "correto": false
}
```

No JSON, `correto: true` indica uma execução classificada como correta; `correto: false` indica uma execução classificada como incorreta. No PDF, esses resultados aparecem como **Execução correta** e **Execução a revisar**.

Os horários são calculados por `frame / FPS`, a partir do início da gravação. Por exemplo, com 30 FPS, os frames 192 a 346 correspondem a `00:00:06.400` até `00:00:11.533`. O horário final representa o último frame do trecho. Intervalos não listados não recebem classificação no relatório.

## Parâmetros da demonstração

O `parte1.sh` utiliza a seguinte configuração:

| Parâmetro | Valor | Finalidade |
| --- | --- | --- |
| `-q` | `5` | Número de divisões para definir os ângulos de referência entre os limites. |
| `-s` | `10` | Ângulo inicial de referência, em graus. |
| `-e` | `155` | Ângulo final de referência, em graus. |
| `-m` | `8` | Tolerância angular para reconhecer início e fim do movimento. |
| `-n` | `8` | Tolerância angular para reconhecer a passagem pelos ângulos de referência. |
| `-a` | `3` | Alteração angular mínima considerada no acompanhamento do movimento. |

Para analisar outro vídeo, altere a variável `VIDEO_FILE` em `parte1.sh` e revise os parâmetros conforme o exercício e o enquadramento. A medida utilizada é a orientação entre ombro e pulso na imagem; ela não equivale a uma avaliação completa das articulações ou da postura.

## Gerar somente o relatório PDF

Se o JSON já estiver disponível, não é necessário processar o vídeo novamente. A partir da raiz do repositório, após preparar o ambiente com `parte1.sh`:

```bash
trabalho4/.venv/bin/python trabalho4/analise_video/gerar_relatorio.py \
  --json trabalho4/analise_video/outputs/avaliacao_sem_base.json \
  --video trabalho4/analise_video/inputs/movies/PM_012-Camera17-30fps.mp4
```

Para gerar um PDF para cada JSON da pasta padrão, informando o FPS real dos vídeos:

```bash
trabalho4/.venv/bin/python trabalho4/analise_video/gerar_relatorio.py --fps 30
```

Use uma mesma taxa em lote apenas quando ela corresponder a todos os vídeos de origem. Mais opções estão no [README da análise de vídeo](analise_video/README.md).

## Roteiro sugerido para a apresentação

1. Apresentar o exercício, o vídeo utilizado e o critério esperado de execução.
2. Mostrar a execução de `parte1.sh` e explicar a identificação dos pontos corporais com MediaPipe.
3. Exibir no vídeo anotado exemplos de repetições corretas e incorretas.
4. Comparar as classificações com o trabalho técnico de referência.
5. Abrir o PDF e mostrar como os horários permitem localizar os movimentos que precisam de revisão.

A parte 1 demonstra a análise de vídeo. As entregas de áudio, integração multimodal, serviços em nuvem e alertas descritas no desafio completo devem ser documentadas nas respectivas etapas do trabalho.
