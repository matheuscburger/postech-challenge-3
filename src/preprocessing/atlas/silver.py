"""Silver layer: tratamento e padronização do Atlas do Desenvolvimento Humano."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.atlas.bronze import bronze_nomes_municipio
from src.preprocessing.atlas.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.atlas.schemas import (
    ANO_BASE_ATLAS,
    COLUNAS_IDENTIFICACAO,
    INDICADORES,
    MUN_KEYS,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def transform(bronze: pd.DataFrame, nomes: pd.DataFrame, silver_ts) -> pd.DataFrame:
    colunas_selecionadas = list(COLUNAS_IDENTIFICACAO.keys()) + list(INDICADORES.keys())
    faltando = [c for c in colunas_selecionadas if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"atlas_desenvolvimento_humano: colunas ausentes na Bronze: {faltando}")

    df = bronze[colunas_selecionadas].copy()
    df = df.rename(columns={**COLUNAS_IDENTIFICACAO, **INDICADORES})

    df["id_municipio"] = df["id_municipio"].astype("Int64").astype(str).str.zfill(7)
    df = df.merge(nomes, on="id_municipio", how="left")

    df = df.loc[df["ano"] == ANO_BASE_ATLAS].reset_index(drop=True)

    cols = [*MUN_KEYS, "nome_municipio", *INDICADORES.values()]
    return add_metadata(df[cols], silver_ts)


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver Atlas do Desenvolvimento Humano...")

    bronze = read_parquet(BRONZE_DATA_DIR / "atlas_municipio")
    nomes = bronze_nomes_municipio()

    silver = transform(bronze, nomes, silver_ts)
    write_parquet_partitioned(
        silver, SILVER_DATA_DIR / "atlas_desenvolvimento_humano", "ano", overwrite_entity=True
    )
    logger.info("atlas_desenvolvimento_humano: {:,} municípios", len(silver))

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver Atlas validada com sucesso.")


if __name__ == "__main__":
    run_silver()
