"""Gold layer: business table for IBGE municipal population."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.ibge.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.ibge.schemas import (
    ANOS_IBGE,
    ENTIDADE_POPULACAO,
    FAIXAS_PORTE,
    GOLD_COLS,
    MEDIDA_AREA,
    SILVER_COLS,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = ENTIDADE_POPULACAO


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def _porte_municipio(populacao: pd.Series) -> pd.Series:
    """Classifica o município em faixas populacionais de baixa cardinalidade."""
    out = pd.Series(pd.NA, index=populacao.index, dtype="string")
    valores = pd.to_numeric(populacao, errors="coerce")
    conhecido = valores.notna()
    for minimo, maximo, rotulo in FAIXAS_PORTE:
        faixa = conhecido & (valores >= minimo)
        if maximo is not None:
            faixa &= valores < maximo
        out.loc[faixa] = rotulo
    return out


def _variacao_populacional(df: pd.DataFrame) -> pd.Series:
    """Variação percentual da população em relação ao ano anterior do mesmo município.

    Nula no primeiro ano da janela: não há base de comparação dentro do recorte.
    """
    ordenado = df.sort_values(["id_municipio", "ano"])
    anterior = ordenado.groupby("id_municipio")["populacao_residente"].shift(1)
    ano_anterior = ordenado.groupby("id_municipio")["ano"].shift(1)

    # Cada condição é reduzida a bool puro antes de combinar: as colunas vêm de Parquet
    # com dtypes nullable (Int64), e um NA sobrevivendo até o `&` levanta
    # "boolean value of NA is ambiguous".
    def _mascara(condicao: pd.Series) -> pd.Series:
        return condicao.fillna(False).astype(bool)

    comparavel = _mascara((ordenado["ano"] - ano_anterior) == 1) & _mascara(anterior.gt(0))
    variacao = (ordenado["populacao_residente"] / anterior - 1) * 100
    return variacao.where(comparavel).round(2).reindex(df.index)


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
    # Área fica em km² com 3 casas — é atributo estrutural do município (Censo 2022) e
    # entra aqui só como insumo: a densidade por ano é derivada na engenharia de features.
    df[MEDIDA_AREA] = pd.to_numeric(df[MEDIDA_AREA], errors="coerce").round(3)
    df["porte_municipio"] = _porte_municipio(df["populacao_residente"])
    df["variacao_populacional_pct"] = _variacao_populacional(df)

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

    for rotulo, n in gold["porte_municipio"].value_counts(dropna=False).items():
        logger.info("  porte {:>16} : {:,}", str(rotulo), n)
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
