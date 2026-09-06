"""Orquestra left-joins de fontes externas sobre ``aluno`` -> ``base_analitica``.

Contrato de cada join
---------------------
Cada função recebe o DataFrame de alunos e devolve o mesmo enriquecido:

    def join_<fonte>(alunos: pd.DataFrame) -> pd.DataFrame: ...

Regras:
  - preservar 1 linha por aluno (merge how="left", validate="m:1");
  - prefixar colunas novas com a fonte (ex.: ctx_atu_*, ctx_ibge_*);
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
de 1º de julho sai antes da aplicação. O FUNDEB entra pela mesma porta, com a
ressalva de 2023 descrita em ``join_fundeb``.
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

# --- FUNDEB ----------------------------------------------------------------
ENTIDADE_FUNDEB = "nse_entes_federados"
CHAVES_FUNDEB_MUNICIPIO = ["ano", "id_municipio"]
CHAVES_FUNDEB_UF = ["ano", "id_uf"]
COL_NSE = "valor_nse"
FUNDEB_NSE_MUNICIPIO = "ctx_fundeb_nse_municipio"
FUNDEB_NSE_UF = "ctx_fundeb_nse_uf"

# --- INEP ------------------------------------------------------------------
PREFIXO_INEP = {"municipio": "ctx_inep_mun_", "ufs": "ctx_inep_uf_"}


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


def _nse_por_ente(nse: pd.DataFrame, tipo: str, chave: str, destino: str) -> pd.DataFrame:
    """Recorta o NSE de um tipo de ente e converte ``codigo_ente`` na chave do projeto.

    O FUNDEB publica município e UF na mesma tabela, distinguidos por ``tipo_ente``,
    e com o código IBGE num campo só. Aqui ele vira ``id_municipio`` (string de 7
    dígitos) ou ``id_uf`` (Int64) — os formatos que ``gold/aluno`` usa.

    Trocar os dois tipos NÃO passa em silêncio, e isso foi conferido: o pandas
    recusa ``merge`` entre chave ``string`` e ``Int64`` com ValueError. É o
    ``astype`` consistente das Golds que compra essa proteção — com ``object`` em
    vez de ``string`` o pandas coagiria e o merge casaria zero linhas calado.
    """
    recorte = nse.loc[nse["tipo_ente"] == tipo].copy()
    if chave == "id_municipio":
        recorte[chave] = recorte["codigo_ente"].astype("Int64").astype("string").str.zfill(7)
    else:
        recorte[chave] = pd.to_numeric(recorte["codigo_ente"], errors="coerce").astype("Int64")
    return recorte.loc[:, ["ano", chave, COL_NSE]].rename(columns={COL_NSE: destino})


def join_fundeb(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do Nível Socioeconômico do FUNDEB, por município e por UF.

    Sem defasagem: o NSE é um índice socioeconômico do ente federado, calculado
    para ratear o fundo. Não agrega, nem em parte, o resultado da avaliação destes
    alunos, então não há alvo voltando pela janela.

    **2023 fica nulo, de propósito.** O FUNDEB só publica NSE para 2024 e 2025.
    Preencher 2023 com o valor de 2024 daria ao modelo um número que ninguém
    mediu, com cara de medição. É exatamente a decisão que a Gold do IBGE já
    tomou para ``populacao_residente`` em 2023, e a razão é a mesma: nulo é a
    afirmação honesta de que o dado não existe. Quem quiser a hipótese do proxy
    que a teste explicitamente no ``features/``, com a flag à vista.

    Só ``valor_nse`` entra. ``ponderador_nse`` é rescala LINEAR dele
    (correlação de Pearson -1,0 exata; o resíduo de 5e-7 é o arredondamento em 6
    casas da fonte), logo é coluna derivada — a mesma regra que tirou
    ``porte_municipio`` e ``variacao_populacional_pct`` da Gold do IBGE. Levar as
    duas daria ao modelo duas colunas perfeitamente colineares.

    Em 2024 o match municipal fica em 98,8%, e os que faltam são dois, nominais:
    **Brasília (5300108)** e **Fernando de Noronha (2605459)**. Nenhum dos dois
    opera rede municipal própria — o DF entra no FUNDEB só como UF (código 53) e
    Noronha é distrito estadual de Pernambuco. Ausência correta, não falha de
    chave; os alunos deles ficam com ``ctx_fundeb_nse_uf`` preenchido e o
    municipal nulo.
    """
    nse = read_parquet(PROCESSED_DATA_DIR / ENTIDADE_FUNDEB)

    # A taxa de match do FUNDEB é 0% em 2023 e isso é o esperado, não um join
    # quebrado. Ao contrário do IBGE — onde sobra o ``area_km2`` para servir de
    # régua —, aqui a tabela inteira não existe naquele ano, então não há coluna
    # honesta para medir. Declarar a ausência ANTES do log de match é o que separa
    # "não existe dado" de "o merge falhou" para quem lê a saída depois.
    anos_com_nse = set(pd.to_numeric(nse["ano"], errors="coerce").dropna().astype(int))
    anos_alunos = set(pd.to_numeric(alunos["ano"], errors="coerce").dropna().astype(int))
    sem_nse = sorted(anos_alunos - anos_com_nse)
    if sem_nse:
        logger.info(
            "FUNDEB não publica NSE para {} — essas linhas ficam nulas por decisão, "
            "sem proxy. Match 0% nesses anos é ausência declarada.",
            sem_nse,
        )

    out = alunos.merge(
        _nse_por_ente(nse, "municipio", "id_municipio", FUNDEB_NSE_MUNICIPIO),
        on=CHAVES_FUNDEB_MUNICIPIO,
        how="left",
        validate="m:1",
    )
    out = out.merge(
        _nse_por_ente(nse, "uf", "id_uf", FUNDEB_NSE_UF),
        on=CHAVES_FUNDEB_UF,
        how="left",
        validate="m:1",
    )

    _logar_match("FUNDEB município", out, FUNDEB_NSE_MUNICIPIO)
    _logar_match("FUNDEB UF", out, FUNDEB_NSE_UF)
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


# Registro ordenado dos joins. Os três primeiros são contexto sem defasagem;
# os do INEP vêm por último porque são os únicos que mexem com o ano.
JOINS = (
    join_atu,
    join_ibge,
    join_fundeb,
    join_inep_municipio,
    join_inep_uf,
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
