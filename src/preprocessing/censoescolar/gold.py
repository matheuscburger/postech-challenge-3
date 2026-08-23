"""Gold layer: business tables for Censo Escolar ATU analytics."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.censoescolar.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.censoescolar.schemas import (
    ANOS_CENSO,
    METRIC_COLS,
    MUN_KEYS,
    UF_KEYS,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

REGIOES = frozenset(
    {"Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste", "Centro Oeste"}
)


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def _tipo_geografia(unidade: pd.Series) -> pd.Series:
    nome = unidade.astype("string").str.strip()
    out = pd.Series("uf", index=unidade.index, dtype="string")
    out.loc[nome.str.casefold() == "brasil"] = "brasil"
    out.loc[nome.isin(REGIOES)] = "regiao"
    out.loc[nome.isna()] = pd.NA
    return out


def _round_metrics(df: pd.DataFrame) -> pd.DataFrame:
    for col in METRIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(1)
    return df


def transform_uf(silver: pd.DataFrame, gold_ts) -> pd.DataFrame:
    required = [*UF_KEYS, *METRIC_COLS]
    faltando = [c for c in required if c not in silver.columns]
    if faltando:
        raise AssertionError(f"atu_brasil_regioes_ufs: colunas ausentes na Silver: {faltando}")

    df = silver.loc[silver["ano"].isin(ANOS_CENSO), required].copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df = _round_metrics(df)
    df["tipo_geografia"] = _tipo_geografia(df["unidade_geografica"])
    cols = [
        "ano",
        "tipo_geografia",
        "unidade_geografica",
        "localizacao",
        "dependencia_administrativa",
        *METRIC_COLS,
    ]
    return add_gold_metadata(df[cols], gold_ts)


def transform_municipios(silver: pd.DataFrame, gold_ts) -> pd.DataFrame:
    required = [
        "ano",
        "regiao",
        "sigla_uf",
        "id_municipio",
        "nome_municipio",
        "localizacao",
        "dependencia_administrativa",
        *METRIC_COLS,
    ]
    faltando = [c for c in required if c not in silver.columns]
    if faltando:
        raise AssertionError(f"atu_municipios: colunas ausentes na Silver: {faltando}")

    df = silver.loc[silver["ano"].isin(ANOS_CENSO), required].copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip().str.zfill(7)
    df = _round_metrics(df)
    return add_gold_metadata(df[required], gold_ts)


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold Censo Escolar (ATU)...")
    logger.info("SILVER_DATA_DIR    : {}", SILVER_DATA_DIR)
    logger.info("PROCESSED_DATA_DIR : {}", PROCESSED_DATA_DIR)

    uf = transform_uf(read_parquet(SILVER_DATA_DIR / "atu_brasil_regioes_ufs"), gold_ts)
    write_parquet_partitioned(
        uf, PROCESSED_DATA_DIR / "atu_brasil_regioes_ufs", "ano", overwrite_entity=True
    )
    logger.info("atu_brasil_regioes_ufs gravada. Total: {:,}", len(uf))

    mun = transform_municipios(read_parquet(SILVER_DATA_DIR / "atu_municipios"), gold_ts)
    write_parquet_partitioned(
        mun, PROCESSED_DATA_DIR / "atu_municipios", "ano", overwrite_entity=True
    )
    logger.info("atu_municipios gravada. Total: {:,}", len(mun))

    for tabela, checks in CHECKS_GOLD.items():
        df = read_parquet(PROCESSED_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "GOLD")
        del df

    logger.success("Camada Gold Censo Escolar validada com sucesso.")


if __name__ == "__main__":
    run_gold()
