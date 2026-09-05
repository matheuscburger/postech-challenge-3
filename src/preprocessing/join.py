"""Orquestra left-joins de fontes externas sobre ``aluno`` -> ``base_analitica``.

Contrato de cada join
---------------------
Cada função recebe o DataFrame de alunos e devolve o mesmo enriquecido:

    def join_<fonte>(alunos: pd.DataFrame) -> pd.DataFrame: ...

Regras:
  - preservar 1 linha por aluno (merge how="left", validate="m:1");
  - prefixar colunas novas com a fonte (ex.: ctx_atu_*, ctx_ibge_*, ctx_atlas_*, ctx_fundeb_*);
  - logar a taxa de match dentro da própria função.

Defasagem
---------
Contexto que mede a própria prova destes alunos não pode entrar no ano deles:
seria o alvo voltando pela janela. ``inep.roles`` é quem declara isso —
``COLUNAS_LAG_OBRIGATORIO`` são resultados da avaliação e entram com um ano de
atraso; ``COLUNAS_SEM_LAG`` são publicadas antes da prova e entram no ano
corrente. Os joins do INEP leem a declaração em vez de repetir a lista: se a
Gold ganhar uma coluna de resultado, ela nasce defasada sem ninguém precisar
lembrar disso aqui.

Como 2023 é o primeiro ano da série, o contexto defasado desse ano não existe e
fica NaN. É ausência esperada, não falha de match — por isso a taxa é logada
também por ano.

O IBGE entra sem defasagem: nada ali mede a prova. Área e os indicadores do
Censo 2022 são atributos estruturais do município, e a estimativa populacional
de 1º de julho sai antes da aplicação.

O Atlas (ano-base 2010) e o FUNDEB (NSE) também entram sem defasagem de prova:
são atributos estruturais / socioeconômicos, não resultados da avaliação.
"""

from __future__ import annotations

from loguru import logger
import pandas as pd

