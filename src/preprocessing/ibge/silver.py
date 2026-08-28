"""Silver layer: pivot from long to wide, semantic rename and quality checks for IBGE."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.ibge.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.ibge.schemas import (
    ANO_REFERENCIA_AREA,
    ANOS_IBGE,
    COLUMN_MAP_BASE,
    ENTIDADE_AREA,
    ENTIDADE_POPULACAO,
    JOBS_POR_ENTIDADE,
    MEDIDA_AREA,
    NIVEL_MUNICIPIO,
    SILVER_COLS,
    ApiJob,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = ENTIDADE_POPULACAO


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def _separar_nome_uf(nome_localidade: pd.Series) -> tuple[pd.Series, pd.Series]:
    """A API devolve o município como 'Alta Floresta D'Oeste - RO'.

    Devolve (nome_municipio, sigla_uf). A sigla aqui é conferência: a fonte de verdade
    da UF são os dois primeiros dígitos do código IBGE, como já é feito no inep/gold.py.
    """
    texto = nome_localidade.astype("string").str.strip()
    partes = texto.str.rsplit(" - ", n=1, expand=True)
    if partes.shape[1] < 2:
        return texto, pd.Series(pd.NA, index=texto.index, dtype="string")
    nome = partes[0].astype("string").str.strip()
    sigla = partes[1].astype("string").str.strip().str.upper()
    valida = sigla.str.match(r"^[A-Z]{2}$", na=False)
    return nome.mask(~valida, texto), sigla.mask(~valida)


def pivotar(bronze: pd.DataFrame, job: ApiJob) -> pd.DataFrame:
    """Longo -> largo: uma linha por (ano, município), uma coluna por medida.

    O nome da coluna de valor vem de ``job.medida``, então cada indicador novo do IBGE
    entra como uma coluna aqui sem tocar no resto do pipeline.
    """
    mapa = {**COLUMN_MAP_BASE, "VL_MEDIDA": job.medida}
    faltando = [c for c in mapa if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"{job.entidade}: colunas ausentes na Bronze: {faltando}")

    df = bronze.loc[bronze["CO_NIVEL"].astype("string") == NIVEL_MUNICIPIO].copy()
    if df.empty:
        niveis = sorted(bronze["CO_NIVEL"].dropna().unique().tolist())
        raise AssertionError(
            f"{job.entidade}: nenhuma linha no nível {NIVEL_MUNICIPIO}. Níveis presentes: {niveis}"
        )

    df = df.rename(columns=mapa)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip().str.zfill(7)
    df[job.medida] = pd.to_numeric(df[job.medida], errors="coerce")

    nome, sigla = _separar_nome_uf(df["nome_localidade"])
    df["nome_municipio"] = nome
    df["sigla_uf"] = sigla
    df["id_uf"] = pd.to_numeric(df["id_municipio"].str.slice(0, 2), errors="coerce").astype(
        "Int64"
    )

    df = df.loc[df["ano"].isin(job.periodos) & df["id_municipio"].notna()].copy()

    duplicadas = int(df.duplicated(["ano", "id_municipio"]).sum())
    if duplicadas:
        logger.warning(
            "{}: {:,} par(es) (ano, id_municipio) duplicado(s) na Bronze; "
            "mantendo o primeiro registro de cada.",
            job.entidade,
            duplicadas,
        )
        df = df.drop_duplicates(["ano", "id_municipio"], keep="first")

    return df


def area_estrutural(bronze_area: pd.DataFrame) -> pd.DataFrame:
    """Reduz a área a um atributo do município, sem ano.

    A área só muda com alteração de limites territoriais, então o valor do Censo
    de {ANO_REFERENCIA_AREA} vale para toda a janela. Devolve (id_municipio, area_km2).
    """
    job = JOBS_POR_ENTIDADE[ENTIDADE_AREA]
    area = pivotar(bronze_area, job)[["id_municipio", MEDIDA_AREA]]
    area = area.drop_duplicates("id_municipio", keep="first")
    logger.info(
        "{}: {:,} municípios com área (referência {}).",
        ENTIDADE_AREA,
        int(area[MEDIDA_AREA].notna().sum()),
        ANO_REFERENCIA_AREA,
    )
    return area


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver IBGE...")
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)
    logger.info("SILVER_DATA_DIR : {}", SILVER_DATA_DIR)

    populacao = pivotar(
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_POPULACAO), JOBS_POR_ENTIDADE[ENTIDADE_POPULACAO]
    )
    area = area_estrutural(read_parquet(BRONZE_DATA_DIR / ENTIDADE_AREA))

    combinada = populacao.merge(area, on="id_municipio", how="left")
    sem_area = int(combinada[MEDIDA_AREA].isna().sum())
    if sem_area:
        logger.warning(
            "{}: {:,} linha(s) sem área — município criado depois do Censo {}.",
            ENTITY,
            sem_area,
            ANO_REFERENCIA_AREA,
        )

    combinada = combinada.loc[combinada["ano"].isin(ANOS_IBGE)].sort_values(
        ["ano", "id_municipio"], ignore_index=True
    )
    silver = add_metadata(combinada[SILVER_COLS], silver_ts)
    write_parquet_partitioned(silver, SILVER_DATA_DIR / ENTITY, "ano", overwrite_entity=True)
    logger.info("{} gravada. Total: {:,}", ENTITY, len(silver))

    for ano, grupo in silver.groupby("ano", dropna=True):
        logger.info(
            "  {}: {:,} municípios | população somada {:,.0f} | área somada {:,.0f} km²",
            ano,
            grupo["id_municipio"].nunique(),
            grupo["populacao_residente"].sum(),
            grupo[MEDIDA_AREA].sum(),
        )

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver IBGE validada com sucesso.")


if __name__ == "__main__":
    run_silver()
