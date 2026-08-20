"""Silver layer: semantic conformance and quality checks."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.config import ANOS
from src.preprocessing.inep.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.io import read_parquet, write_parquet_partitioned

META_YEARS = range(2024, 2031)


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series(pd.NA, index=df.index)


def norm_pct(series: pd.Series) -> pd.Series:
    """Normalize meta percentages: '>80' -> 80.0, numeric strings -> float, else NA."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_string_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype("string").str.strip()
    out = pd.Series(pd.NA, index=series.index, dtype="Float64")
    gt = text.str.startswith(">", na=False)
    out.loc[gt] = 80.0
    numeric_mask = text.str.match(r"^[0-9]+([.][0-9]+)?$", na=False)
    out.loc[numeric_mask] = pd.to_numeric(text.loc[numeric_mask], errors="coerce")
    return out


def diagonal_taxa(df: pd.DataFrame) -> pd.Series:
    ano = pd.to_numeric(df["NU_ANO_AVALIACAO"], errors="coerce")
    t2023 = norm_pct(_col(df, "PC_ALUNO_ALFABETIZADO"))
    t2024 = norm_pct(_col(df, "PC_ALUNO_ALFABETIZADO_2024"))
    t2025 = norm_pct(_col(df, "PC_ALUNO_ALFABETIZADO_2025"))
    out = pd.Series(pd.NA, index=df.index, dtype="Float64")
    out.loc[ano == 2023] = t2023.loc[ano == 2023]
    out.loc[ano == 2024] = t2024.loc[ano == 2024]
    out.loc[ano == 2025] = t2025.loc[ano == 2025]
    return out


