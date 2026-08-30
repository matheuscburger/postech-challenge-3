"""Gold layer: business table for IBGE municipal context.

Uma linha por ``(ano, id_municipio)``, com as duas medições que a API do IBGE
entrega: ``populacao_residente`` (série, agregado 6579) e ``area_km2``
(atributo estrutural do Censo 2022, replicado na janela).

A tabela guarda só medições independentes — nada calculável a partir de outra
coluna dela. ``porte_municipio`` era faixa de ``populacao_residente`` e
``variacao_populacional_pct`` era o delta dessa mesma coluna; as duas saíram e
reaparecem na Gold analítica, junto da densidade (população ÷ área).

Em 2023 o IBGE não publicou estimativa municipal: essas linhas existem, com
``area_km2`` preenchida e ``populacao_residente`` NULA. Ver ``schemas``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.ibge.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.ibge.schemas import (
    ANOS_IBGE,
    ENTIDADE_POPULACAO,
    GOLD_COLS,
    MEDIDA_AREA,
    MEDIDA_POPULACAO,
    SILVER_COLS,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = ENTIDADE_POPULACAO


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def transform_populacao(silver: pd.DataFrame, gold_ts) -> pd.DataFrame:
    faltando = [c for c in SILVER_COLS if c not in silver.columns]
    if faltando:
        raise AssertionError(f"{ENTITY}: colunas ausentes na Silver: {faltando}")

    df = silver.loc[silver["ano"].isin(ANOS_IBGE), SILVER_COLS].copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip().str.zfill(7)
    df["populacao_residente"] = (
        pd.to_numeric(df["populacao_residente"], errors="coerce").round(0).astype("Int64")
    )
    # Área em km² com 3 casas — atributo estrutural do município (Censo 2022),
    # insumo da densidade, que é derivada na engenharia de features.
    df[MEDIDA_AREA] = pd.to_numeric(df[MEDIDA_AREA], errors="coerce").round(3)

    return add_gold_metadata(df[GOLD_COLS], gold_ts)


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold IBGE...")
    logger.info("SILVER_DATA_DIR    : {}", SILVER_DATA_DIR)
    logger.info("PROCESSED_DATA_DIR : {}", PROCESSED_DATA_DIR)

    gold = transform_populacao(read_parquet(SILVER_DATA_DIR / ENTITY), gold_ts)
    write_parquet_partitioned(gold, PROCESSED_DATA_DIR / ENTITY, "ano", overwrite_entity=True)
    logger.info("{} gravada. Total: {:,}", ENTITY, len(gold))

    for ano, grupo in gold.groupby("ano", dropna=True):
        com_pop = int(grupo[MEDIDA_POPULACAO].notna().sum())
        logger.info(
            "  {}: {:,} municípios | {:,} com população | {:,} sem estimativa",
            ano,
            len(grupo),
            com_pop,
            len(grupo) - com_pop,
        )
    logger.info(
        "  área km²: min {:,.3f} | mediana {:,.1f} | max {:,.1f} | nulos {:,}",
        gold[MEDIDA_AREA].min(),
        gold[MEDIDA_AREA].median(),
        gold[MEDIDA_AREA].max(),
        int(gold[MEDIDA_AREA].isna().sum()),
    )

    for tabela, checks in CHECKS_GOLD.items():
        df = read_parquet(PROCESSED_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "GOLD")
        del df

    logger.success("Camada Gold IBGE validada com sucesso.")


if __name__ == "__main__":
    run_gold()
