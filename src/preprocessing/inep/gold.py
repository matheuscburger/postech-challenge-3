"""Gold layer: business tables for analytics and modeling.

Three tables, one grain each:

* ``gold/aluno``     — one row per ``(ano, id_aluno)``: foreign keys + the target.
* ``gold/municipio`` — one row per ``(ano, id_municipio)``: results, goals and
  INEP classifications for the municipal network (``ts_municipio`` +
  ``resultados_e_metas_municipios``).
* ``gold/ufs``       — one row per ``(ano, id_uf)``: the same, for the state
  network (``ts_estado`` + ``resultados_e_metas_ufs``).

``gold/aluno`` carries almost no predictors on purpose. The former ``ctx_*``
columns were same-year municipal aggregates of the very students being
predicted, which is leakage of a subtler kind; ``caderno`` is a draw that INEP
equalizes, so it carries no signal.

**A proficiência voltou — como ALVO, não como feature.**
-------------------------------------------------------
Ela saiu daqui na primeira versão, e o motivo estava certo: como feature de um
classificador de ``label_alfabetizado``, ela é vazamento perfeito, porque o
rótulo é literalmente ``proficiencia >= CORTE_PROFICIENCIA`` (conferido: bate em
100,0000% das linhas). Isso não mudou.

O que mudou foi a pergunta. A EDA de 04-05/09/2026 mediu quanto a dicotomização
custa, e o número é grande: com as mesmas features e o mesmo grão, o teto do
oráculo é **+6,4 pontos de acurácia** para a binária contra **R² de 19,5%** para
a contínua. O sinal é o mesmo; a acurácia é que não consegue expressá-lo. Pior,
o corte 743 cai no percentil 41,6 — o pico da densidade —, então errar a nota
por 10 pontos (0,2 desvio) já troca a classe de 17% dos alunos.

Então ``label_proficiencia`` entra como **segundo alvo**, para modelagem por
regressão. As duas colunas de alvo são MUTUAMENTE EXCLUDENTES:

    modelo de regressão      -> alvo label_proficiencia, label_alfabetizado FORA
    modelo de classificação  -> alvo label_alfabetizado,  label_proficiencia FORA

Usar uma como feature da outra dá AUC 1,0. ``roles.VAZAMENTO_POR_ALVO`` declara
isso, e é de lá que o ``features/`` deve ler — não daqui.

O prefixo ``label_`` é o mesmo de ``label_alfabetizado``: as duas são alvos, e
nomear igual o que cumpre o mesmo papel é o que impede alguém de tratar uma
delas como preditor por distração de leitura.

The one predictor that stays is ``dependencia_administrativa`` (2 = estadual,
3 = municipal). It names the network the school belongs to, is known long
before the exam, is not derivable from any other column here, and is not
constant — so it passes the three tests the others failed. It is also the
grain at which the Censo Escolar publishes ATU: without it, ``join.join_atu``
cannot attach municipal averages to the right network.

The municipal and state tables hold only independently measured columns.
Anything derivable from another column was dropped: ``rede`` was constant
(the row filters below already pin the network), and ``distancia_meta``,
``atingiu_meta``, ``categoria_desempenho`` and ``faixa_participacao`` were
four encodings of two quantities still present — ``taxa_alfabetizacao −
meta`` and ``percentual_participacao``. The classification rules survive as
functions at the bottom of this module; ``features/`` applies them to the
lagged values, which is the only form in which they may legitimately reach a
student row. See ``roles.COLUNAS_LAG_OBRIGATORIO``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import ANOS, PROCESSED_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.inep.quality import CHECKS_GOLD, checar_qualidade
from src.preprocessing.io import read_parquet, write_parquet_partitioned

META_YEARS = list(range(2024, 2031))

# Redes em ``ID_TIPO_REDE``: 2 = estadual, 3 = municipal, 5 = pública (as duas).
# A planilha de metas só cobre a rede pública, então esses são os filtros que
# casam as duas fontes.
REDE_MUNICIPAL = 3
REDE_PUBLICA = 5

COLS_ALUNO = [
    "ano",
    "id_uf",
    "id_municipio",
    "id_escola",
    "id_aluno",
    "dependencia_administrativa",
    # A NOTA vem antes do RÓTULO porque é ela a medição: label_alfabetizado é
    # label_proficiencia >= CORTE_PROFICIENCIA, e ler a derivada antes da origem
    # inverte a leitura da tabela.
    "label_proficiencia",
    "label_alfabetizado",
]

COLS_MUNICIPIO = [
    "ano",
    "id_uf",
    "sigla_uf",
    "id_municipio",
    "nome_municipio",
    "taxa_alfabetizacao",
    "media_portugues",
    "meta",
    "percentual_participacao",
    "nivel_alfabetizacao",
]

COLS_UF = [
    "ano",
    "id_uf",
    "sigla_uf",
    "taxa_alfabetizacao",
    "media_portugues",
    "meta",
    "percentual_participacao",
]


def add_gold_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_gold_processed_at"] = ts
    return df


def metas_long(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    """Unpivot META_FINAL_2024..2030 and keep latest non-null per key+year.

    ``META_FINAL_2024`` is the goal *for* 2024, and every publication repeats
    the whole 2024..2030 range. Later publications round to integers, so the
    "latest" rule trades precision for officialness; the non-null preference
    is what rescues states present in one publication but not another.
    """
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


def _juntar(
    res: pd.DataFrame,
    part: pd.DataFrame,
    meta: pd.DataFrame,
    keys: list[str],
) -> pd.DataFrame:
    """Attach participation and goal to a results frame, one row per key."""
    part = (
        part.assign(_ok=part["percentual_participacao"].notna())
        .sort_values([*keys, "_ok"], ascending=[True] * len(keys) + [False])
        .drop_duplicates(keys)
        .drop(columns=["_ok"])
    )
    return res.merge(part, on=keys, how="left").merge(meta, on=keys, how="left")


def _id_uf(df: pd.DataFrame) -> pd.Series:
    """UF code from the source column, falling back to the município prefix."""
    out = pd.Series(pd.NA, index=df.index, dtype="Int64")
    if "id_uf" in df.columns:
        out = pd.to_numeric(df["id_uf"], errors="coerce").astype("Int64")
    prefixo = pd.to_numeric(
        df["id_municipio"].astype("string").str.slice(0, 2), errors="coerce"
    ).astype("Int64")
    return out.fillna(prefixo)


def transform_municipio(
    silver_municipio: pd.DataFrame, silver_meta: pd.DataFrame, gold_ts
) -> pd.DataFrame:
    """``ts_municipio`` (results) + ``resultados_e_metas_municipios`` (goals)."""
    res = silver_municipio.loc[
        silver_municipio["rede"] == REDE_MUNICIPAL,
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
    part_cols = ["ano", "id_municipio", "percentual_participacao"]
    if "nivel_alfabetizacao" in silver_meta.columns:
        part_cols.append("nivel_alfabetizacao")
    part = silver_meta[part_cols].copy()
    meta = metas_long(silver_meta, ["id_municipio"])
    out = _juntar(res, part, meta, ["ano", "id_municipio"])
    for col in COLS_MUNICIPIO:
        if col not in out.columns:
            out[col] = pd.NA
    return add_gold_metadata(out[COLS_MUNICIPIO], gold_ts)


def transform_ufs(silver_uf: pd.DataFrame, silver_meta: pd.DataFrame, gold_ts) -> pd.DataFrame:
    """``ts_estado`` (results) + ``resultados_e_metas_ufs`` (goals)."""
    res = silver_uf.loc[
        silver_uf["rede"] == REDE_PUBLICA,
        ["ano", "id_uf", "sigla_uf", "taxa_alfabetizacao", "media_portugues"],
    ].copy()
    part = silver_meta[["ano", "sigla_uf", "percentual_participacao"]].copy()
    meta = metas_long(silver_meta, ["sigla_uf"])
    out = _juntar(res, part, meta, ["ano", "sigla_uf"])
    return add_gold_metadata(out[COLS_UF], gold_ts)


def transform_aluno(silver_alunos: pd.DataFrame, gold_ts) -> pd.DataFrame:
    """``ts_aluno`` reduced to foreign keys, the network, and the two targets.

    Rows without ``proficiencia`` have no defined label, so they are dropped
    here rather than carried into training as nulls. O mesmo filtro serve aos
    dois alvos: sem nota não há nem rótulo nem regressão.

    ``label_alfabetizado`` e ``label_proficiencia`` são alvos alternativos, não
    features um do outro — ver o docstring do módulo e ``roles.PAPEIS_ALUNO``.
    """
    base = silver_alunos.loc[
        silver_alunos["proficiencia"].notna() & silver_alunos["alfabetizado"].notna()
    ]
    out = pd.DataFrame(
        {
            "ano": pd.to_numeric(base["ano"], errors="coerce").astype("Int64"),
            "id_uf": _id_uf(base),
            "id_municipio": base["id_municipio"].astype("string"),
            "id_escola": base["id_escola"].astype("string"),
            "id_aluno": base["id_aluno"].astype("string"),
            "dependencia_administrativa": pd.to_numeric(
                base["dependencia_administrativa"], errors="coerce"
            ).astype("Int64"),
            "label_alfabetizado": pd.to_numeric(base["alfabetizado"], errors="coerce").astype(
                "Int64"
            ),
            "label_proficiencia": pd.to_numeric(base["proficiencia"], errors="coerce"),
        }
    )
    return add_gold_metadata(out[COLS_ALUNO], gold_ts)


def run_gold() -> None:
    gold_ts = datetime.now(UTC)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Gold...")
    logger.info("SILVER_DATA_DIR     : {}", SILVER_DATA_DIR)
    logger.info("PROCESSED_DATA_DIR  : {}", PROCESSED_DATA_DIR)

    gold_mun = transform_municipio(
        read_parquet(SILVER_DATA_DIR / "municipio"),
        read_parquet(SILVER_DATA_DIR / "meta_alfabetizacao_municipio"),
        gold_ts,
    )
    write_parquet_partitioned(
        gold_mun, PROCESSED_DATA_DIR / "municipio", "ano", overwrite_entity=True
    )
    logger.info("gold/municipio: {:,}", len(gold_mun))

    gold_uf = transform_ufs(
        read_parquet(SILVER_DATA_DIR / "uf"),
        read_parquet(SILVER_DATA_DIR / "meta_alfabetizacao_uf"),
        gold_ts,
    )
    write_parquet_partitioned(gold_uf, PROCESSED_DATA_DIR / "ufs", "ano", overwrite_entity=True)
    logger.info("gold/ufs: {:,}", len(gold_uf))

    dest_aluno = PROCESSED_DATA_DIR / "aluno"
    for ano in ANOS:
        alunos = read_parquet(SILVER_DATA_DIR / "alunos" / f"ano={ano}")
        gold_aluno = transform_aluno(alunos, gold_ts)
        write_parquet_partitioned(gold_aluno, dest_aluno, "ano", overwrite_entity=(ano == ANOS[0]))
        logger.info("gold/aluno {}: {:,}", ano, len(gold_aluno))
        del alunos, gold_aluno

    for tabela, checks in CHECKS_GOLD.items():
        df = read_parquet(PROCESSED_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "GOLD")
        del df

    logger.success("Camada Gold validada com sucesso.")


# ---------------------------------------------------------------------------
# Regras de classificação do INEP.
#
# Não são colunas da Gold: seriam redundantes com ``taxa_alfabetizacao - meta``
# e ``percentual_participacao``, que já estão nas tabelas. Ficam aqui porque os
# cortes são conhecimento de negócio que não deve se perder — ``features/`` as
# aplica sobre as versões com lag.
# ---------------------------------------------------------------------------


def distancia_meta(taxa: pd.Series, meta: pd.Series) -> pd.Series:
    """Pontos percentuais acima (+) ou abaixo (−) da meta."""
    return (taxa - meta).round(2)


def atingiu_meta(taxa: pd.Series, meta: pd.Series) -> pd.Series:
    """``True`` se a taxa alcançou a meta; NA quando não há meta publicada."""
    out = pd.Series(pd.NA, index=taxa.index, dtype="boolean")
    return out.mask(meta.notna(), distancia_meta(taxa, meta) >= 0)


def categoria_desempenho(taxa: pd.Series, meta: pd.Series) -> pd.Series:
    """Faixas de distância da meta, em pontos percentuais."""
    dist = distancia_meta(taxa, meta)
    out = pd.Series(pd.NA, index=dist.index, dtype="string")
    known = meta.notna()
    out.loc[known & (dist >= 5)] = "Muito acima"
    out.loc[known & (dist >= 0) & (dist < 5)] = "Acima"
    out.loc[known & (dist >= -5) & (dist < 0)] = "Próximo"
    out.loc[known & (dist < -5)] = "Muito abaixo"
    return out


def faixa_participacao(part: pd.Series) -> pd.Series:
    """Faixas de participação na avaliação, em percentual."""
    out = pd.Series(pd.NA, index=part.index, dtype="string")
    known = part.notna()
    out.loc[known & (part >= 95)] = "Alta"
    out.loc[known & (part >= 80) & (part < 95)] = "Média"
    out.loc[known & (part < 80)] = "Baixa"
    return out


if __name__ == "__main__":
    run_gold()