def metas_normalizadas(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for ano in META_YEARS:
        out[f"meta_alfabetizacao_{ano}"] = norm_pct(_col(df, f"META_FINAL_{ano}"))
    return out


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def _filter_anos(df: pd.DataFrame) -> pd.DataFrame:
    ano = pd.to_numeric(df["NU_ANO_AVALIACAO"], errors="coerce")
    return df.loc[ano.isin(ANOS)].copy()


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver...")
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)
    logger.info("SILVER_DATA_DIR : {}", SILVER_DATA_DIR)

    metas_uf = _filter_anos(read_parquet(BRONZE_DATA_DIR / "metas_ufs"))
    metas = metas_normalizadas(metas_uf)
    base_uf = pd.DataFrame(
        {
            "ano": pd.to_numeric(metas_uf["NU_ANO_AVALIACAO"], errors="coerce").astype("Int64"),
            "sigla_uf": _col(metas_uf, "SIGLA_UF"),
            "nome_uf": _col(metas_uf, "NOME_UF").astype("string"),
            "rede": _col(metas_uf, "REDE").astype("string").str.title(),
            "taxa_alfabetizacao": diagonal_taxa(metas_uf),
            "percentual_participacao": pd.to_numeric(
                _col(metas_uf, "PC_AVALIADOS_LP"), errors="coerce"
            ),
        }
    )
    base_uf = pd.concat([base_uf, metas], axis=1)

    brasil = add_metadata(
        base_uf.loc[base_uf["nome_uf"].str.strip() == "Brasil"].drop(
            columns=["sigla_uf", "nome_uf"]
        ),
        silver_ts,
    )
    write_parquet_partitioned(
        brasil, SILVER_DATA_DIR / "meta_alfabetizacao_brasil", "ano", overwrite_entity=True
    )
    logger.info("meta_alfabetizacao_brasil gravada. Total: {:,}", len(brasil))

    meta_uf = add_metadata(
        base_uf.loc[
            base_uf["nome_uf"].notna() & (base_uf["nome_uf"].str.strip() != "Brasil")
        ].drop(columns=["nome_uf"]),
        silver_ts,
    )
    write_parquet_partitioned(
        meta_uf, SILVER_DATA_DIR / "meta_alfabetizacao_uf", "ano", overwrite_entity=True
    )
    logger.info("meta_alfabetizacao_uf gravada. Total: {:,}", len(meta_uf))

    metas_mun = _filter_anos(read_parquet(BRONZE_DATA_DIR / "metas_municipios"))
    nivel = _col(metas_mun, "NIVEIS_ALFABETIZACAO_2023")
    if "CO_NIVEL_ALFABETIZACAO" in metas_mun.columns:
        nivel = nivel.fillna(_col(metas_mun, "CO_NIVEL_ALFABETIZACAO"))
    meta_mun = add_metadata(
        pd.concat(
            [
                pd.DataFrame(
                    {
                        "ano": pd.to_numeric(
                            metas_mun["NU_ANO_AVALIACAO"], errors="coerce"
                        ).astype("Int64"),
                        "id_municipio": (
                            metas_mun["CO_MUNICIPIO"].astype("string").str.strip().str.zfill(7)
                        ),
                        "rede": _col(metas_mun, "NO_TP_REDE").astype("string").str.title(),
                        "taxa_alfabetizacao": diagonal_taxa(metas_mun),
                        "nivel_alfabetizacao": pd.to_numeric(nivel, errors="coerce"),
                        "percentual_participacao": pd.to_numeric(
                            _col(metas_mun, "PC_AVALIADOS_LP"), errors="coerce"
                        ),
                    }
                ),
                metas_normalizadas(metas_mun),
            ],
            axis=1,
        ).loc[lambda d: d["id_municipio"].notna()],
        silver_ts,
    )
    write_parquet_partitioned(
        meta_mun,
        SILVER_DATA_DIR / "meta_alfabetizacao_municipio",
        "ano",
        overwrite_entity=True,
    )
    logger.info("meta_alfabetizacao_municipio gravada. Total: {:,}", len(meta_mun))

    uf_bronze = read_parquet(BRONZE_DATA_DIR / "ts_estado")
    rede_uf = pd.to_numeric(uf_bronze["ID_TIPO_REDE"], errors="coerce")
    uf = add_metadata(
        pd.DataFrame(
            {
                "ano": pd.to_numeric(uf_bronze["NU_ANO_AVALIACAO"], errors="coerce").astype(
                    "Int64"
                ),
                "id_uf": pd.to_numeric(uf_bronze["CO_UF"], errors="coerce").astype("Int64"),
                "sigla_uf": uf_bronze["SG_UF"],
                "serie": pd.to_numeric(uf_bronze["TP_SERIE"], errors="coerce").astype("Int64"),
                "rede": rede_uf.astype("Int64"),
                "taxa_alfabetizacao": pd.to_numeric(
                    uf_bronze["PC_ALUNO_ALFABETIZADO"], errors="coerce"
                ),
                "media_portugues": pd.to_numeric(uf_bronze["VL_MEDIA_LP"], errors="coerce"),
            }
        ).loc[uf_bronze["CO_UF"].notna() & (rede_uf == 5)],
        silver_ts,
    )
    write_parquet_partitioned(uf, SILVER_DATA_DIR / "uf", "ano", overwrite_entity=True)
    logger.info("silver/uf gravada. Total: {:,}", len(uf))

    mun_bronze = read_parquet(BRONZE_DATA_DIR / "ts_municipio")
    rede_mun = pd.to_numeric(mun_bronze["ID_TIPO_REDE"], errors="coerce")
    municipio = add_metadata(
        pd.DataFrame(
            {
                "ano": pd.to_numeric(mun_bronze["NU_ANO_AVALIACAO"], errors="coerce").astype(
                    "Int64"
                ),
                "id_municipio": (
                    mun_bronze["CO_MUNICIPIO"].astype("string").str.strip().str.zfill(7)
                ),
                "nome_municipio": mun_bronze["NO_MUNICIPIO"].astype("string").str.strip(),
                "id_uf": pd.to_numeric(mun_bronze["CO_UF"], errors="coerce").astype("Int64"),
                "sigla_uf": mun_bronze["SG_UF"],
                "serie": pd.to_numeric(mun_bronze["TP_SERIE"], errors="coerce").astype("Int64"),
                "rede": rede_mun.astype("Int64"),
                "taxa_alfabetizacao": pd.to_numeric(
                    mun_bronze["PC_ALUNO_ALFABETIZADO"], errors="coerce"
                ),
                "media_portugues": pd.to_numeric(mun_bronze["VL_MEDIA_LP"], errors="coerce"),
            }
        ).loc[mun_bronze["CO_MUNICIPIO"].notna() & (rede_mun == 3)],
        silver_ts,
    )
    write_parquet_partitioned(
        municipio, SILVER_DATA_DIR / "municipio", "ano", overwrite_entity=True
    )
    logger.info("silver/municipio gravada. Total: {:,}", len(municipio))

    dest_alunos = SILVER_DATA_DIR / "alunos"
    for ano in ANOS:
        alunos_bronze = read_parquet(BRONZE_DATA_DIR / "ts_aluno" / f"NU_ANO_AVALIACAO={ano}")
        prof = pd.to_numeric(alunos_bronze["VL_PROFICIENCIA_LP"], errors="coerce")
        dep = pd.to_numeric(alunos_bronze["TP_DEPENDENCIA"], errors="coerce")
        mask = (
            alunos_bronze["ID_ALUNO"].notna()
            & alunos_bronze["CO_MUNICIPIO"].notna()
            & dep.isin([2, 3])
        )
        base = alunos_bronze.loc[mask].copy()
        prof = prof.loc[mask]
        alfabetizado = pd.to_numeric(base["IN_ALFABETIZADO"], errors="coerce").astype("Int64")
        alunos = add_metadata(
            pd.DataFrame(
                {
                    "ano": pd.to_numeric(base["NU_ANO_AVALIACAO"], errors="coerce").astype(
                        "Int64"
                    ),
                    "id_municipio": base["CO_MUNICIPIO"].astype("string").str.strip().str.zfill(7),
                    "id_escola": base["ID_ESCOLA"].astype("string").str.strip(),
                    "id_aluno": base["ID_ALUNO"].astype("string").str.strip(),
                    "caderno": pd.to_numeric(base["CO_CADERNO_LP"], errors="coerce").astype(
                        "Int64"
                    ),
                    "serie": pd.to_numeric(base["TP_SERIE"], errors="coerce").astype("Int64"),
                    "dependencia_administrativa": pd.to_numeric(
                        base["TP_DEPENDENCIA"], errors="coerce"
                    ).astype("Int64"),
                    "presenca": pd.to_numeric(base["IN_PRESENCA_LP"], errors="coerce").astype(
                        "Int64"
                    ),
                    "preenchimento_caderno": pd.to_numeric(
                        base["IN_PREENCHIMENTO_LP"], errors="coerce"
                    ).astype("Int64"),
                    "alfabetizado": alfabetizado.where(prof.notna(), pd.NA),
                    "proficiencia": prof,
                    "peso_aluno": pd.to_numeric(base["VL_PESO_ALUNO_LP"], errors="coerce"),
                }
            ),
            silver_ts,
        )
        write_parquet_partitioned(alunos, dest_alunos, "ano", overwrite_entity=(ano == ANOS[0]))
        logger.info("silver/alunos {}: {:,} linhas", ano, len(alunos))
        del alunos, alunos_bronze, base

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver validada com sucesso.")
