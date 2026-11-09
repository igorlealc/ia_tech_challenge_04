import pandas as pd

def retornar_dados(caminho) -> pd.DataFrame:
    return pd.read_json(caminho, orient="records")