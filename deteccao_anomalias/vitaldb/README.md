# Seleção de casos e extração de sinais do VitalDB

Os scripts desta pasta preparam os dados para a análise de anomalias. O [casos.py](casos.py) seleciona casos cirúrgicos por faixa etária, sexo registrado e disponibilidade de sinais. O [baixar_sinais.py](baixar_sinais.py) usa a lista selecionada para baixar os arquivos completos que faltam e exportar os sinais em Parquet. Eles não treinam modelos nem classificam anomalias.

## Preparação

Use Python 3.11 e as dependências de [requirements.txt](../../requirements.txt). Os exemplos abaixo devem ser executados a partir de `trabalho4`, com o ambiente virtual ativado:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows, ative com `.venv\Scripts\activate`. A seleção e os downloads precisam de acesso à internet. A extração pode usar arquivos `.vital` já disponíveis localmente.

## Fluxo recomendado para 200 casos do sexo feminino entre 45 e 55 anos

Primeiro, gere os metadados e a lista de casos. Neste fluxo, exigimos também frequência cardíaca e SpO₂ para atender ao extrator atual:

```bash
python deteccao_anomalias/vitaldb/casos.py \
  --idade-minima 45 \
  --idade-maxima 55 \
  --sexo F \
  --sinais pressao_invasiva frequencia_cardiaca spo2 \
  --quantidade 200 \
  --pasta deteccao_anomalias/vitaldb/vitaldb_200 \
  --somente-lista
```

Depois, baixe os arquivos completos e extraia os sinais dessa seleção:

```bash
python deteccao_anomalias/vitaldb/baixar_sinais.py \
  --casos deteccao_anomalias/vitaldb/vitaldb_200/casos_selecionados.csv \
  --pasta-vital deteccao_anomalias/vitaldb/vitaldb_200 \
  --saida deteccao_anomalias/vitaldb/vitaldb_200/sinais
```

**Os padrões de pasta dos scripts são diferentes:** `casos.py` usa `vitaldb_200`; `baixar_sinais.py` ainda usa `vitaldb_50`. Passe as três opções de caminho no segundo comando para trabalhar com a nova seleção. Alterar apenas `--casos` não altera automaticamente `--pasta-vital` ou `--saida`.

Para testar a extração de apenas dois casos, acrescente `--limite 2` ao segundo comando. Depois, execute sem essa opção para processar a lista inteira.

## casos.py

Consulta as tabelas `trks` e `cases` da API pública em `https://api.vitaldb.net`. Filtra a idade com os dois limites inclusivos, seleciona o sexo registrado em `sex` e exige as trilhas escolhidas em `--sinais`.

O padrão exige **somente pressão arterial média invasiva**. Frequência cardíaca e SpO₂ não são obrigatórias na seleção padrão. Ao informar vários sinais, o caso precisa conter **todos** eles; a lista substitui o padrão. Informar as duas pressões exige ambas, e não uma ou outra.

| Opção de `--sinais` | Trilha exigida | Significado |
| --- | --- | --- |
| `pressao_invasiva` | `Solar8000/ART_MBP` | Pressão arterial média invasiva. |
| `pressao_nao_invasiva` | `Solar8000/NIBP_MBP` | Pressão arterial média não invasiva. |
| `frequencia_cardiaca` | `Solar8000/HR` | Frequência cardíaca. |
| `spo2` | `Solar8000/PLETH_SPO2` | Saturação periférica de oxigênio. |
| `frequencia_respiratoria` | `Solar8000/RR` | Frequência respiratória do monitor. |
| `frequencia_respiratoria_co2` | `Solar8000/RR_CO2` | Frequência respiratória por capnografia. |
| `temperatura` | `Solar8000/BT` | Temperatura corporal. |
| `etco2` | `Solar8000/ETCO2` | CO₂ ao final da expiração. |

O filtro verifica a presença da trilha no índice da API, não a cobertura de valores preenchidos nem a qualidade das medições. Os arquivos baixados continuam sendo os `.vital` completos.

Idades ausentes ou não numéricas são excluídas. Registros com sexo ausente ou diferente do solicitado também são excluídos. O script ordena os identificadores elegíveis e sorteia a quantidade pedida sem repetição, usando a semente informada. A quantidade representa **casos cirúrgicos**, não necessariamente pacientes distintos; `subjectid` identifica o paciente na tabela clínica.

