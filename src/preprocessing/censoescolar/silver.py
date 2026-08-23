"""Silver layer: semantic rename and quality checks for Censo Escolar ATU."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.censoescolar.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.censoescolar.schemas import (
    ANOS_CENSO,
    METRIC_COLS,
    METRIC_MAP,
    MUN_KEYS,
    UF_KEYS,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

UF_COLUMN_MAP = {
    "NU_ANO_CENSO": "ano",
    "UNIDGEO": "unidade_geografica",
    "NO_CATEGORIA": "localizacao",
    "NO_DEPENDENCIA": "dependencia_administrativa",
    **METRIC_MAP,
}

MUN_COLUMN_MAP = {
    "NU_ANO_CENSO": "ano",
    "NO_REGIAO": "regiao",
    "SG_UF": "sigla_uf",
    "CO_MUNICIPIO": "id_municipio",
    "NO_MUNICIPIO": "nome_municipio",
    "NO_CATEGORIA": "localizacao",
    "NO_DEPENDENCIA": "dependencia_administrativa",
    **METRIC_MAP,
}


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def _cast_metrics(df: pd.DataFrame) -> pd.DataFrame:
    for col in METRIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def transform_uf(bronze: pd.DataFrame, silver_ts) -> pd.DataFrame:
    faltando = [c for c in UF_COLUMN_MAP if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"atu_brasil_regioes_ufs: colunas ausentes na Bronze: {faltando}")

    df = bronze.rename(columns=UF_COLUMN_MAP)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["unidade_geografica"] = df["unidade_geografica"].astype("string").str.strip()
    df["localizacao"] = df["localizacao"].astype("string").str.strip().str.title()
    df["dependencia_administrativa"] = (
        df["dependencia_administrativa"].astype("string").str.strip().str.title()
    )
    df = _cast_metrics(df)
    df = df.loc[df["ano"].isin(ANOS_CENSO)].copy()
    cols = [*UF_KEYS, *METRIC_COLS]
    return add_metadata(df[cols], silver_ts)


def transform_municipios(bronze: pd.DataFrame, silver_ts) -> pd.DataFrame:
    faltando = [c for c in MUN_COLUMN_MAP if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"atu_municipios: colunas ausentes na Bronze: {faltando}")

    df = bronze.rename(columns=MUN_COLUMN_MAP)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["regiao"] = df["regiao"].astype("string").str.strip()
    df["sigla_uf"] = df["sigla_uf"].astype("string").str.strip().str.upper()
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip().str.zfill(7)
    df["nome_municipio"] = df["nome_municipio"].astype("string").str.strip()
    df["localizacao"] = df["localizacao"].astype("string").str.strip().str.title()
    df["dependencia_administrativa"] = (
        df["dependencia_administrativa"].astype("string").str.strip().str.title()
    )
    df = _cast_metrics(df)
    df = df.loc[df["ano"].isin(ANOS_CENSO) & df["id_municipio"].notna()].copy()
    cols = [
        "ano",
        "regiao",
        "sigla_uf",
        "id_municipio",
        "nome_municipio",
        "localizacao",
        "dependencia_administrativa",
        *METRIC_COLS,
    ]
    return add_metadata(df[cols], silver_ts)


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver Censo Escolar (ATU)...")
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)
    logger.info("SILVER_DATA_DIR : {}", SILVER_DATA_DIR)

    uf = transform_uf(read_parquet(BRONZE_DATA_DIR / "atu_brasil_regioes_ufs"), silver_ts)
    write_parquet_partitioned(
        uf, SILVER_DATA_DIR / "atu_brasil_regioes_ufs", "ano", overwrite_entity=True
    )
    logger.info("atu_brasil_regioes_ufs gravada. Total: {:,}", len(uf))

    mun = transform_municipios(read_parquet(BRONZE_DATA_DIR / "atu_municipios"), silver_ts)
    write_parquet_partitioned(
        mun, SILVER_DATA_DIR / "atu_municipios", "ano", overwrite_entity=True
    )
    logger.info("atu_municipios gravada. Total: {:,}", len(mun))

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver Censo Escolar validada com sucesso.")


if __name__ == "__main__":
    run_silver()
