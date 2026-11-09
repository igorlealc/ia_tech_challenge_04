import pandas as pd

def retornar_dados(caminho, query) -> pd.DataFrame:
    df = pd.read_csv(caminho, sep=";")
    print(df.columns.tolist())
    print(df.head(2))
    print(query)
    return df.query(query)