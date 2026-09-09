"""Bronze layer: structural contract for Atlas do Desenvolvimento Humano.

Ingere o CSV do espelho público do Atlas como ele vem — 237 colunas, siglas
originais, as três coortes (1991, 2000, 2010) — sem renomear nem filtrar.
Seleção e tradução de nomes acontecem na Silver; aqui só entra o que a fonte
publicou, mais os metadados de ingestão.

O arquivo é baixado automaticamente por ``download.py``: não há passo manual.

Dialeto: separador ``;``, decimal ``,``, textos entre aspas (``DIALETO_BRONZE``
em ``schemas.py``). Ler com o dialeto errado não estoura na primeira linha — as
coortes têm quantidades diferentes de células vazias, então o parser atravessa
1991 inteiro e só quebra na virada para 2000. Por isso a conferência de colunas
logo após a leitura: é ela que transforma um ``ParserError`` no meio do arquivo
em uma mensagem que diz qual arquivo está errado.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, EXTERNAL_DATA_DIR
from src.preprocessing.atlas.schemas import (
    ARQUIVO_BRONZE,
    COLUNAS_IDENTIFICACAO,
    DIALETO_BRONZE,
    INDICADORES,
)
from src.preprocessing.io import write_parquet_partitioned

EXTERNAL_DIR = EXTERNAL_DATA_DIR / "atlas_desenvolvimento_humano"

COLUNA_PARTICAO = "ANO"


def _checar_arquivo(caminho) -> None:
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} não encontrado. Rode o download do Atlas "
            f"(`python -m src.preprocessing.atlas.download`) ou rode o pipeline "
            f"sem `--skip-download`."
        )


def _checar_colunas(df: pd.DataFrame, caminho) -> None:
    """Falha cedo e com nome próprio se o CSV não for o do Atlas."""
    esperadas = [*COLUNAS_IDENTIFICACAO, *INDICADORES]
    faltando = [c for c in esperadas if c not in df.columns]
    if faltando:
        raise AssertionError(
            f"{caminho} não tem as colunas do Atlas: {faltando[:5]}"
            f"{'...' if len(faltando) > 5 else ''} "
            f"({len(faltando)} de {len(esperadas)} ausentes). "
            f"Lido com sep='{DIALETO_BRONZE['sep']}' decimal='{DIALETO_BRONZE['decimal']}' "
            f"-> {df.shape[1]} colunas. Esperado: o CSV municipal do espelho do Atlas "
            f"(237 colunas, siglas como IDHM, T_ANALF11A14, PMPOB). "
            f"Apague o arquivo e rode o download de novo."
        )


def bronze_municipio(ingestion_ts) -> pd.DataFrame:
    caminho = EXTERNAL_DIR / ARQUIVO_BRONZE
    _checar_arquivo(caminho)
    df = pd.read_csv(caminho, **DIALETO_BRONZE)
    df.columns = [c.strip('"') for c in df.columns]
    _checar_colunas(df, caminho)
    # Concat em vez de duas atribuições: inserir coluna a coluna num frame de
    # 237 colunas fragmenta os blocos internos e o pandas avisa.
    meta = pd.DataFrame(
        {"_source_file": str(caminho), "_ingestion_timestamp": ingestion_ts},
        index=df.index,
    )
    return pd.concat([df, meta], axis=1)


def run_bronze() -> None:
    ingestion_ts = datetime.now(UTC)
    BRONZE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Bronze Atlas do Desenvolvimento Humano...")

    municipio = bronze_municipio(ingestion_ts)
    municipio[COLUNA_PARTICAO] = (
        pd.to_numeric(municipio[COLUNA_PARTICAO], errors="coerce").astype("Int64")
    )
    write_parquet_partitioned(
        municipio, BRONZE_DATA_DIR / "atlas_municipio", COLUNA_PARTICAO, overwrite_entity=True
    )
    logger.info(
        "atlas_municipio: {:,} linhas x {} colunas | coortes: {}",
        len(municipio),
        municipio.shape[1],
        sorted(municipio[COLUNA_PARTICAO].dropna().unique().tolist()),
    )

    logger.success("Camada Bronze Atlas concluída.")


if __name__ == "__main__":
    run_bronze()
