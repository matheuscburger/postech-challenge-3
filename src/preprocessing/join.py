"""Orquestra left-joins de fontes externas sobre ``aluno`` -> ``base_analitica``.

Contrato de cada join
---------------------
Cada função recebe o DataFrame de alunos e devolve o mesmo enriquecido:

    def join_<fonte>(alunos: pd.DataFrame) -> pd.DataFrame: ...

Regras:
  - preservar 1 linha por aluno (merge how="left", validate="m:1");
  - prefixar colunas novas com a fonte (ex.: ctx_atu_*, ctx_ibge_*, ctx_atlas_*,
    ctx_fundeb_*);
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

O Atlas do Desenvolvimento Humano e o FUNDEB (NSE) também entram sem
defasagem, pelo mesmo motivo do IBGE: nenhum dos dois mede a prova destes
alunos.
  - Atlas: indicadores estruturais fixos no ano-base 2010 (Censo Demográfico).
    O join usa só ``id_municipio`` — o mesmo valor de 2010 é usado para todos
    os anos de ``aluno`` (2023-2025), assumindo que indicadores
    socioeconômicos municipais mudam devagar.
  - FUNDEB: Nível Socioeconômico (NSE) por ente federado. O INEP publica uma
    edição por exercício financeiro e existem duas — 2024 e 2025. **2023 fica
    nulo, sem proxy.** O NSE é medição refeita a cada edição, não atributo
    estrutural: entre 2024 e 2025 nenhum dos 5.568 municípios repete valor
    (|Δ| mediano de 7,3% de um desvio-padrão, p95 de 26%, máximo acima de um
    desvio). Carregar 2024 para trás inventaria um ponto da série — mesma
    regra que deixa ``populacao_residente`` nulo em 2023 na Gold do IBGE, e o
    oposto do que se faz com ``area_km2`` e com o Atlas, que não são séries.
    O NSE da UF entra como coluna separada (``ctx_fundeb_nse_uf``), além do
    NSE do município — não é usado como fallback.

Um ano por vez
--------------
``run_join`` processa uma partição de ``aluno`` por vez, não a base inteira.
São 5,3 milhões de alunos e 86 colunas no fim da cadeia: o frame completo passa
de 3 GB, e cada ``merge`` mantém o frame antigo e o novo vivos ao mesmo tempo,
então o pico dobra. Em WSL isso estoura a memória e o processo é morto no meio
do join — sem traceback, só a sessão caindo.

O recorte por ano é exato, não uma aproximação: todo join aqui é left-join por
chaves que ou incluem ``ano`` ou independem dele (Atlas), e ``validate="m:1"``
olha a unicidade do lado direito, que não é fatiado. Partição a partição dá o
mesmo resultado com um terço do pico, e ``base_analitica`` já é gravada
particionada por ano de qualquer forma.
"""

from __future__ import annotations

import gc

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
from src.preprocessing.io import (
    list_partition_values,
    read_parquet,
    write_parquet_partitioned,
)

ENTIDADE_ALUNO = "aluno"
ENTIDADE_DESTINO = "base_analitica"

SUFIXO_LAG = "_lag1"

# --- Censo Escolar (ATU) ---------------------------------------------------
MAP_DEP_ALUNO_ATU = {1: "Federal", 2: "Estadual", 3: "Municipal", 4: "Privada"}
METRIC_RENAME = {c: f"ctx_atu_{c.removeprefix('media_')}" for c in METRIC_COLS}
JOIN_KEYS = ["ano", "id_municipio", "_dep_atu"]

# --- IBGE ------------------------------------------------------------------
CHAVES_IBGE = ["ano", "id_municipio"]
IDENT_IBGE = ["nome_municipio", "id_uf", "sigla_uf"]
COLS_IBGE = [c for c in IBGE_GOLD_COLS if c not in {*CHAVES_IBGE, *IDENT_IBGE}]
IBGE_RENAME = {c: f"ctx_ibge_{c}" for c in COLS_IBGE}
IBGE_COL_MATCH = "area_km2"

# --- INEP ------------------------------------------------------------------
PREFIXO_INEP = {"municipio": "ctx_inep_mun_", "ufs": "ctx_inep_uf_"}

