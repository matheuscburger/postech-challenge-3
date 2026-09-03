"""Contrato de cada join
------------------------
Cada função recebe o DataFrame de alunos e devolve o mesmo enriquecido:

    def join_<fonte>(alunos: pd.DataFrame) -> pd.DataFrame: ...

Regras:
  - preservar 1 linha por aluno (merge how="left", validate="m:1");
  - prefixar colunas novas com a fonte (ex.: ctx_atu_*, ctx_fundeb_*);
  - logar a taxa de match dentro da própria função.
"""

from __future__ import annotations

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR
from src.preprocessing.censoescolar.schemas import METRIC_COLS
from src.preprocessing.io import read_parquet, write_parquet_partitioned

MAP_DEP_ALUNO_ATU = {1: "Federal", 2: "Estadual", 3: "Municipal", 4: "Privada"}
METRIC_RENAME = {c: f"ctx_atu_{c.removeprefix('media_')}" for c in METRIC_COLS}
JOIN_KEYS = ["ano", "id_municipio", "_dep_atu"]


def join_atu(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join métricas municipais do Censo Escolar ATU em ``alunos``."""
    atu = read_parquet(PROCESSED_DATA_DIR / "atu_municipios")

    atu_join = (
        atu.loc[
            atu["localizacao"].eq("Total")
            & atu["dependencia_administrativa"].isin(MAP_DEP_ALUNO_ATU.values())
        ]
        .rename(columns={"dependencia_administrativa": "_dep_atu", **METRIC_RENAME})
        .loc[:, [*JOIN_KEYS, *METRIC_RENAME.values()]]
        .copy()
    )

    out = alunos.copy()
    out["_dep_atu"] = out["dependencia_administrativa"].map(MAP_DEP_ALUNO_ATU)
    out = out.merge(atu_join, on=JOIN_KEYS, how="left", validate="m:1")
    out = out.drop(columns=["_dep_atu"])

    match_col = METRIC_RENAME["media_fundamental"]
    match_rate = float(out[match_col].notna().mean())
    logger.info("Taxa de match ATU ({}): {:.1%}", match_col, match_rate)
    return out


# ---------------------------------------------------------------------------
# Atlas do Desenvolvimento Humano
# ---------------------------------------------------------------------------
ATLAS_COLUNAS = [
    "idhm",
    "idhm_educacao",
    "idhm_renda",
    "idhm_longevidade",
    "taxa_analfabetismo_15mais",
    "taxa_frequencia_6a14",
    "expectativa_anos_estudo",
    "taxa_fundamental_incompleto",
    "renda_per_capita",
    "indice_gini",
    "percentual_pobres",
    "percentual_extremamente_pobres",
    "percentual_vulneraveis_pobreza",
    "percentual_domicilios_agua",
    "percentual_domicilios_energia",
    "taxa_densidade_domiciliar",
]
ATLAS_RENAME = {c: f"ctx_atlas_{c}" for c in ATLAS_COLUNAS}


def join_atlas(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join indicadores municipais do Atlas do Desenvolvimento Humano em ``alunos``.

    O Atlas está fixo no ano-base 2010 (Censo Demográfico) — o join é feito
    apenas por id_municipio (não por ano); o mesmo valor de 2010 é usado
    para todos os anos de ``alunos``.
    """
    atlas = read_parquet(PROCESSED_DATA_DIR / "atlas_desenvolvimento_humano")

    atlas_join = (
        atlas.rename(columns=ATLAS_RENAME)
        .loc[:, ["id_municipio", *ATLAS_RENAME.values()]]
        .copy()
    )
    atlas_join["id_municipio"] = atlas_join["id_municipio"].astype(str).str.zfill(7)

    out = alunos.copy()
    out["id_municipio"] = out["id_municipio"].astype(str).str.zfill(7)
    out = out.merge(atlas_join, on="id_municipio", how="left", validate="m:1")

    match_col = ATLAS_RENAME["idhm"]
    match_rate = float(out[match_col].notna().mean())
    logger.info("Taxa de match Atlas ({}): {:.1%}", match_col, match_rate)
    return out


# ---------------------------------------------------------------------------
# FUNDEB — Nível Socioeconômico (NSE)
# ---------------------------------------------------------------------------
ANO_PROXY_FUNDEB = 2023
ANO_BASE_PROXY_FUNDEB = 2024


def _preparar_nse_municipio(nse: pd.DataFrame) -> pd.DataFrame:
    nse_mun = nse.loc[nse["tipo_ente"] == "municipio"].copy()
    nse_mun["id_municipio"] = nse_mun["codigo_ente"].astype("Int64").astype(str).str.zfill(7)

    base = nse_mun[["ano", "id_municipio", "valor_nse", "ponderador_nse"]].copy()
    base["nse_proxy"] = False

    proxy = base.loc[base["ano"] == ANO_BASE_PROXY_FUNDEB].copy()
    proxy["ano"] = ANO_PROXY_FUNDEB
    proxy["nse_proxy"] = True

    resultado = pd.concat([base, proxy], ignore_index=True)
    return resultado.rename(
        columns={
            "valor_nse": "ctx_fundeb_nse_municipio",
            "ponderador_nse": "ctx_fundeb_ponderador_nse_municipio",
            "nse_proxy": "ctx_fundeb_nse_municipio_proxy_2023",
        }
    )


def _preparar_nse_uf(nse: pd.DataFrame) -> pd.DataFrame:
    nse_uf = nse.loc[nse["tipo_ente"] == "uf"].copy()
    nse_uf["id_uf"] = nse_uf["codigo_ente"].astype("Int64").astype(str).str.zfill(2)

    base = nse_uf[["ano", "id_uf", "valor_nse", "ponderador_nse"]].copy()
    base["nse_proxy"] = False

    proxy = base.loc[base["ano"] == ANO_BASE_PROXY_FUNDEB].copy()
    proxy["ano"] = ANO_PROXY_FUNDEB
    proxy["nse_proxy"] = True

    resultado = pd.concat([base, proxy], ignore_index=True)
    return resultado.rename(
        columns={
            "valor_nse": "ctx_fundeb_nse_uf",
            "ponderador_nse": "ctx_fundeb_ponderador_nse_uf",
            "nse_proxy": "ctx_fundeb_nse_uf_proxy_2023",
        }
    )


def join_fundeb(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do NSE do FUNDEB (município e UF) em ``alunos``.

    O FUNDEB só cobre 2024-2025; o ano de 2023 recebe o valor de 2024 como
    proxy (NSE muda pouco ano a ano) — coluna ctx_fundeb_nse_*_proxy_2023
    marca quais linhas usaram o proxy. O NSE da UF entra como coluna
    separada, além do NSE do município (não é usado como fallback).
    """
    nse = read_parquet(PROCESSED_DATA_DIR / "nse_entes_federados")
    nse_mun = _preparar_nse_municipio(nse)
    nse_uf = _preparar_nse_uf(nse)

    out = alunos.copy()
    out["id_municipio"] = out["id_municipio"].astype(str).str.zfill(7)
    out["id_uf"] = out["id_uf"].astype(str).str.zfill(2)

    out = out.merge(nse_mun, on=["ano", "id_municipio"], how="left", validate="m:1")
    out = out.merge(nse_uf, on=["ano", "id_uf"], how="left", validate="m:1")

    match_rate_mun = float(out["ctx_fundeb_nse_municipio"].notna().mean())
    match_rate_uf = float(out["ctx_fundeb_nse_uf"].notna().mean())
    logger.info("Taxa de match FUNDEB município (ctx_fundeb_nse_municipio): {:.1%}", match_rate_mun)
    logger.info("Taxa de match FUNDEB UF (ctx_fundeb_nse_uf): {:.1%}", match_rate_uf)
    return out


# Registro ordenado dos joins.
JOINS = (
    join_atu,
    join_atlas,
    join_fundeb,
)


def run_join() -> None:
    """Lê aluno_contexto, aplica ``JOINS`` em sequência e grava aluno_joined."""
    logger.info("Iniciando joins sobre aluno_contexto...")
    alunos = read_parquet(PROCESSED_DATA_DIR / "aluno_contexto")

    for join_fn in JOINS:
        logger.info("Aplicando {}...", join_fn.__name__)
        alunos = join_fn(alunos)

    dest = PROCESSED_DATA_DIR / "aluno_joined"
    write_parquet_partitioned(alunos, dest, "ano", overwrite_entity=True)
    logger.success("aluno_joined gravada em {}: {:,} linhas", dest, len(alunos))


if __name__ == "__main__":
    run_join()
