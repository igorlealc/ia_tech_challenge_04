#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AUDIO_DIR="$SCRIPT_DIR/analise_audio"
TRAINING_DIR="$AUDIO_DIR/inputs/training"
PATIENTS_DIR="$AUDIO_DIR/inputs/patients"
OUTPUT_DIR="${PARTE2_OUTPUT:-$AUDIO_DIR/outputs}"
VENV_DIR="${PARTE2_VENV:-$SCRIPT_DIR/.venv}"
IDIOMA="en-US"
PACIENTE=""
INSTALAR=1
SEM_EMAIL=0

uso() {
    cat <<'EOF'
Uso: bash parte2.sh [--idioma en-US] [--paciente "Paciente 001"] [--sem-email] [--sem-instalar]

Extrai atributos de inputs/training, executa o notebook SVM e avalia os WAVs
de inputs/patients usando os modelos recém-exportados.

  --idioma         Idioma falado nos áudios de patients (padrão: en-US).
  --paciente       Nome/identificador; disponível quando há um único WAV em patients.
  --sem-email      Gera os relatórios sem enviar e-mail.
  --sem-instalar   Reutiliza as dependências já instaladas no ambiente virtual.
  --help           Exibe esta ajuda.

Configurações Azure/SMTP: trabalho4/.env.
Ambiente virtual: trabalho4/.venv (pode ser alterado por PARTE2_VENV).
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --idioma|--paciente)
            if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                echo "Erro: $1 exige um valor." >&2
                exit 1
            fi
            if [[ "$1" == --idioma ]]; then IDIOMA="$2"; else PACIENTE="$2"; fi
            shift 2
            ;;
        --sem-email) SEM_EMAIL=1; shift ;;
        --sem-instalar) INSTALAR=0; shift ;;
        --help|-h) uso; exit 0 ;;
        *) echo "Argumento desconhecido: $1" >&2; uso >&2; exit 1 ;;
    esac
done

shopt -s nullglob nocaseglob
TREINAMENTO=("$TRAINING_DIR"/*.wav)
PACIENTES=("$PATIENTS_DIR"/*.wav)
if [[ ${#TREINAMENTO[@]} -eq 0 || ${#PACIENTES[@]} -eq 0 ]]; then
    echo "Erro: inclua WAVs reais nas pastas inputs/training e inputs/patients." >&2
    exit 1
fi
if [[ -n "$PACIENTE" && ${#PACIENTES[@]} -ne 1 ]]; then
    echo "Erro: --paciente exige um único WAV em patients, para não atribuir a mesma identidade a consultas distintas." >&2
    exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    if [[ -d "$VENV_DIR" ]]; then
        echo "Erro: o ambiente $VENV_DIR existe, mas seu Python não funciona. Recrie-o localmente ou informe PARTE2_VENV." >&2
        exit 1
    fi
    if ! command -v python3.11 >/dev/null 2>&1; then
        echo "Erro: python3.11 não foi encontrado no PATH." >&2
        exit 1
    fi
    python3.11 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Utilize Python 3.11."'

if [[ "$INSTALAR" -eq 1 ]]; then
    "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

mkdir -p "$OUTPUT_DIR/avaliacoes"
echo "Etapa 1/3: extraindo atributos de ${#TREINAMENTO[@]} áudios de treinamento..."
"$PYTHON" "$AUDIO_DIR/extrair_atributos_audio.py" \
    --pasta "$TRAINING_DIR" \
    --output "$OUTPUT_DIR/atributos_treinamento.parquet"

echo "Etapa 2/3: treinando e exportando os três modelos SVM..."
"$PYTHON" "$AUDIO_DIR/treinar_svm_audio.py" \
    --parquet "$OUTPUT_DIR/atributos_treinamento.parquet" \
    --output "$OUTPUT_DIR/svm"

echo "Etapa 3/3: avaliando ${#PACIENTES[@]} áudio(s) de pacientes..."
STATUS=0
for audio in "${PACIENTES[@]}"; do
    nome="${audio##*/}"
    destino="$OUTPUT_DIR/avaliacoes/${nome%.*}.pdf"
    echo "Avaliando: $nome"
    AVALIACAO_ARGS=(--audio "$audio" --idioma "$IDIOMA"
        --modelos "$OUTPUT_DIR/svm/modelos"
        --env "$SCRIPT_DIR/.env" --output "$destino")
    if [[ -n "$PACIENTE" ]]; then AVALIACAO_ARGS+=(--paciente "$PACIENTE"); fi
    if [[ "$SEM_EMAIL" -eq 1 ]]; then AVALIACAO_ARGS+=(--sem-email); fi
    if "$PYTHON" "$AUDIO_DIR/avaliar_audio.py" "${AVALIACAO_ARGS[@]}"; then
        echo "Relatório concluído: $destino"
    else
        codigo=$?
        echo "Avaliação de $nome retornou código $codigo. Consulte as mensagens e os arquivos de saída." >&2
        STATUS=2
    fi
done

echo "Saídas da parte 2: $OUTPUT_DIR"
exit "$STATUS"
