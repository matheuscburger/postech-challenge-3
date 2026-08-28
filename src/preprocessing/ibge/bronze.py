"""Bronze layer: structural contract + Parquet conversion for the IBGE API responses.

A resposta da API de agregados vem aninhada e no formato longo. A Bronze normaliza esse
aninhamento para uma tabela longa e aplica o contrato de tipos — sem pivotar. O pivot
para largo é responsabilidade da Silver.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import shutil
from typing import Any

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, RAW_DATA_DIR
from src.preprocessing.ibge.download import caminho_serie
from src.preprocessing.ibge.schemas import (
    API_JOBS,
    SCHEMA_SERIE_LONGA,
    SENTINELAS_SIDRA,
    ApiJob,
)
from src.preprocessing.io import (
    apply_schema,
    list_partition_values,
    read_parquet,
    write_parquet_partitioned,
)


def _checar_anos(job: ApiJob, partition_col: str) -> None:
    """Confere as partições contra os períodos declarados NO JOB, não contra config.ANOS.

    Cada agregado tem sua própria janela — a de população começa em 2024 —, então cobrar
    config.ANOS aqui quebraria por um ano que a fonte simplesmente não publica.
    """
    presentes = list_partition_values(BRONZE_DATA_DIR / job.entidade, partition_col)
    faltando = set(job.periodos) - presentes
    if faltando:
        raise ValueError(
            f"{job.entidade}: anos esperados ausentes -> {sorted(faltando)} "
            f"(presentes: {sorted(presentes)})"
        )
    logger.info("{}: anos OK -> {}", job.entidade, sorted(presentes))


def _exigir(obj: Any, chave: str, contexto: str) -> Any:
    """Acesso a chave com erro que diz o que veio, em vez de KeyError seco."""
    if not isinstance(obj, dict) or chave not in obj:
        recebido = sorted(obj) if isinstance(obj, dict) else type(obj).__name__
        raise AssertionError(
            f"{contexto}: chave '{chave}' ausente na resposta da API. Recebido: {recebido}"
        )
    return obj[chave]


def normalizar_resposta(payload: Any, ano: int, entidade: str) -> pd.DataFrame:
    """Achata a resposta da API de agregados numa tabela longa.

    Formato esperado (API de agregados v3)::

        [{"id": "...", "variavel": "...", "unidade": "...",
          "resultados": [{"classificacoes": [],
                          "series": [{"localidade": {"id", "nivel", "nome"},
                                      "serie": {"2024": "22853"}}]}]}]
    """
    if not isinstance(payload, list):
        recebido = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise AssertionError(
            f"{entidade}: resposta da API fora do formato de lista. Recebido: {recebido}"
        )
    if not payload:
        raise AssertionError(
            f"{entidade} ({ano}): a API respondeu com uma lista vazia. Confira o agregado, "
            f"a variável e os períodos com: python -m src.preprocessing.ibge.download "
            f"--inspecionar"
        )

    alvo = str(ano)
    linhas: list[dict] = []

    for bloco in payload:
        ctx = f"{entidade}/variavel"
        id_variavel = _exigir(bloco, "id", ctx)
        no_variavel = _exigir(bloco, "variavel", ctx)
        no_unidade = bloco.get("unidade")

        for resultado in _exigir(bloco, "resultados", ctx):
            for serie in _exigir(resultado, "series", f"{ctx}/resultados"):
                localidade = _exigir(serie, "localidade", f"{ctx}/series")
                valores = _exigir(serie, "serie", f"{ctx}/series")
                nivel = (localidade.get("nivel") or {}).get("id")
                if alvo not in valores:
                    continue
                linhas.append(
                    {
                        "NU_ANO": alvo,
                        "CO_LOCALIDADE": localidade.get("id"),
                        "NO_LOCALIDADE": localidade.get("nome"),
                        "CO_NIVEL": nivel,
                        "CO_VARIAVEL": id_variavel,
                        "NO_VARIAVEL": no_variavel,
                        "NO_UNIDADE": no_unidade,
                        "VL_MEDIDA": valores[alvo],
                    }
                )

    if not linhas:
        raise AssertionError(f"{entidade}: nenhuma série retornada para o período {ano}.")
    return pd.DataFrame(linhas)


def _log_sentinelas(entidade: str, ano: int, bruto: pd.Series) -> None:
    """Conta os valores especiais do SIDRA antes do cast, para não sumirem em silêncio."""
    texto = bruto.astype("string").str.strip()
    achados = {s: int((texto == s).sum()) for s in SENTINELAS_SIDRA if s}
    achados = {k: v for k, v in achados.items() if v}
    if achados:
        logger.warning(
            "{} {}: valores especiais do SIDRA convertidos em nulo -> {}", entidade, ano, achados
        )


def bronze_api(job: ApiJob, ingestion_ts) -> None:
    dest = BRONZE_DATA_DIR / job.entidade
    if dest.exists():
        shutil.rmtree(dest)

    for ano in job.periodos:
        caminho = caminho_serie(job.entidade, ano)
        if not caminho.exists():
            raise FileNotFoundError(
                f"{job.entidade} ({ano}) não encontrado: {caminho}. "
                "Rode sem --skip-download pelo menos uma vez."
            )

        payload = json.loads(caminho.read_text(encoding="utf-8"))
        bruto = normalizar_resposta(payload, ano, job.entidade)
        _log_sentinelas(job.entidade, ano, bruto["VL_MEDIDA"])

        df = apply_schema(bruto, SCHEMA_SERIE_LONGA)
        df["_source_file"] = str(caminho)
        df["_ingestion_timestamp"] = ingestion_ts
        df = df.loc[df["NU_ANO"].notna()].copy()

        write_parquet_partitioned(df, dest, "NU_ANO")
        logger.info("{} {}: {:,} linhas", job.entidade, ano, len(df))
        del df, bruto, payload


def run_bronze() -> None:
    ingestion_ts = datetime.now(UTC)
    BRONZE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Bronze IBGE...")
    logger.info("RAW_DATA_DIR    : {}", RAW_DATA_DIR)
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)

    logger.info("Ingerindo séries da API para a Bronze...")
    for job in API_JOBS:
        bronze_api(job, ingestion_ts)

    for job in API_JOBS:
        _checar_anos(job, "NU_ANO")
        df = read_parquet(BRONZE_DATA_DIR / job.entidade)
        niveis = sorted(df["CO_NIVEL"].dropna().unique().tolist())
        logger.info(
            "{}: {:,} linhas | {} colunas | níveis {}",
            job.entidade,
            len(df),
            len(df.columns),
            niveis,
        )
        del df

    logger.success("Camada Bronze IBGE concluída.")


if __name__ == "__main__":
    run_bronze()
