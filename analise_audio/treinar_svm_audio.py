"""Executa o notebook SVM existente e valida os modelos exportados."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from jupyter_client import KernelManager
import nbformat
from nbclient import NotebookClient


RAIZ = Path(__file__).resolve().parent


def exibir_saidas(cell, **kwargs):
    """Mostra no terminal os prints e a representação textual das tabelas."""
    for saida in cell.get('outputs', []):
        if saida.output_type == 'stream':
            print(saida.text, end='', flush=True)
        elif saida.output_type in ('display_data', 'execute_result'):
            texto = saida.get('data', {}).get('text/plain')
            if texto:
                print(texto, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parquet', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Pasta dos modelos, métricas e notebook executado.')
    parser.add_argument('--duracao', type=int, default=120, help='Duração usada na extração dos segmentos, em segundos.')
    args = parser.parse_args()
    if not args.parquet.is_file():
        parser.error(f'Parquet não encontrado: {args.parquet}')
    if args.duracao <= 0:
        parser.error('--duracao deve ser positiva.')
    saida = args.output.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.read(RAIZ / 'treinar_svm_audio.ipynb', as_version=4)
    # A cópia executada retém os parâmetros para poder ser reexecutada no Jupyter.
    parametros = nbformat.v4.new_code_cell(
        f'RAIZ_AUDIO_CONFIG = {str(RAIZ)!r}\n'
        f'PARQUET_ENTRADA = {str(args.parquet.resolve())!r}\n'
        f'SAIDA_TREINAMENTO = {str(saida)!r}\n'
        f'DURACAO_TREINAMENTO = {args.duracao!r}\n',
        metadata={'tags': ['parameters']},
    )
    notebook.cells.insert(1, parametros)
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    nbformat.validate(notebook)
    destino = saida / 'treinamento_executado.ipynb'
    kernel = KernelManager(kernel_name='python3')
    # Usa exatamente o ambiente do script, mesmo se o kernel global apontar a outro Python.
    kernel.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']

    def progresso(cell, cell_index, **kwargs):
        if cell.cell_type == 'code':
            print(f'Executando célula {cell_index + 1}/{len(notebook.cells)} do notebook...', flush=True)

    cliente = NotebookClient(
        notebook, km=kernel, timeout=600,
        resources={'metadata': {'path': str(RAIZ)}}, on_cell_start=progresso,
        on_cell_executed=exibir_saidas,
    )
    try:
        cliente.execute()
    finally:
        nbformat.write(notebook, destino)
        if cliente.kc is not None:
            cliente.kc.stop_channels()
        if kernel.has_kernel:
            kernel.shutdown_kernel(now=True)

    pasta_modelos = saida / 'modelos'
    manifesto = json.loads((pasta_modelos / 'manifesto.json').read_text(encoding='utf-8'))
    entrada_sha = hashlib.sha256(args.parquet.read_bytes()).hexdigest()
    if manifesto['sha256_parquet'] != entrada_sha:
        raise RuntimeError('Os modelos exportados não correspondem ao Parquet informado.')
    for target in ('cansaco', 'falta_ar', 'doenca_respiratoria'):
        info = manifesto['modelos'][target]
        arquivo = pasta_modelos / info['arquivo']
        if hashlib.sha256(arquivo.read_bytes()).hexdigest() != info['sha256']:
            raise RuntimeError(f'Exportação inválida para {target}.')
        print(f'Modelo validado: {arquivo}')
    print(f'Notebook executado: {destino}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
