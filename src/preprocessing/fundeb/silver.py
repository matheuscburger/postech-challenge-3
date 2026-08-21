"""Silver layer: semantic rename and light quality checks for FUNDEB NSE."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.fundeb.schemas import ANOS_FUNDEB
from src.preprocessing.io import list_partition_values, read_parquet, write_parquet_partitioned

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


def _checar_anos(entidade: str) -> None:
    presentes = list_partition_values(SILVER_DATA_DIR / entidade, "ano")
    faltando = set(ANOS_FUNDEB) - presentes
    if faltando:
        raise ValueError(
            f"{entidade}: anos esperados ausentes -> {sorted(faltando)} "
            f"(presentes: {sorted(presentes)})"
        )
    logger.info("{}: anos OK -> {}", entidade, sorted(presentes))


def _checar_qualidade(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError(f"{ENTITY}: tabela Silver vazia")

    nulos_chave = int(df[["ano", "codigo_ente"]].isna().any(axis=1).sum())
    if nulos_chave:
        raise ValueError(f"{ENTITY}: {nulos_chave} linha(s) com ano/codigo_ente nulo")

    dups = int(df.duplicated(["ano", "codigo_ente"]).sum())
    if dups:
        raise ValueError(f"{ENTITY}: {dups} duplicata(s) na chave (ano, codigo_ente)")

    ponderador = pd.to_numeric(df["ponderador_nse"], errors="coerce")
    fora = int(((ponderador < 0.95) | (ponderador > 1.05)).sum())
    if fora:
        logger.warning(
            "{}: {:,} linha(s) com ponderador_nse fora de [0.95, 1.05]",
            ENTITY,
            fora,
        )
    else:
        logger.info("{}: ponderador_nse dentro de [0.95, 1.05]", ENTITY)


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

    _checar_anos(ENTITY)
    _checar_qualidade(silver)
    logger.success("Camada Silver FUNDEB validada com sucesso.")


if __name__ == "__main__":
    run_silver()