# --- Atlas do Desenvolvimento Humano ---------------------------------------
ATLAS_ENTIDADE = "atlas_desenvolvimento_humano"
# Lista expandida em 04/09/2026 (ver src/preprocessing/atlas/schemas.py para
# a fonte e a justificativa de cada indicador novo — foco em saúde da
# infância, trabalho infantil, frequência escolar por faixa etária e
# capital educacional dos pais/responsáveis).
ATLAS_COLS = [
    "idhm",
    "idhm_educacao",
    "idhm_renda",
    "idhm_longevidade",
    "taxa_analfabetismo_11a14",
    "taxa_analfabetismo_15a17",
    "taxa_analfabetismo_15mais",
    "taxa_frequencia_6a14",
    "taxa_frequencia_4a5",
    "taxa_frequencia_0a3",
    "expectativa_anos_estudo",
    "taxa_fundamental_incompleto",
    "renda_per_capita",
    "indice_gini",
    "indice_theil",
    "razao_10_ricos_40_pobres",
    "percentual_pobres",
    "percentual_extremamente_pobres",
    "percentual_vulneraveis_pobreza",
    "percentual_pobres_criancas",
    "percentual_extremamente_pobres_criancas",
    "percentual_vulneraveis_pobreza_criancas",
    "mortalidade_ate_1_ano",
    "mortalidade_ate_5_anos",
    "taxa_trabalho_infantil_10a14",
    "taxa_maes_10a14",
    "taxa_maes_chefes_familia",
    "taxa_fora_escola_4a5",
    "taxa_fora_escola_6a14",
    "taxa_frequencia_liquida_fundamental",
    "taxa_domicilios_vulneraveis_sem_fundamental",
    "taxa_criancas_em_domicilios_sem_fundamental",
    "percentual_domicilios_agua",
    "percentual_domicilios_energia",
    "taxa_densidade_domiciliar",
]
ATLAS_RENAME = {c: f"ctx_atlas_{c}" for c in ATLAS_COLS}
ATLAS_COL_MATCH = ATLAS_RENAME["idhm"]

# --- FUNDEB (NSE) ------------------------------------------------------------
FUNDEB_ENTIDADE = "nse_entes_federados"
COL_NSE_MUNICIPIO = "ctx_fundeb_nse_municipio"
COL_NSE_UF = "ctx_fundeb_nse_uf"


# Taxas de match acumuladas entre os chunks. O contrato de cada join é
# ``f(alunos) -> DataFrame``, sem parâmetro extra, então a consolidação dos anos
# passa por aqui em vez de entrar na assinatura de todo mundo.
_MATCH_ACUMULADO: dict[str, list[int]] = {}


def _logar_match(rotulo: str, out: pd.DataFrame, coluna: str) -> None:
    """Taxa de match do chunk, somando no acumulado que ``run_join`` consolida.

    A quebra por ano é o que expõe lag vazio; como cada chunk é um ano, ela sai
    naturalmente — uma linha por join por ano.
    """
    chave = f"{rotulo} ({coluna})"
    casados = int(out[coluna].notna().sum())
    total = len(out)

    acumulado = _MATCH_ACUMULADO.setdefault(chave, [0, 0])
    acumulado[0] += casados
    acumulado[1] += total

    logger.info("    match {} : {:.2%}", chave, casados / total if total else 0.0)


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


def _com_chave_municipio(alunos: pd.DataFrame) -> pd.DataFrame:
    """``alunos`` com ``id_municipio`` normalizado — sem copiar se já estiver.

    ``gold/aluno`` publica a coluna como string de 7 dígitos, então o caminho
    normal é não copiar nada e não realocar array de string nenhum. A
    normalização continua como rede para quem chamar o join com um frame de
    outra origem — só que agora ela custa uma varredura de inteiros em vez de
    reconstruir 2 milhões de strings e duplicar o frame, duas vezes por chunk
    (Atlas e FUNDEB). Era esse par de cópias que estourava a memória no meio da
    cadeia, quando o frame já passou de 40 colunas.
    """
    ids = alunos["id_municipio"]
    if ids.dtype == "string" and bool(ids.str.len().eq(7).all()):
        return alunos
    return alunos.assign(id_municipio=ids.astype("string").str.zfill(7))


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

    out = alunos.assign(_dep_atu=alunos["dependencia_administrativa"].map(MAP_DEP_ALUNO_ATU))
    out = out.merge(atu_join, on=JOIN_KEYS, how="left", validate="m:1")
    out = out.drop(columns=["_dep_atu"])

    _logar_match("ATU", out, METRIC_RENAME["media_fundamental"])
    return out


