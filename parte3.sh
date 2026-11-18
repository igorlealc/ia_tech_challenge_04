#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ANOMALIAS_DIR="$SCRIPT_DIR/deteccao_anomalias"
BASE="$ANOMALIAS_DIR/vitaldb/outputs/vitaldb_200"
REFERENCIA="$ANOMALIAS_DIR/vitaldb/outputs/vitaldb_50"
OUTPUT_DIR="$ANOMALIAS_DIR/outputs"
VENV_DIR="${PARTE3_VENV:-$SCRIPT_DIR/.venv}"
INSTALAR=1
REUTILIZAR=0
SEM_MONITOR=0
MONITOR_ARGS=()

uso() {
    cat <<'AJUDA'
Uso: bash parte3.sh [--sem-instalar] [--reutilizar-dados] [--sem-interface] [--sem-monitor]

Executa os componentes existentes, nesta ordem:
  1. Seleção de 200 casos femininos entre 45 e 55 anos, com semente 42.
  2. Download e extração dos sinais em grade de 1 segundo.
  3. Execução de uma cópia do notebook de análise de PAM.
  4. Monitor do caso 1341: início em 500 s, velocidade 3, sem agregação,
     limites demonstrativos 40, 60, 100 e 120 mmHg.

  --sem-instalar      Reutiliza as dependências do ambiente virtual.
  --reutilizar-dados  Usa a seleção e os Parquets existentes; pula etapas 1 e 2.
  --sem-interface    Executa o monitor sem janela ou espera; salva a figura.
  --sem-monitor      Encerra após a análise do notebook.
  --help, -h         Exibe esta ajuda.

Python 3.11; ambiente: trabalho4/.venv (alterável por PARTE3_VENV).
Dados: deteccao_anomalias/vitaldb/outputs/vitaldb_200.
SMTP: trabalho4/.env. O monitor mantém o envio de alerta já implementado,
inclusive no modo sem interface. Os scripts Python e o notebook original
não são alterados; somente a cópia executada recebe os caminhos de outputs.
AJUDA
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sem-instalar) INSTALAR=0; shift ;;
        --reutilizar-dados) REUTILIZAR=1; shift ;;
        --sem-interface) MONITOR_ARGS+=(--sem-interface); shift ;;
        --sem-monitor) SEM_MONITOR=1; shift ;;
        --help|-h) uso; exit 0 ;;
        *) echo "Argumento desconhecido: $1" >&2; uso >&2; exit 1 ;;
    esac
done

for arquivo in DICIONARIO_DADOS.md DICIONARIO_SINAIS_PARQUET.md; do
    if [[ ! -f "$REFERENCIA/$arquivo" ]]; then
        echo "Erro: dicionário de referência ausente: $REFERENCIA/$arquivo" >&2; exit 1
    fi
done
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    if [[ -d "$VENV_DIR" ]]; then
        echo "Erro: o Python de $VENV_DIR não funciona. Recrie o ambiente localmente ou informe PARTE3_VENV." >&2; exit 1
    fi
    if ! command -v python3.11 >/dev/null 2>&1; then
        echo "Erro: python3.11 não foi encontrado no PATH." >&2; exit 1
    fi
    python3.11 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Utilize Python 3.11."'
if [[ "$INSTALAR" -eq 1 ]]; then
    "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

if [[ "$REUTILIZAR" -eq 0 ]]; then
    echo "Etapa 1/4: selecionando 200 casos..."
    "$PYTHON" "$ANOMALIAS_DIR/vitaldb/casos.py" \
        --idade-minima 45 --idade-maxima 55 --sexo F \
        --quantidade 200 --semente 42 \
        --sinais pressao_invasiva frequencia_cardiaca spo2 \
        --pasta "$BASE" --somente-lista

    echo "Etapa 2/4: baixando arquivos faltantes e extraindo sinais..."
    "$PYTHON" "$ANOMALIAS_DIR/vitaldb/baixar_sinais.py" \
        --casos "$BASE/casos_selecionados.csv" \
        --pasta-vital "$BASE" --saida "$BASE/sinais" --intervalo 1
