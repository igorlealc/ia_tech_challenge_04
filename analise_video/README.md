# Relatório da avaliação de vídeo

`gerar_relatorio.py` atende à geração de relatórios automáticos do item 1
(Análise de Vídeo) do Tech Challenge, usando as classificações de
`avaliacao_video.py`.

Instale a dependência:

```bash
python3 -m pip install 'reportlab>=4.0,<5'
```

Gere um PDF para **cada JSON atualmente presente em `outputs`**, informando o
FPS real dos vídeos (30 é um exemplo):

```bash
python3 trabalho4/analise_video/gerar_relatorio.py --fps 30
```

A pasta padrão é relativa ao script, independentemente do diretório de execução.
Cada PDF recebe o nome do JSON, na mesma pasta, e é substituído ao executar
novamente. Arquivos que não terminam em `.json` são ignorados. A leitura não é
recursiva. Um JSON inválido é informado no terminal; os demais são processados,
e o comando termina com código 1 se houver erros.

Para consultar automaticamente o FPS do vídeo de origem, use `--video`
(requer OpenCV, já listado em `trabalho4/requirements.txt`):

```bash
python3 trabalho4/analise_video/gerar_relatorio.py \
  --json trabalho4/analise_video/outputs/avaliacao_sem_base.json \
  --video trabalho4/analise_video/inputs/movies/PM_012-Camera17-30fps.mp4
```

Informe o vídeo que realmente originou a avaliação. Para escolher outras pastas:

```bash
python3 trabalho4/analise_video/gerar_relatorio.py \
  --input-dir caminho/avaliacoes --output-dir caminho/relatorios --fps 30
```

`--output caminho/relatorio.pdf` permite escolher o nome de saída quando usado
com `--json`, sem `--output-dir`.

O JSON aceita uma lista de objetos ou um único objeto:

```json
[
  {"frame_inicio": 192, "frame_fim": 346, "correto": false},
  {"frame_inicio": 372, "frame_fim": 517, "correto": true}
]
```

Também aceita `fps` em cada objeto. A prioridade é `--fps`, depois `--video`,
depois o campo `fps`. Sem uma dessas fontes, o script informa erro para evitar
horários incorretos. Em lote, `--fps` ou `--video` aplica a mesma taxa a todos os
JSONs; para vídeos com taxas diferentes, processe separadamente ou inclua FPS
em cada objeto.

O PDF contém resumo, percentual por quantidade de trechos e tabela cronológica
com tempo inicial, tempo final e resultado, destacando as execuções a revisar.
Os textos são voltados a pacientes e fisioterapeutas, sem detalhes técnicos de
JSON, frames ou FPS no PDF.
Usa `tempo = frame / fps`, no formato `HH:MM:SS.mmm`. Os frames começam em zero
e os limites são inclusivos, conforme o avaliador: o tempo final é o instante
do último frame, não o instante seguinte. A 30 FPS, os frames 192–346
correspondem a `00:00:06.400`–`00:00:11.533`.

Listas vazias geram um PDF sem avaliações. Tabelas extensas continuam em outras
páginas com cabeçalho repetido. O relatório reproduz as classificações do JSON;
não infere causas ou gravidade de falhas nem classifica intervalos ausentes.
