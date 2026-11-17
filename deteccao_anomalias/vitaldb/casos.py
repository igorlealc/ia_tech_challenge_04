"""Seleciona casos e baixa arquivos completos pela API pública do VitalDB.

Exemplo: python deteccao_anomalias/vitaldb/casos.py --idade-minima 45 --idade-maxima 55 --sexo F --quantidade 200
Usa somente bibliotecas já declaradas em requirements.txt.
"""

import argparse
import random
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://api.vitaldb.net"
PASTA_PADRAO = Path(__file__).resolve().parent / "vitaldb_200"
SINAIS_DISPONIVEIS = {
    "pressao_invasiva": "Solar8000/ART_MBP",
    "pressao_nao_invasiva": "Solar8000/NIBP_MBP",
    "frequencia_cardiaca": "Solar8000/HR",
    "spo2": "Solar8000/PLETH_SPO2",
    "frequencia_respiratoria": "Solar8000/RR",
    "frequencia_respiratoria_co2": "Solar8000/RR_CO2",
    "temperatura": "Solar8000/BT",
    "etco2": "Solar8000/ETCO2",
}
SINAIS_PADRAO = ("pressao_invasiva",)


def ler_tabela(sessao: requests.Session, nome: str) -> pd.DataFrame:
    with sessao.get(f"{API_URL}/{nome}", timeout=(30, 180)) as resposta:
        resposta.raise_for_status()
        return pd.read_csv(StringIO(resposta.text))


def selecionar_casos(
    trilhas: pd.DataFrame,
    clinicos: pd.DataFrame,
    quantidade: int,
    semente: int,
    idade_minima: int,
    idade_maxima: int,
    sexo: str = "F",
    sinais: tuple[str, ...] | list[str] = SINAIS_PADRAO,
) -> list[int]:
    if not sinais or any(sinal not in SINAIS_DISPONIVEIS for sinal in sinais):
        raise ValueError("Informe pelo menos um sinal vital disponível.")
    def casos_com(sinal: str) -> set[int]:
        return set(trilhas.loc[trilhas["tname"] == sinal, "caseid"])

    idades = pd.to_numeric(clinicos["age"], errors="coerce")
    casos_na_faixa = set(
        clinicos.loc[
            idades.between(idade_minima, idade_maxima)
            & clinicos["sex"].eq(sexo),
            "caseid",
        ]
    )
    for sinal in sinais:
        casos_na_faixa &= casos_com(SINAIS_DISPONIVEIS[sinal])
    candidatos = sorted(casos_na_faixa)
    if len(candidatos) < quantidade:
        raise RuntimeError(
            f"Foram encontrados apenas {len(candidatos)} casos com os sinais "
            f"{', '.join(sinais)} e idade entre {idade_minima} e {idade_maxima} anos "
            f"(inclusive), sexo {sexo}; foram solicitados {quantidade}."
        )
    return random.Random(semente).sample(candidatos, quantidade)


def baixar_caso(sessao: requests.Session, caseid: int, destino: Path) -> None:
    # Só publica o arquivo final após concluir o download.
    temporario = destino.with_suffix(".vital.part")
    try:
        with sessao.get(
            f"{API_URL}/{caseid}.vital", stream=True, timeout=(30, 180)
        ) as resposta:
            resposta.raise_for_status()
            with temporario.open("wb") as arquivo:
                for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                    arquivo.write(bloco)
        if temporario.stat().st_size == 0:
            raise RuntimeError(f"O download do caso {caseid} retornou um arquivo vazio.")
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quantidade", type=int, default=200,
                        help="Número de casos a selecionar (padrão: 200).")
    parser.add_argument("--idade-minima", type=int, default=45,
                        help="Idade mínima em anos, inclusive (padrão: 45).")
    parser.add_argument("--idade-maxima", type=int, default=55,
                        help="Idade máxima em anos, inclusive (padrão: 55).")
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--sexo", type=str.upper, choices=("F", "M"), default="F",
                        help="Sexo registrado: F (feminino) ou M (masculino); padrão: F.")
    parser.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    parser.add_argument(
        "--sinais", nargs="+", choices=tuple(SINAIS_DISPONIVEIS),
        default=SINAIS_PADRAO,
        help="Exige todas as trilhas informadas (padrão: apenas pressao_invasiva).",
    )
    parser.add_argument(
        "--somente-lista", action="store_true",
        help="Salva a seleção e a tabela clínica sem baixar os arquivos .vital.",
    )
    args = parser.parse_args()
    if args.quantidade < 1:
        parser.error("--quantidade deve ser maior que zero")

    if args.idade_minima < 0 or args.idade_maxima < 0:
        parser.error("as idades devem ser maiores ou iguais a zero")
    if args.idade_minima > args.idade_maxima:
        parser.error("--idade-minima não pode superar --idade-maxima")

    args.pasta.mkdir(parents=True, exist_ok=True)
    with requests.Session() as sessao:
        sessao.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504)
        )))
        print("Consultando os sinais disponíveis no VitalDB...", flush=True)
        trilhas = ler_tabela(sessao, "trks")
        clinicos = ler_tabela(sessao, "cases")
        casos = selecionar_casos(
            trilhas, clinicos, args.quantidade, args.semente,
            args.idade_minima, args.idade_maxima, args.sexo, args.sinais,
        )
        clinicos = clinicos.loc[clinicos["caseid"].isin(casos)]
        pd.DataFrame({"caseid": casos}).to_csv(
            args.pasta / "casos_selecionados.csv", index=False
        )
        clinicos.to_csv(args.pasta / f"clinical_data_{args.quantidade}.csv", index=False)
        print(f"{len(casos)} casos selecionados. CSVs salvos em {args.pasta}", flush=True)
        if args.somente_lista:
            return
        for i, caseid in enumerate(casos, start=1):
            destino = args.pasta / f"caso_{caseid:04d}.vital"
            if destino.exists() and destino.stat().st_size > 0:
                print(f"{i}/{len(casos)} já existe: {destino}", flush=True)
                continue
            print(f"{i}/{len(casos)} baixando caso {caseid}...", flush=True)
            baixar_caso(sessao, caseid, destino)
            print(f"{i}/{len(casos)} salvo: {destino}", flush=True)


if __name__ == "__main__":
    main()