from src.config import PROCESSED_DATA_DIR
from src.preprocessing.censoescolar.schemas import METRIC_COLS
from src.preprocessing.ibge.schemas import ENTIDADE_POPULACAO
from src.preprocessing.ibge.schemas import GOLD_COLS as IBGE_GOLD_COLS
from src.preprocessing.inep.roles import (
    CHAVES_JOIN,
    COLUNAS_LAG_OBRIGATORIO,
    COLUNAS_SEM_LAG,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTIDADE_ALUNO = "aluno"
ENTIDADE_DESTINO = "base_analitica"

SUFIXO_LAG = "_lag1"

# --- Censo Escolar (ATU) ---------------------------------------------------
MAP_DEP_ALUNO_ATU = {1: "Federal", 2: "Estadual", 3: "Municipal", 4: "Privada"}
METRIC_RENAME = {c: f"ctx_atu_{c.removeprefix('media_')}" for c in METRIC_COLS}
JOIN_KEYS = ["ano", "id_municipio", "_dep_atu"]

# --- IBGE ------------------------------------------------------------------
CHAVES_IBGE = ["ano", "id_municipio"]
# nome_municipio, id_uf e sigla_uf já chegam pela Gold do INEP: trazê-los de
# novo só criaria _x/_y no merge.
IDENT_IBGE = ["nome_municipio", "id_uf", "sigla_uf"]
COLS_IBGE = [c for c in IBGE_GOLD_COLS if c not in {*CHAVES_IBGE, *IDENT_IBGE}]
IBGE_RENAME = {c: f"ctx_ibge_{c}" for c in COLS_IBGE}
# Em 2023 o IBGE não publicou estimativa municipal e a população é nula por
# decisão da Gold. Medir o match nela confundiria ausência declarada com falha
# de join, então a régua é a área, presente em todos os anos.
IBGE_COL_MATCH = "area_km2"

# --- INEP ------------------------------------------------------------------
PREFIXO_INEP = {"municipio": "ctx_inep_mun_", "ufs": "ctx_inep_uf_"}

# --- Atlas -----------------------------------------------------------------
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

# --- FUNDEB ----------------------------------------------------------------
ANO_PROXY_FUNDEB = 2023
ANO_BASE_PROXY_FUNDEB = 2024


def _logar_match(rotulo: str, out: pd.DataFrame, coluna: str) -> None:
    """Taxa de match global e por ano — a quebra por ano é o que expõe lag vazio."""
    logger.info(
        "Taxa de match {} ({}) : {:.1%}", rotulo, coluna, float(out[coluna].notna().mean())
    )
    por_ano = out.groupby("ano", dropna=False)[coluna].apply(lambda s: float(s.notna().mean()))
    for ano, taxa in por_ano.items():
        logger.info("    {} : {:.1%}", ano, taxa)


def _defasar(gold: pd.DataFrame, chaves: list[str], cols: list[str], prefixo: str) -> pd.DataFrame:
    """Avança o ano em 1: a linha de ``ano`` passa a carregar a medição de ``ano-1``."""
    out = gold.loc[:, [*chaves, *cols]].copy()
    out["ano"] = pd.to_numeric(out["ano"], errors="coerce").astype("Int64") + 1
    return out.rename(columns={c: f"{prefixo}{c}{SUFIXO_LAG}" for c in cols})


def _corrente(
    gold: pd.DataFrame, chaves: list[str], cols: list[str], prefixo: str
) -> pd.DataFrame:
    """Colunas publicadas antes da prova: entram no ano do próprio aluno."""
    return gold.loc[:, [*chaves, *cols]].rename(columns={c: f"{prefixo}{c}" for c in cols})


def _join_inep(alunos: pd.DataFrame, entidade: str, rotulo: str) -> pd.DataFrame:
    """Anexa uma tabela de contexto do INEP, respeitando a defasagem de ``roles``."""
    gold = read_parquet(PROCESSED_DATA_DIR / entidade)
    chaves = CHAVES_JOIN[entidade]
    prefixo = PREFIXO_INEP[entidade]

    lag = [c for c in COLUNAS_LAG_OBRIGATORIO if c in gold.columns]
    sem_lag = [c for c in COLUNAS_SEM_LAG if c in gold.columns]
    if not lag and not sem_lag:
        raise AssertionError(f"{entidade}: nenhuma coluna de contexto disponível na Gold")

    out = alunos
    if lag:
        out = out.merge(
            _defasar(gold, chaves, lag, prefixo), on=chaves, how="left", validate="m:1"
        )
    if sem_lag:
        out = out.merge(
            _corrente(gold, chaves, sem_lag, prefixo), on=chaves, how="left", validate="m:1"
        )

    if lag:
        _logar_match(f"{rotulo} defasado", out, f"{prefixo}{lag[0]}{SUFIXO_LAG}")
    if sem_lag:
        _logar_match(f"{rotulo} corrente", out, f"{prefixo}{sem_lag[0]}")
    return out


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

    _logar_match("ATU", out, METRIC_RENAME["media_fundamental"])
    return out


def join_ibge(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto municipal do IBGE (``gold/populacao_municipios``).

    Sem defasagem: nada aqui mede a prova. Em 2023 o IBGE não publicou
    estimativa municipal, então ``ctx_ibge_populacao_residente`` fica nula
    naquelas linhas — ausência declarada pela Gold, não falha de match.
    """
    ibge = read_parquet(PROCESSED_DATA_DIR / ENTIDADE_POPULACAO)
    ibge_join = ibge.loc[:, [*CHAVES_IBGE, *COLS_IBGE]].rename(columns=IBGE_RENAME)

    out = alunos.merge(ibge_join, on=CHAVES_IBGE, how="left", validate="m:1")

    _logar_match("IBGE", out, IBGE_RENAME[IBGE_COL_MATCH])
    return out


def join_inep_municipio(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto municipal do INEP (``gold/municipio``).

    ``meta`` entra no mesmo ano — o INEP a publica antes da prova. Taxa,
    média, participação e nível entram do ano anterior: no ano corrente eles
    agregam a prova destes mesmos alunos.
    """
    return _join_inep(alunos, "municipio", "INEP município")


def join_inep_uf(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto estadual do INEP (``gold/ufs``), com a mesma regra."""
    return _join_inep(alunos, "ufs", "INEP UF")


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

    _logar_match("Atlas", out, ATLAS_RENAME["idhm"])
    return out


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

    _logar_match("FUNDEB município", out, "ctx_fundeb_nse_municipio")
    _logar_match("FUNDEB UF", out, "ctx_fundeb_nse_uf")
    return out


# Registro ordenado dos joins.
JOINS = (
    join_atu,
    join_ibge,
    join_inep_municipio,
    join_inep_uf,
    join_atlas,
    join_fundeb,
)


def run_join() -> None:
    """Lê ``aluno``, aplica ``JOINS`` em sequência e grava ``base_analitica``."""
    logger.info("Iniciando joins sobre {}...", ENTIDADE_ALUNO)
    alunos = read_parquet(PROCESSED_DATA_DIR / ENTIDADE_ALUNO)
    linhas = len(alunos)
    logger.info("{}: {:,} linhas x {} colunas", ENTIDADE_ALUNO, linhas, alunos.shape[1])

    for join_fn in JOINS:
        logger.info("Aplicando {}...", join_fn.__name__)
        alunos = join_fn(alunos)
        # validate="m:1" já barra o fan-out do lado direito; isto pega o resto
        # (filtro indevido, chave nula, join que virou inner por engano).
        if len(alunos) != linhas:
            raise AssertionError(
                f"{join_fn.__name__} alterou a contagem de linhas: {linhas:,} -> {len(alunos):,}"
            )

    colisoes = [c for c in alunos.columns if c.endswith(("_x", "_y"))]
    if colisoes:
        raise AssertionError(f"colunas colidiram no merge: {colisoes}")

    dest = PROCESSED_DATA_DIR / ENTIDADE_DESTINO
    write_parquet_partitioned(alunos, dest, "ano", overwrite_entity=True)
    logger.success(
        "{} gravada em {}: {:,} linhas x {} colunas",
        ENTIDADE_DESTINO,
        dest,
        len(alunos),
        alunos.shape[1],
    )


if __name__ == "__main__":
    run_join()
