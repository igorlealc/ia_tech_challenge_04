"""Baixa e extrai os sinais da lista existente de casos, sem refazer o sorteio."""

import argparse
import gzip
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import vitaldb
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from casos import baixar_caso

PASTA_PADRAO = Path(__file__).resolve().parent / "vitaldb_50"
SINAIS = {
    "Solar8000/HR": "frequencia_cardiaca_bpm",
    "Solar8000/PLETH_SPO2": "spo2_percentual",
    "Solar8000/ART_MBP": "pressao_media_invasiva_mmhg",
    "Solar8000/NIBP_MBP": "pressao_media_nao_invasiva_mmhg",
}


def ler_casos(caminho: Path) -> list[int]:
    tabela = pd.read_csv(caminho, dtype=str)
    if "caseid" not in tabela or tabela.empty:
        raise ValueError("O CSV precisa conter a coluna caseid e pelo menos um caso.")
    ids = tabela["caseid"]
    if not ids.str.fullmatch(r"[0-9]+").fillna(False).all():
        raise ValueError("caseid deve conter somente identificadores inteiros positivos.")
    casos = [int(valor) for valor in ids]
    if any(valor <= 0 for valor in casos) or len(set(casos)) != len(casos):
        raise ValueError("Os identificadores devem ser positivos e não podem se repetir.")
    return casos


def validar_vital(arquivo: Path) -> None:
    # O leitor VitalDB pode tolerar arquivos truncados; valide também o gzip.
    with gzip.open(arquivo, "rb") as entrada:
        if entrada.read(4) != b"VITA":
            raise ValueError(f"Cabeçalho Vital inválido: {arquivo}")
        while entrada.read(1024 * 1024):
            pass


def extrair_sinais(arquivo: Path, caseid: int, intervalo: float) -> pd.DataFrame:
    validar_vital(arquivo)
    vf = vitaldb.VitalFile(str(arquivo), track_names=list(SINAIS))
    disponiveis = set(vf.get_track_names())
    obrigatorios = {"Solar8000/HR", "Solar8000/PLETH_SPO2"}
    pressoes = {"Solar8000/ART_MBP", "Solar8000/NIBP_MBP"}
    if not obrigatorios <= disponiveis or not pressoes & disponiveis:
        raise ValueError(f"Caso {caseid}: faltam HR, SpO₂ ou ambas as pressões médias.")
    if not math.isfinite(vf.dtend - vf.dtstart) or vf.dtend <= vf.dtstart:
        raise ValueError(f"Caso {caseid}: duração inválida.")
    selecionados = [sinal for sinal in SINAIS if sinal in disponiveis]
    df = vf.to_pandas(selecionados, interval=intervalo)
    if df.empty or df.dropna(how="all").empty:
        raise ValueError(f"Caso {caseid}: nenhuma amostra disponível.")
    # Mantém o mesmo esquema mesmo quando uma das pressões não foi registrada.
    df = df.reindex(columns=list(SINAIS)).rename(columns=SINAIS)
    df.insert(0, "tempo_s", np.arange(len(df), dtype=float) * intervalo)
    df.insert(0, "caseid", caseid)
    return df


def salvar_parquet(df: pd.DataFrame, destino: Path) -> None:
    temporario = destino.with_suffix(".parquet.part")
    try:
        df.to_parquet(temporario, engine="pyarrow", compression="snappy", index=False)
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casos", type=Path, default=PASTA_PADRAO / "casos_selecionados.csv")
    parser.add_argument("--pasta-vital", type=Path, default=PASTA_PADRAO)
    parser.add_argument("--saida", type=Path, default=PASTA_PADRAO / "sinais")
    parser.add_argument("--intervalo", type=float, default=1.0, help="Intervalo da grade em segundos (padrão: 1).")
    parser.add_argument("--limite", type=int, help="Processa somente os primeiros N casos da lista, para teste.")
    args = parser.parse_args()
    if not math.isfinite(args.intervalo) or args.intervalo <= 0:
        parser.error("--intervalo deve ser finito e maior que zero")
    if args.limite is not None and args.limite <= 0:
        parser.error("--limite deve ser maior que zero")
    try:
        casos = ler_casos(args.casos)
    except (OSError, ValueError) as erro:
        parser.error(str(erro))
    if args.limite is not None:
        casos = casos[:args.limite]
    args.pasta_vital.mkdir(parents=True, exist_ok=True)
    args.saida.mkdir(parents=True, exist_ok=True)
    falhas = []
    with requests.Session() as sessao:
        sessao.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504)
        )))
        for indice, caseid in enumerate(casos, start=1):
            arquivo = args.pasta_vital / f"caso_{caseid:04d}.vital"
            destino = args.saida / f"caso_{caseid:04d}.parquet"
            try:
                if not arquivo.exists() or arquivo.stat().st_size == 0:
                    print(f"{indice}/{len(casos)} baixando caso {caseid}...", flush=True)
                    baixar_caso(sessao, caseid, arquivo)
                else:
                    print(f"{indice}/{len(casos)} usando {arquivo}", flush=True)
                df = extrair_sinais(arquivo, caseid, args.intervalo)
                salvar_parquet(df, destino)
                print(f"Salvo: {destino} ({len(df)} linhas)", flush=True)
            except Exception as erro:
                # Uma falha de rede ou arquivo não impede os demais casos.
                falhas.append(caseid)
                print(f"ERRO no caso {caseid}: {erro}", flush=True)
    print(f"Concluídos: {len(casos) - len(falhas)}/{len(casos)}.", flush=True)
    if falhas:
        print(f"Casos com falha: {falhas}. Corrija a causa e execute novamente.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
