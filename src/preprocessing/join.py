"""Orquestra left-joins de fontes externas sobre aluno_contexto -> aluno_joined.

Contrato de cada join
---------------------
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
    logger.info("Taxa de match ATU ({}) : {:.1%}", match_col, match_rate)
    return out


# Registro ordenado dos joins.
JOINS = (
    join_atu,
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
