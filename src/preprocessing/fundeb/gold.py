"""Gold layer: business table for FUNDEB NSE analytics."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.fundeb.schemas import ANOS_FUNDEB
from src.preprocessing.fundeb.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = "nse_entes_federados"


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def _tipo_ente(codigo: pd.Series) -> pd.Series:
    """Classify IBGE entity codes: UF (2 digits) vs município (7 digits)."""
    out = pd.Series(pd.NA, index=codigo.index, dtype="string")
    known = codigo.notna()
    out.loc[known & (codigo < 100)] = "uf"
    out.loc[known & (codigo >= 1_000_000)] = "municipio"
    out.loc[known & out.isna()] = "outro"
    return out


def transform_nse(silver: pd.DataFrame, gold_ts) -> pd.DataFrame:
    required = [
        "ano",
        "codigo_ente",
        "nome_ente",
        "sigla_uf",
        "valor_nse",
        "ponderador_nse",
    ]
    faltando = [c for c in required if c not in silver.columns]
    if faltando:
        raise AssertionError(f"{ENTITY}: colunas ausentes na Silver: {faltando}")

    df = silver.loc[silver["ano"].isin(ANOS_FUNDEB), required].copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["codigo_ente"] = pd.to_numeric(df["codigo_ente"], errors="coerce").astype("Int64")
    df["valor_nse"] = pd.to_numeric(df["valor_nse"], errors="coerce").round(6)
    df["ponderador_nse"] = pd.to_numeric(df["ponderador_nse"], errors="coerce").round(6)
    df["tipo_ente"] = _tipo_ente(df["codigo_ente"])

    cols = [
        "ano",
        "codigo_ente",
        "tipo_ente",
        "nome_ente",
        "sigla_uf",
        "valor_nse",
        "ponderador_nse",
    ]
    return add_gold_metadata(df[cols], gold_ts)


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold FUNDEB...")
    logger.info("SILVER_DATA_DIR    : {}", SILVER_DATA_DIR)
    logger.info("PROCESSED_DATA_DIR : {}", PROCESSED_DATA_DIR)

    silver = read_parquet(SILVER_DATA_DIR / ENTITY)
    gold = transform_nse(silver, gold_ts)
    write_parquet_partitioned(
        gold, PROCESSED_DATA_DIR / ENTITY, "ano", overwrite_entity=True
    )
    logger.info("{} gravada. Total: {:,}", ENTITY, len(gold))

    for tabela, checks in CHECKS_GOLD.items():
        df = read_parquet(PROCESSED_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "GOLD")
        del df

    logger.success("Camada Gold FUNDEB validada com sucesso.")


if __name__ == "__main__":
    run_gold()
