"""Bronze layer: structural contract + Parquet conversion for FUNDEB NSE."""

from __future__ import annotations

from datetime import UTC, datetime
import shutil

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, RAW_DATA_DIR
from src.preprocessing.fundeb.schemas import ANOS_FUNDEB, XLSX_JOBS
from src.preprocessing.io import (
    apply_schema,
    list_partition_values,
    read_parquet,
    write_parquet_partitioned,
)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _checar_anos(entidade: str, partition_col: str) -> None:
    presentes = list_partition_values(BRONZE_DATA_DIR / entidade, partition_col)
    faltando = set(ANOS_FUNDEB) - presentes
    if faltando:
        raise ValueError(
            f"{entidade}: anos esperados ausentes -> {sorted(faltando)} "
            f"(presentes: {sorted(presentes)})"
        )
    logger.info("{}: anos OK -> {}", entidade, sorted(presentes))


def bronze_xlsx(
    entidade: str,
    arquivo: str,
    sheet: str,
    schema: list[tuple[str, str]],
    ano: int,
    ingestion_ts,
) -> None:
    caminho = RAW_DATA_DIR / str(ano) / arquivo
    if not caminho.exists():
        raise FileNotFoundError(f"{arquivo} não encontrado: {caminho}")

    try:
        raw = pd.read_excel(caminho, sheet_name=sheet, dtype=str)
    except ValueError as exc:
        abas = pd.ExcelFile(caminho).sheet_names
        raise ValueError(f"{arquivo}: aba '{sheet}' não encontrada. Abas: {abas}") from exc

    raw = _normalize_columns(raw)
    df = apply_schema(raw, schema)
    df["NU_ANO_AVALIACAO"] = ano
    df["_source_file"] = str(caminho)
    df["_ingestion_timestamp"] = ingestion_ts
    write_parquet_partitioned(df, BRONZE_DATA_DIR / entidade, "NU_ANO_AVALIACAO")
    logger.info("{} {}: {:,} linhas", entidade, ano, len(df))


def run_bronze() -> None:
    ingestion_ts = datetime.now(UTC)
    BRONZE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Bronze FUNDEB...")
    logger.info("RAW_DATA_DIR    : {}", RAW_DATA_DIR)
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)

    logger.info("Ingerindo planilhas NSE para a Bronze...")
    entidades = {job[0] for job in XLSX_JOBS}
    for entidade in entidades:
        dest = BRONZE_DATA_DIR / entidade
        if dest.exists():
            shutil.rmtree(dest)

    for entidade, arquivo, sheet, schema, ano in XLSX_JOBS:
        bronze_xlsx(entidade, arquivo, sheet, schema, ano, ingestion_ts)

    for entidade in entidades:
        _checar_anos(entidade, "NU_ANO_AVALIACAO")
        df = read_parquet(BRONZE_DATA_DIR / entidade)
        logger.info("{}: {:,} linhas | {} colunas", entidade, len(df), len(df.columns))

    logger.success("Camada Bronze FUNDEB concluída.")


if __name__ == "__main__":
    run_bronze()
