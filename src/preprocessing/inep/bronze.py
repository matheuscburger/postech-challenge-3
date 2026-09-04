"""Bronze layer: structural contract + Parquet conversion."""

from __future__ import annotations

from datetime import UTC, datetime
import shutil

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, RAW_DATA_DIR
from src.config import ANOS
from src.preprocessing.inep.schemas import CSV_JOBS, XLSX_JOBS
from src.preprocessing.io import (
    apply_schema,
    list_partition_values,
    read_parquet,
    write_parquet_partitioned,
)

CSV_OPTS = {
    "sep": ";",
    "encoding": "ISO-8859-1",
    "dtype": str,
    "low_memory": False,
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _checar_anos(entidade: str, partition_col: str) -> None:
    presentes = list_partition_values(BRONZE_DATA_DIR / entidade, partition_col)
    faltando = set(ANOS) - presentes
    if faltando:
        raise ValueError(
            f"{entidade}: anos esperados ausentes -> {sorted(faltando)} "
            f"(presentes: {sorted(presentes)})"
        )
    logger.info("{}: anos OK -> {}", entidade, sorted(presentes))


def _checar_aluno() -> None:
    df = read_parquet(BRONZE_DATA_DIR / "ts_aluno")
    prof_nula = int(df["VL_PROFICIENCIA_LP"].isna().sum())
    viol = int(((df["IN_PRESENCA_LP"] == 0) & df["VL_PROFICIENCIA_LP"].notna()).sum())
    logger.info("ts_aluno: proficiência nula = {:,}", prof_nula)
    if viol == 0:
        logger.info("ts_aluno: invariante ausente=>sem-nota OK (0 violações)")
    else:
        logger.warning("ts_aluno: {:,} aluno(s) ausente(s) COM proficiência (anomalia)", viol)


def bronze_csv(entidade: str, arquivo: str, schema: list[tuple[str, str]], ingestion_ts) -> None:
    dest = BRONZE_DATA_DIR / entidade
    if dest.exists():
        shutil.rmtree(dest)

    nomes = [n for n, _ in schema]
    for ano in ANOS:
        caminho = RAW_DATA_DIR / str(ano) / arquivo
        if not caminho.exists():
            raise FileNotFoundError(f"{arquivo} ({ano}) não encontrado: {caminho}")
        
        # Leitura em chunks (blocos de 200 mil linhas) para economizar memória RAM
        chunk_size = 200_000
        processados = []
        
        for raw_chunk in pd.read_csv(caminho, chunksize=chunk_size, **CSV_OPTS):
            raw_chunk = _normalize_columns(raw_chunk)
            faltando = [n for n in nomes if n not in raw_chunk.columns]
            if faltando:
                raise AssertionError(f"{arquivo} ({ano}) sem colunas do contrato: {faltando}")
            
            df_chunk = apply_schema(raw_chunk, schema)
            df_chunk["_source_file"] = str(caminho)
            df_chunk["_ingestion_timestamp"] = ingestion_ts
            processados.append(df_chunk)
        
        # Concatena os blocos já limpos e estruturados
        df = pd.concat(processados, ignore_index=True)
        write_parquet_partitioned(df, dest, "NU_ANO_AVALIACAO")
        logger.info("{} {}: {:,} linhas", entidade, ano, len(df))
        del df, processados


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

    # Spark dataAddress='sheet'!A2 with header=true -> skip title row.
    try:
        raw = pd.read_excel(caminho, sheet_name=sheet, skiprows=1, dtype=str)
    except ValueError as exc:
        abas = pd.ExcelFile(caminho).sheet_names
        raise ValueError(f"{arquivo}: aba '{sheet}' não encontrada. Abas: {abas}") from exc
    raw = _normalize_columns(raw)
    df = apply_schema(raw, schema)
    df["_source_file"] = str(caminho)
    df["_ingestion_timestamp"] = ingestion_ts
    df = df.rename(columns={"ANO": "NU_ANO_AVALIACAO"})
    df = df[df["NU_ANO_AVALIACAO"].notna()]
    write_parquet_partitioned(df, BRONZE_DATA_DIR / entidade, "NU_ANO_AVALIACAO")
    logger.info("{} {}: {:,} linhas", entidade, ano, len(df))


def run_bronze() -> None:
    ingestion_ts = datetime.now(UTC)
    BRONZE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Bronze...")
    logger.info("RAW_DATA_DIR    : {}", RAW_DATA_DIR)
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)

    logger.info("Ingerindo CSVs para a Bronze...")
    for entidade, arquivo, schema in CSV_JOBS:
        bronze_csv(entidade, arquivo, schema, ingestion_ts)

    for entidade in ("ts_aluno", "ts_municipio", "ts_estado"):
        _checar_anos(entidade, "NU_ANO_AVALIACAO")
        n = sum(1 for _ in (BRONZE_DATA_DIR / entidade).rglob("*.parquet"))
        logger.info("{}: {} partições parquet", entidade, n)
    _checar_aluno()

    logger.info("Ingerindo planilhas XLSX de metas para a Bronze...")
    for entidade in ("metas_municipios", "metas_ufs"):
        dest = BRONZE_DATA_DIR / entidade
        if dest.exists():
            shutil.rmtree(dest)

    for entidade, arquivo, sheet, schema, ano in XLSX_JOBS:
        bronze_xlsx(entidade, arquivo, sheet, schema, ano, ingestion_ts)

    for entidade in ("metas_municipios", "metas_ufs"):
        _checar_anos(entidade, "NU_ANO_AVALIACAO")
        df = read_parquet(BRONZE_DATA_DIR / entidade)
        logger.info("{}: {:,} linhas | {} colunas", entidade, len(df), len(df.columns))

    logger.success("Camada Bronze concluída.")