Se houver menos candidatos que o solicitado, o script informa a quantidade disponível e encerra antes de escrever os CSVs. A existência das trilhas não garante medições válidas e simultâneas em todos os instantes.

| Argumento | Padrão | Descrição |
| --- | --- | --- |
| `--idade-minima` | `45` | Idade mínima inclusiva, em anos; inteiro não negativo. |
| `--idade-maxima` | `55` | Idade máxima inclusiva; inteiro não negativo e maior ou igual à mínima. |
| `--quantidade` | `200` | Número inteiro de casos, maior que zero. |
| `--sexo` | `F` | Sexo registrado: `F` (feminino) ou `M` (masculino). Aceita também `f` e `m`. |
| `--sinais` | `pressao_invasiva` | Um ou mais nomes da tabela acima, separados por espaços; todos são obrigatórios. |
| `--semente` | `42` | Semente do sorteio reproduzível. |
| `--pasta` | `vitaldb_200`, ao lado do script | Diretório dos CSVs e arquivos completos. |
| `--somente-lista` | Desativado | Grava os CSVs sem baixar arquivos `.vital`. |
| `--help` | — | Exibe a ajuda. |

Sem argumentos, seleciona 200 casos do sexo feminino entre 45 e 55 anos com pressão arterial média invasiva, salva os CSVs e baixa os arquivos completos:

```bash
python deteccao_anomalias/vitaldb/casos.py
```

Para selecionar casos do sexo masculino com outra faixa e quantidade:

```bash
python deteccao_anomalias/vitaldb/casos.py \
  --idade-minima 40 --idade-maxima 60 --sexo M --quantidade 100 \
  --pasta deteccao_anomalias/vitaldb/vitaldb_100
```

A pasta padrão não muda quando `--quantidade` muda. Use `--pasta` para separar experimentos.

Para selecionar somente pela disponibilidade de SpO₂ e frequência respiratória, mantendo os padrões de idade, sexo e quantidade:

```bash
python deteccao_anomalias/vitaldb/casos.py \
  --sinais spo2 frequencia_respiratoria \
  --pasta deteccao_anomalias/vitaldb/vitaldb_respiratorio \
  --somente-lista
```

### Saídas e reexecução

| Arquivo | Conteúdo |
| --- | --- |
| `casos_selecionados.csv` | Coluna `caseid`, na ordem do sorteio. |
| `clinical_data_<quantidade>.csv` | Tabela clínica dos casos selecionados; no padrão, `clinical_data_200.csv`. |
| `caso_XXXX.vital` | Arquivo completo do caso, com pelo menos quatro dígitos no nome. |

A tabela clínica mantém a ordem recebida da API; relacione-a à lista por `caseid`, não pelo número da linha. Ela contém metadados, não as séries temporais.

Cada execução consulta a API e refaz o sorteio. A seleção se repete com a mesma semente e o mesmo conjunto ordenado de candidatos; mudanças na fonte podem alterar o resultado. Preserve o CSV da seleção para registrar o experimento.

Os CSVs correspondentes à execução são sobrescritos. Arquivos `.vital` existentes e não vazios são reutilizados sem validação de integridade neste script. Se um download falhar, a execução encerra; os arquivos já concluídos permanecem no disco. Uma quantidade diferente na mesma pasta pode deixar tabelas clínicas antigas.

## baixar_sinais.py

**Compatibilidade:** este extrator ainda exige HR, SpO₂ e pelo menos uma pressão média. Ele exporta apenas esses sinais, independentemente das opções usadas em `casos.py`. Uma seleção apenas com pressão invasiva pode incluir casos que falham nessa validação. Para usar os dois scripts juntos, selecione explicitamente `--sinais pressao_invasiva frequencia_cardiaca spo2` (ou substitua a pressão pela não invasiva). Temperatura, frequência respiratória e EtCO₂ não são exportados pelo extrator atual.

Lê `casos_selecionados.csv` sem refazer o sorteio ou aplicar novamente os filtros de idade e sexo. O CSV deve conter pelo menos um `caseid`, com identificadores inteiros positivos e sem duplicação.

Para cada caso, o script:

1. Reutiliza o `.vital` local se estiver presente e não vazio; caso contrário, baixa-o usando a função de `casos.py`.
2. Valida o cabeçalho `VITA` e lê todo o conteúdo gzip para verificar sua integridade.
3. Confere as trilhas necessárias, a duração e a presença de amostras.
4. Converte os sinais para uma grade temporal e grava um Parquet com compressão Snappy.

| Argumento | Padrão | Descrição |
| --- | --- | --- |
| `--casos` | `vitaldb_50/casos_selecionados.csv` | CSV da lista de entrada. |
| `--pasta-vital` | `vitaldb_50` | Pasta dos arquivos completos, existentes ou a baixar. |
| `--saida` | `vitaldb_50/sinais` | Pasta dos arquivos Parquet. |
| `--intervalo` | `1.0` | Intervalo da grade em segundos; finito e maior que zero. |
| `--limite` | Sem limite | Processa somente os primeiros N casos da lista; inteiro positivo. |
| `--help` | — | Exibe a ajuda. |

Os caminhos padrão são relativos à localização do script. Caminhos relativos passados em argumentos são resolvidos a partir do diretório de execução.

### Esquema dos Parquets

Cada caso gera `sinais/caso_XXXX.parquet`, com estas colunas:

| Coluna | Significado |
| --- | --- |
| `caseid` | Identificador do caso; permite relacionar os sinais à tabela clínica. |
| `tempo_s` | Posição na grade em segundos desde o início da gravação. |
| `frequencia_cardiaca_bpm` | Frequência cardíaca, em batimentos por minuto. |
| `spo2_percentual` | SpO₂, em percentual. |
| `pressao_media_invasiva_mmhg` | Pressão arterial média invasiva, em mmHg. |
| `pressao_media_nao_invasiva_mmhg` | Pressão arterial média não invasiva, em mmHg. |

A grade começa em zero e avança conforme `--intervalo`. Uma linha por segundo não implica uma nova medição por segundo. O script não interpola, não preenche lacunas com zero, não remove extremos e não combina as pressões. A coluna de uma pressão ausente no caso permanece no esquema, com valores nulos.

Os Parquets existentes são regenerados, inclusive ao alterar o intervalo. Um arquivo `.vital` local corrompido gera falha; não é baixado novamente automaticamente. Mova ou remova o arquivo inválido antes de repetir o processamento.

Uma falha em um caso não impede os demais. Ao final, o script informa o total concluído e os identificadores com falha. O código de saída é `0` quando todos os casos processados têm sucesso e `1` quando há falhas por caso; argumentos ou lista inválidos encerram antes do processamento.

## Escrita de arquivos e retomada

Os downloads e Parquets são escritos primeiro em arquivos `.part` e renomeados após a conclusão. Os temporários são removidos em falhas tratadas; uma interrupção abrupta pode deixá-los no disco. Downloads interrompidos recomeçam do início, sem retomada por byte.

Ambos os scripts usam tentativas HTTP adicionais para falhas configuradas, incluindo respostas 429, 500, 502, 503 e 504. Isso não garante recuperação de uma interrupção durante a leitura do download.

## Uso dos resultados

Exemplo de leitura e associação dos sinais aos metadados, executado em `trabalho4`:

```python
from pathlib import Path
import pandas as pd

base = Path("deteccao_anomalias/vitaldb/vitaldb_200")
casos = pd.read_csv(base / "casos_selecionados.csv")
caseid = int(casos.iloc[0]["caseid"])
sinais = pd.read_parquet(base / "sinais" / f"caso_{caseid:04d}.parquet")
clinicos = pd.read_csv(base / "clinical_data_200.csv")
dados = sinais.merge(clinicos, on="caseid", how="left", validate="many_to_one")
```

Antes de treinar um detector, avalie lacunas, qualidade dos sinais e disponibilidade por caso. Os arquivos exportados não contêm rótulos de anomalia. Preserve os `.vital` para consultar os registros originais.

Os dicionários da amostra anterior explicam os campos, mas suas contagens descrevem somente aqueles 50 casos:

- [Dicionário da tabela clínica](vitaldb_50/DICIONARIO_DADOS.md).
- [Dicionário dos sinais Parquet](vitaldb_50/DICIONARIO_SINAIS_PARQUET.md).
- [Documentação da amostra de 50 casos](vitaldb_50/README.md).
