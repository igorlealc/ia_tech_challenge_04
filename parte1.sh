#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VIDEO_FILE="$SCRIPT_DIR/analise_video/inputs/movies/PM_012-Camera17-30fps.mp4"
OUTPUT_DIR="$SCRIPT_DIR/analise_video/outputs"
REQUIREMENTS_FILE="${1:-$SCRIPT_DIR/requirements.txt}"

if ! command -v python3.11 >/dev/null 2>&1; then
    echo "Erro: python3.11 não foi encontrado no PATH." >&2
    exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Criando ambiente virtual em: $VENV_DIR"
    python3.11 -m venv "$VENV_DIR"
else
    echo "Ambiente virtual já existe em: $VENV_DIR"
fi

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    echo "Erro: arquivo de dependências não encontrado: $REQUIREMENTS_FILE" >&2
    echo "Crie requirements.txt ao lado deste script." >&2
    exit 1
fi

source "$VENV_DIR/bin/activate"

echo "Atualizando dependências de: $REQUIREMENTS_FILE"
python -m pip install --upgrade pip
python -m pip install -r "$REQUIREMENTS_FILE"


mkdir -p "$OUTPUT_DIR"

python "$SCRIPT_DIR/analise_video/avaliacao_video.py" \
 -v "$VIDEO_FILE" \
 -o "$OUTPUT_DIR" \
 -q 5 \
 -s 10 \
 -e 140 \
 -m 8 \
 -n 5 \
 -a 1

echo "Gerando relatório PDF da avaliação..."
python "$SCRIPT_DIR/analise_video/gerar_relatorio.py" \
 --json "$OUTPUT_DIR/avaliacao.json" \
 --video "$VIDEO_FILE"