else
    echo "Etapas 1 e 2: reutilizando a seleção e os Parquets de $BASE."
fi

echo "Etapa 3/4: executando o notebook de análise de PAM..."
# O notebook não possui CLI. nbclient executa uma cópia no mesmo Python,
# com os caminhos de dados ajustados apenas nessa cópia, sem editar a origem.
"$PYTHON" - "$ANOMALIAS_DIR" <<'PY'
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

raiz = Path(sys.argv[1])
base = raiz / 'vitaldb/outputs/vitaldb_200'
for nome in ('casos_selecionados.csv', 'clinical_data_200.csv'):
    if not (base / nome).is_file():
        raise SystemExit(f'Erro: arquivo ausente: {base / nome}')
if not any((base / 'sinais').glob('caso_*.parquet')):
    raise SystemExit(f'Erro: nenhum Parquet em {base / "sinais"}')
notebook = nbformat.read(raiz / 'analisar_pressao_invasiva.ipynb', as_version=4)
for cell in notebook.cells:
    cell.source = cell.source.replace('vitaldb/vitaldb_200', 'vitaldb/outputs/vitaldb_200')
    cell.source = cell.source.replace('vitaldb/vitaldb_50', 'vitaldb/outputs/vitaldb_50')
    if cell.cell_type == 'code':
        cell.outputs = []
        cell.execution_count = None
notebook.cells.insert(1, nbformat.v4.new_code_cell(
    f'RAIZ_CONFIG = {str(raiz)!r}\n', metadata={'tags': ['parameters']}))
nbformat.validate(notebook)
saida = base / 'analise_exploratoria'
saida.mkdir(parents=True, exist_ok=True)
destino = saida / 'analise_executada.ipynb'
kernel = KernelManager(kernel_name='python3')
kernel.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']

def progresso(cell, cell_index, **kwargs):
    if cell.cell_type == 'code':
        print(f'Executando célula {cell_index + 1}/{len(notebook.cells)}...', flush=True)

def exibir_saidas(cell, **kwargs):
    for output in cell.get('outputs', []):
        if output.output_type == 'stream':
            print(output.text, end='', flush=True)
        elif output.output_type in ('display_data', 'execute_result'):
            texto = output.get('data', {}).get('text/plain')
            if texto:
                print(texto, flush=True)

cliente = NotebookClient(notebook, km=kernel, timeout=600,
    resources={'metadata': {'path': str(raiz)}},
    on_cell_start=progresso, on_cell_executed=exibir_saidas)
try:
    cliente.execute()
finally:
    nbformat.write(notebook, destino)
    if cliente.kc is not None:
        cliente.kc.stop_channels()
    if kernel.has_kernel:
        kernel.shutdown_kernel(now=True)
print(f'Notebook executado: {destino}')
PY

if [[ "$SEM_MONITOR" -eq 0 ]]; then
    mkdir -p "$OUTPUT_DIR"
    echo "Etapa 4/4: reproduzindo o caso 1341..."
    "$PYTHON" "$ANOMALIAS_DIR/simular_monitor_pam.py" \
        --pasta "$BASE/sinais" --caso 1341 \
        --urgente-baixa 40 --normal-min 60 --normal-max 100 --urgente-alta 120 \
        --intervalo 0 --velocidade 3 --inicio-segundos 500 \
        --saida-eventos "$OUTPUT_DIR/eventos_pam.json" \
        --saida-figura "$OUTPUT_DIR/monitor_pam.png" "${MONITOR_ARGS[@]}"
else
    echo "Etapa 4/4: monitor desativado por --sem-monitor."
fi
echo "Análise concluída: $BASE/analise_exploratoria"
