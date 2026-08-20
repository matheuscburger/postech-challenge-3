"""Gold layer: business tables for analytics and modeling."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.config import ANOS, CORTE_PROFICIENCIA
from src.preprocessing.inep.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.io import read_parquet, write_parquet_partitioned

META_YEARS = list(range(2024, 2031))


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def metas_long(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    """Unpivot META_FINAL_2024..2030 and keep latest non-null per key+year."""
    value_vars = [c for c in (f"meta_alfabetizacao_{a}" for a in META_YEARS) if c in df.columns]
    long = df.melt(
        id_vars=["ano", *key_cols],
        value_vars=value_vars,
        var_name="meta_col",
        value_name="meta",
    )
    long = long.rename(columns={"ano": "ano_pub"})
    long["ano"] = long["meta_col"].str.extract(r"(\d{4})$").astype("Int64")
    long["_has_meta"] = long["meta"].notna()
    long = long.sort_values(
        [*key_cols, "ano", "_has_meta", "ano_pub"],
        ascending=[True] * len(key_cols) + [True, False, False],
    )
    long = long.drop_duplicates([*key_cols, "ano"])
    return long.loc[long["meta"].notna(), [*key_cols, "ano", "meta"]]


def _categoria_desempenho(dist: pd.Series, meta: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=dist.index, dtype="string")
    known = meta.notna()
    out.loc[known & (dist >= 5)] = "Muito acima"
    out.loc[known & (dist >= 0) & (dist < 5)] = "Acima"
    out.loc[known & (dist >= -5) & (dist < 0)] = "Próximo"
    out.loc[known & (dist < -5)] = "Muito abaixo"
    return out


def _faixa_participacao(part: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=part.index, dtype="string")
    known = part.notna()
    out.loc[known & (part >= 95)] = "Alta"
    out.loc[known & (part >= 80) & (part < 95)] = "Média"
    out.loc[known & (part < 80)] = "Baixa"
    return out


def _indicadores(
    res: pd.DataFrame,
    part: pd.DataFrame,
    meta: pd.DataFrame,
    keys: list[str],
    rede: int,
) -> pd.DataFrame:
    part = (
        part.assign(_ok=part["percentual_participacao"].notna())
        .sort_values([*keys, "_ok"], ascending=[True] * len(keys) + [False])
        .drop_duplicates(keys)
        .drop(columns=["_ok"])
    )
    out = res.merge(part, on=keys, how="left").merge(meta, on=keys, how="left")
    out["rede"] = rede
    dist = (out["taxa_alfabetizacao"] - out["meta"]).round(2)
    out["distancia_meta"] = dist
    atingiu = pd.Series(pd.NA, index=out.index, dtype="boolean")
    atingiu = atingiu.mask(out["meta"].notna(), dist >= 0)
    out["atingiu_meta"] = atingiu
    out["categoria_desempenho"] = _categoria_desempenho(dist, out["meta"])
    out["faixa_participacao"] = _faixa_participacao(out["percentual_participacao"])
    return out


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold...")
    logger.info("SILVER_DATA_DIR     : {}", SILVER_DATA_DIR)
    logger.info("PROCESSED_DATA_DIR  : {}", PROCESSED_DATA_DIR)

    silver_municipio = read_parquet(SILVER_DATA_DIR / "municipio")
    silver_meta_mun = read_parquet(SILVER_DATA_DIR / "meta_alfabetizacao_municipio")
    res_mun = silver_municipio.loc[
        silver_municipio["rede"] == 3,
        [
            "ano",
            "id_municipio",
            "nome_municipio",
            "id_uf",
            "sigla_uf",
            "taxa_alfabetizacao",
            "media_portugues",
        ],
    ].copy()
    part_mun = silver_meta_mun[["ano", "id_municipio", "percentual_participacao"]].copy()
    meta_mun = metas_long(silver_meta_mun, ["id_municipio"])
    gold_ind_mun = add_gold_metadata(
        _indicadores(res_mun, part_mun, meta_mun, ["ano", "id_municipio"], rede=3),
        gold_ts,
    )
    write_parquet_partitioned(
        gold_ind_mun,
        PROCESSED_DATA_DIR / "indicadores_municipio",
        "ano",
        overwrite_entity=True,
    )
    logger.info("gold/indicadores_municipio: {:,}", len(gold_ind_mun))

    silver_uf = read_parquet(SILVER_DATA_DIR / "uf")
    silver_meta_uf = read_parquet(SILVER_DATA_DIR / "meta_alfabetizacao_uf")
    res_uf = silver_uf.loc[
        silver_uf["rede"] == 5,
        ["ano", "id_uf", "sigla_uf", "taxa_alfabetizacao", "media_portugues"],
    ].copy()
    part_uf = silver_meta_uf[["ano", "sigla_uf", "percentual_participacao"]].copy()
    meta_uf = metas_long(silver_meta_uf, ["sigla_uf"])
    gold_ind_uf = add_gold_metadata(
        _indicadores(res_uf, part_uf, meta_uf, ["ano", "sigla_uf"], rede=5),
        gold_ts,
    )
    write_parquet_partitioned(
        gold_ind_uf,
        PROCESSED_DATA_DIR / "indicadores_uf",
        "ano",
        overwrite_entity=True,
    )
    logger.info("gold/indicadores_uf: {:,}", len(gold_ind_uf))

    ctx_mun = gold_ind_mun[
        [
            "ano",
            "id_municipio",
            "taxa_alfabetizacao",
            "media_portugues",
            "meta",
            "distancia_meta",
            "atingiu_meta",
            "percentual_participacao",
            "categoria_desempenho",
            "faixa_participacao",
        ]
    ].rename(
        columns={
            "taxa_alfabetizacao": "ctx_taxa_municipio",
            "media_portugues": "ctx_media_municipio",
            "meta": "ctx_meta_municipio",
            "distancia_meta": "ctx_distancia_meta_municipio",
            "atingiu_meta": "ctx_atingiu_meta_municipio",
            "percentual_participacao": "ctx_participacao_municipio",
            "categoria_desempenho": "ctx_categoria_municipio",
            "faixa_participacao": "ctx_faixa_participacao_municipio",
        }
    )

    dest_aluno = PROCESSED_DATA_DIR / "aluno_contexto"
    for ano in ANOS:
        alunos = read_parquet(SILVER_DATA_DIR / "alunos" / f"ano={ano}")
        alunos = alunos.loc[alunos["proficiencia"].notna()].copy()
        merged = alunos.merge(ctx_mun, on=["ano", "id_municipio"], how="left")
        gold_aluno = add_gold_metadata(
            pd.DataFrame(
                {
                    "id_aluno": merged["id_aluno"],
                    "ano": merged["ano"],
                    "id_municipio": merged["id_municipio"],
                    "id_uf": pd.to_numeric(
                        merged["id_municipio"].astype("string").str.slice(0, 2),
                        errors="coerce",
                    ).astype("Int64"),
                    "dependencia_administrativa": merged["dependencia_administrativa"],
                    "caderno": merged["caderno"],
                    "ctx_taxa_municipio": merged["ctx_taxa_municipio"],
                    "ctx_media_municipio": merged["ctx_media_municipio"],
                    "ctx_meta_municipio": merged["ctx_meta_municipio"],
                    "ctx_distancia_meta_municipio": merged["ctx_distancia_meta_municipio"],
                    "ctx_atingiu_meta_municipio": merged["ctx_atingiu_meta_municipio"],
                    "ctx_participacao_municipio": merged["ctx_participacao_municipio"],
                    "ctx_categoria_municipio": merged["ctx_categoria_municipio"],
                    "ctx_faixa_participacao_municipio": merged["ctx_faixa_participacao_municipio"],
                    "proficiencia": merged["proficiencia"],
                    "gap_proficiencia": (merged["proficiencia"] - CORTE_PROFICIENCIA).round(2),
                    "label_alfabetizado": merged["alfabetizado"],
                }
            ),
            gold_ts,
        )
        write_parquet_partitioned(gold_aluno, dest_aluno, "ano", overwrite_entity=(ano == ANOS[0]))
        logger.info("gold/aluno_contexto {}: {:,}", ano, len(gold_aluno))
        del alunos, merged, gold_aluno

    for tabela, checks in CHECKS_GOLD.items():
        df = read_parquet(PROCESSED_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "GOLD")
        del df

    logger.success("Camada Gold validada com sucesso.")
