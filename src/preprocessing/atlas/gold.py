"""Gold layer: tabela de indicadores municipais do Atlas do Desenvolvimento Humano.

Esta é uma tabela gold "standalone" (indicadores por município, ano-base
2010). A junção com a base de alunos (aluno_contexto) acontece em
src/preprocessing/join.py, não aqui — mantendo a camada gold de cada fonte
independente e auditável isoladamente, no mesmo padrão de inep/gold.py,
fundeb/gold.py e censoescolar/gold.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.atlas.schemas import COLUNAS_GOLD, MUN_KEYS
from src.preprocessing.io import read_parquet, write_parquet_partitioned


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold Atlas do Desenvolvimento Humano...")

    silver = read_parquet(SILVER_DATA_DIR / "atlas_desenvolvimento_humano")
    cols = [*MUN_KEYS, "nome_municipio", *COLUNAS_GOLD]
    gold = add_gold_metadata(silver[cols], gold_ts)

    write_parquet_partitioned(
        gold, PROCESSED_DATA_DIR / "atlas_desenvolvimento_humano", "ano", overwrite_entity=True
    )
    logger.info("atlas_desenvolvimento_humano (gold): {:,} municípios", len(gold))
    logger.success("Camada Gold Atlas concluída.")


if __name__ == "__main__":
    run_gold()
