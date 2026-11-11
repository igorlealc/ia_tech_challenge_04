import argparse
import sys
from pathlib import Path

import opensmile
import pandas as pd
import soundfile as sf


def classificar(caminho):
    categorias = {
        'cansaco': (1, 0, 0),
        'falta_ar': (0, 1, 0),
        'tosse': (0, 0, 1),
        'respiratorio': (0, 0, 1),
        'doenca_respiratoria': (0, 0, 1),
        'sem_relacao': (0, 0, 0),
    }
    for categoria, valores in categorias.items():
        if caminho.stem.startswith(f'consulta_{categoria}_'):
            return dict(zip(('cansaco', 'falta_ar', 'doenca_respiratoria'), valores))
    raise ValueError(f'Categoria desconhecida no nome do arquivo: {caminho.name}')


def listar_audios(pasta):
    audios = sorted(p for p in Path(pasta).iterdir() if p.is_file() and p.suffix.lower() == '.wav')
    if not audios:
        raise ValueError(f'Nenhum WAV encontrado em {pasta}')
    return audios


def extrair_atributos(extrator, caminho, duracao=None, incluir_rotulos=True):
    """Extrai do áudio inteiro quando duracao não é informada."""
    caminho = Path(caminho)
    if duracao is not None and duracao <= 0:
        raise ValueError('A duração dos segmentos deve ser positiva.')
    rotulos = classificar(caminho) if incluir_rotulos else {}
    with caminho.open('rb') as arquivo:
        if arquivo.read(80).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'{caminho}: ponteiro Git LFS; obtenha o WAV real antes de executar.')
    partes = []
    with sf.SoundFile(caminho) as audio:
        if not len(audio):
            raise ValueError(f'Áudio vazio: {caminho}')
        tamanho = len(audio) if duracao is None else duracao * audio.samplerate
        for parte, inicio in enumerate(range(0, len(audio), tamanho), start=1):
            sinal = audio.read(tamanho, dtype='float32', always_2d=True).mean(axis=1)
            atributos = extrator.process_signal(sinal, audio.samplerate).reset_index(drop=True)
            if len(atributos) != 1:
                raise ValueError(f'Não foi possível extrair atributos de {caminho}, parte {parte}.')
            atributos.insert(0, 'arquivo', caminho.name)
            atributos.insert(1, 'parte', parte)
            atributos.insert(2, 'inicio_s', inicio / audio.samplerate)
            atributos.insert(3, 'fim_s', (inicio + len(sinal)) / audio.samplerate)
            for coluna, valor in rotulos.items():
                atributos[coluna] = valor
            partes.append(atributos)
    return partes


def argumentos():
    parser = argparse.ArgumentParser(description='Extrair atributos com openSMILE e gerar Parquet.')
    entrada = parser.add_mutually_exclusive_group(required=True)
    entrada.add_argument('-a', '--audio', nargs='+', help='Caminhos dos arquivos WAV classificados.')
    entrada.add_argument('--pasta', help='Pasta de WAVs (sem percorrer subpastas).')
    parser.add_argument('-o', '--output', required=True, help='Caminho do arquivo Parquet.')
    parser.add_argument('--duracao', type=int, default=None, help='Opcional: segundos por segmento. Por padrão, usa o áudio inteiro.')
    args = parser.parse_args()
    if args.duracao is not None and args.duracao <= 0:
        parser.error('--duracao deve ser maior que zero.')
    return args


def main():
    args = argumentos()
    audios = listar_audios(args.pasta) if args.pasta else [Path(p) for p in args.audio]
    extrator = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.Functionals,
    )
    partes = []
    for caminho in audios:
        print(f'Processando: {caminho.name}')
        partes.extend(extrair_atributos(extrator, caminho, args.duracao))
    dados = pd.concat(partes, ignore_index=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    dados.to_parquet(args.output, engine='pyarrow', index=False)
    unidade = 'áudios inteiros' if args.duracao is None else 'segmentos'
    print(f'Parquet gerado: {args.output} ({len(dados)} {unidade})')


if __name__ == '__main__':
    sys.exit(main())