def join_atlas(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join dos indicadores municipais do Atlas do Desenvolvimento Humano.

    Sem defasagem: nada aqui mede a prova. O Atlas está fixo no ano-base 2010
    (Censo Demográfico) — o join usa só ``id_municipio``, e o mesmo valor de
    2010 é replicado para todos os anos de ``alunos``.
    """
    atlas_path = PROCESSED_DATA_DIR / ATLAS_ENTIDADE
    if not atlas_path.exists():
        logger.error(f"Arquivo {atlas_path} não encontrado, retornando alunos sem join do Atlas.")
        return alunos

    atlas = read_parquet(atlas_path)
    atlas_join = (
        atlas.loc[:, ["id_municipio", *ATLAS_COLS]]
        .rename(columns=ATLAS_RENAME)
        .copy()
    )
    atlas_join["id_municipio"] = atlas_join["id_municipio"].astype("string").str.zfill(7)

    out = _com_chave_municipio(alunos)
    out = out.merge(atlas_join, on="id_municipio", how="left", validate="m:1")

    _logar_match("Atlas", out, ATLAS_COL_MATCH)
    return out


def _preparar_nse_municipio(nse: pd.DataFrame) -> pd.DataFrame:
    """Filtra ``tipo_ente == 'municipio'`` e renomeia para o prefixo da fonte.

    Sem proxy: o ano que o FUNDEB não publicou simplesmente não tem linha aqui,
    e o left-join deixa nulo.
    """
    nse_mun = nse.loc[nse["tipo_ente"] == "municipio"].copy()
    nse_mun["id_municipio"] = nse_mun["codigo_ente"].astype("Int64").astype("string").str.zfill(7)

    return nse_mun[["ano", "id_municipio", "valor_nse", "ponderador_nse"]].rename(
        columns={
            "valor_nse": COL_NSE_MUNICIPIO,
            "ponderador_nse": "ctx_fundeb_ponderador_nse_municipio",
        }
    )


def _preparar_nse_uf(nse: pd.DataFrame) -> pd.DataFrame:
    """Filtra ``tipo_ente == 'uf'`` e renomeia para o prefixo da fonte.

    ``codigo_ente`` já é Int64 para UF (ex.: 11, 35) — mesmo tipo de
    ``id_uf`` em ``gold/aluno``, então não há zero-padding aqui (diferente de
    município, que é sempre string de 7 dígitos). Sem proxy, como o município.
    """
    nse_uf = nse.loc[nse["tipo_ente"] == "uf"].copy()
    nse_uf["id_uf"] = nse_uf["codigo_ente"].astype("Int64")

    return nse_uf[["ano", "id_uf", "valor_nse", "ponderador_nse"]].rename(
        columns={
            "valor_nse": COL_NSE_UF,
            "ponderador_nse": "ctx_fundeb_ponderador_nse_uf",
        }
    )


def _anos_sem_nse(out: pd.DataFrame, nse: pd.DataFrame, coluna: str, rotulo: str) -> list[int]:
    """Anos que o FUNDEB não publicou têm de sair nulos — e continuar nulos.

    Análogo ao ``populacao_imputada_em_ano_sem_estimativa`` da Gold do IBGE:
    existe para que reintroduzir um proxy pare o pipeline, em vez de passar
    despercebido como um número plausível na coluna certa. Devolve os anos sem
    NSE para quem quiser logar.
    """
    publicados = set(pd.to_numeric(nse["ano"], errors="coerce").dropna().astype(int))
    presentes = set(pd.to_numeric(out["ano"], errors="coerce").dropna().astype(int))

    sem_nse = sorted(presentes - publicados)
    for ano in sem_nse:
        imputados = int(out.loc[out["ano"] == ano, coluna].notna().sum())
        if imputados:
            raise AssertionError(
                f"{rotulo}: {imputados:,} linhas de {ano} com NSE preenchido, mas o FUNDEB "
                f"não publicou NSE para {ano} (edições: {sorted(publicados)}). "
                f"Carregar outro ano para trás inventaria um ponto da série."
            )
    return sem_nse


def join_fundeb(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do NSE do FUNDEB (município e UF) em ``alunos``.

    Sem defasagem: o NSE é uma classificação socioeconômica do ente, não uma
    medição da prova. E **sem proxy**: o INEP publica uma edição por exercício
    financeiro, existem duas (2024 e 2025), e 2023 fica nulo. Ver a seção do
    FUNDEB no topo do módulo para a medição que sustenta essa decisão.
    """
    nse = read_parquet(PROCESSED_DATA_DIR / FUNDEB_ENTIDADE)
    nse_mun = _preparar_nse_municipio(nse)
    nse_uf = _preparar_nse_uf(nse)

    out = _com_chave_municipio(alunos)

    out = out.merge(nse_mun, on=["ano", "id_municipio"], how="left", validate="m:1")
    out = out.merge(nse_uf, on=["ano", "id_uf"], how="left", validate="m:1")

    # Antes do log de match, para que 0% não seja lido como merge quebrado.
    sem_nse = _anos_sem_nse(out, nse, COL_NSE_MUNICIPIO, "FUNDEB município")
    _anos_sem_nse(out, nse, COL_NSE_UF, "FUNDEB UF")
    if sem_nse:
        logger.info(
            "    FUNDEB não publicou NSE para {} — contexto nulo por decisão, não falha de merge",
            sem_nse,
        )

    _logar_match("FUNDEB município", out, COL_NSE_MUNICIPIO)
    _logar_match("FUNDEB UF", out, COL_NSE_UF)
    return out


def join_ibge(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto municipal do IBGE (``gold/populacao_municipios``).

    Sem defasagem: nada ali mede a prova. Em 2023 o IBGE não publicou
    estimativa municipal, então ``ctx_ibge_populacao_residente`` fica nula
    naquelas linhas — ausência declarada pela Gold, não falha de match.
    """
    ibge = read_parquet(PROCESSED_DATA_DIR / ENTIDADE_POPULACAO)
    ibge_join = ibge.loc[:, [*CHAVES_IBGE, *COLS_IBGE]].rename(columns=IBGE_RENAME)

    out = alunos.merge(ibge_join, on=CHAVES_IBGE, how="left", validate="m:1")

    _logar_match("IBGE", out, IBGE_RENAME[IBGE_COL_MATCH])
    return out


def join_inep_municipio(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto municipal do INEP (``gold/municipio``)."""
    return _join_inep(alunos, "municipio", "INEP município")


def join_inep_uf(alunos: pd.DataFrame) -> pd.DataFrame:
    """Left-join do contexto estadual do INEP (``gold/ufs``), com a mesma regra."""
    return _join_inep(alunos, "ufs", "INEP UF")


# Registro ordenado dos joins.
JOINS = (
    join_atu,
    join_atlas,
    join_fundeb,
    join_ibge,
    join_inep_municipio,
    join_inep_uf,
)


def _aplicar_joins(alunos: pd.DataFrame, rotulo: str) -> pd.DataFrame:
    """Aplica ``JOINS`` em sequência, exigindo 1 linha por aluno no caminho todo."""
    linhas = len(alunos)
    for join_fn in JOINS:
        logger.info("  aplicando {}...", join_fn.__name__)
        alunos = join_fn(alunos)
        if len(alunos) != linhas:
            raise AssertionError(
                f"{join_fn.__name__} alterou a contagem de linhas em {rotulo}: "
                f"{linhas:,} -> {len(alunos):,}"
            )

    colisoes = [c for c in alunos.columns if c.endswith(("_x", "_y"))]
    if colisoes:
        raise AssertionError(f"colunas colidiram no merge ({rotulo}): {colisoes}")
    return alunos


def _chunks(origem) -> list[tuple[str, object]]:
    """Uma partição de ano por chunk; a base inteira se não houver partição."""
    anos = sorted(list_partition_values(origem, "ano"))
    if anos:
        return [(f"ano={ano}", origem / f"ano={ano}") for ano in anos]
    logger.warning("{} não está particionado por ano; processando de uma vez.", origem)
    return [("base inteira", origem)]


def run_join() -> None:
    """Lê ``aluno`` ano a ano, aplica ``JOINS`` e grava ``base_analitica``.

    Um chunk por vez — ver "Um ano por vez" no topo do módulo para o porquê.
    """
    origem = PROCESSED_DATA_DIR / ENTIDADE_ALUNO
    dest = PROCESSED_DATA_DIR / ENTIDADE_DESTINO
    chunks = _chunks(origem)
    _MATCH_ACUMULADO.clear()

    logger.info(
        "Iniciando joins sobre {} em {} chunk(s): {}",
        ENTIDADE_ALUNO,
        len(chunks),
        [rotulo for rotulo, _ in chunks],
    )

    total_linhas = 0
    total_colunas = 0
    for indice, (rotulo, caminho) in enumerate(chunks):
        alunos = read_parquet(caminho)
        logger.info("[{}] {:,} linhas x {} colunas", rotulo, len(alunos), alunos.shape[1])

        alunos = _aplicar_joins(alunos, rotulo)

        # overwrite_entity só no primeiro chunk: limpa partição órfã de execução
        # anterior sem apagar o que este mesmo loop já gravou.
        write_parquet_partitioned(alunos, dest, "ano", overwrite_entity=(indice == 0))

        total_linhas += len(alunos)
        total_colunas = alunos.shape[1]
        logger.info("[{}] gravado: {:,} linhas x {} colunas", rotulo, len(alunos), total_colunas)

        del alunos
        gc.collect()

    logger.info("Taxa de match consolidada:")
    for chave, (casados, total) in _MATCH_ACUMULADO.items():
        logger.info("    {:<44} : {:.2%}", chave, casados / total if total else 0.0)

    logger.success(
        "{} gravada em {}: {:,} linhas x {} colunas",
        ENTIDADE_DESTINO,
        dest,
        total_linhas,
        total_colunas,
    )


if __name__ == "__main__":
    run_join()
