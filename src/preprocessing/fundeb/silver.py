"""Silver layer: semantic rename and light quality checks for FUNDEB NSE."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.fundeb.schemas import ANOS_FUNDEB
from src.preprocessing.fundeb.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = "nse_entes_federados"

COLUMN_MAP = {
    "NU_ANO_AVALIACAO": "ano",
    "Código do Ente": "codigo_ente",
    "Nome do Ente": "nome_ente",
    "Sigla UF": "sigla_uf",
    "Valor do Nível Socioeconômico": "valor_nse",
    "Ponderador do NSE entre 0,95 e 1,05": "ponderador_nse",
}


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def transform_nse(bronze: pd.DataFrame, silver_ts) -> pd.DataFrame:
    faltando = [c for c in COLUMN_MAP if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"{ENTITY}: colunas ausentes na Bronze: {faltando}")

    df = bronze.rename(columns=COLUMN_MAP)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["codigo_ente"] = pd.to_numeric(df["codigo_ente"], errors="coerce").astype("Int64")
    df["nome_ente"] = df["nome_ente"].astype("string").str.strip()
    df["sigla_uf"] = df["sigla_uf"].astype("string").str.strip().str.upper()
    df["valor_nse"] = pd.to_numeric(df["valor_nse"], errors="coerce")
    df["ponderador_nse"] = pd.to_numeric(df["ponderador_nse"], errors="coerce")

    df = df.loc[df["ano"].isin(ANOS_FUNDEB)].copy()
    cols = [
        "ano",
        "codigo_ente",
        "nome_ente",
        "sigla_uf",
        "valor_nse",
        "ponderador_nse",
    ]
    return add_metadata(df[cols], silver_ts)


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver FUNDEB...")
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)
    logger.info("SILVER_DATA_DIR : {}", SILVER_DATA_DIR)

    bronze = read_parquet(BRONZE_DATA_DIR / ENTITY)
    silver = transform_nse(bronze, silver_ts)
    write_parquet_partitioned(
        silver, SILVER_DATA_DIR / ENTITY, "ano", overwrite_entity=True
    )
    logger.info("{} gravada. Total: {:,}", ENTITY, len(silver))

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver FUNDEB validada com sucesso.")


if __name__ == "__main__":
    run_silver()
