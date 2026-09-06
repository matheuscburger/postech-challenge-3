"""Download layer: Atlas do Desenvolvimento Humano.

O Atlas não tem API: o dado é publicado como planilha em ``atlasbrasil.org.br``,
que bloqueia acesso automatizado. As duas saídas eram:

  - **Base dos Dados** (dataset ``mundo_onu.adh``) — distribui o dado por
    BigQuery, o que exige conta Google Cloud autenticada e billing project por
    pessoa (`pip install basedosdados`). Não é download HTTP, então virava um
    passo manual por colega, e um CSV com o dialeto errado colocado no lugar
    passava batido pela checagem de existência e só quebrava na Bronze.
  - **Espelho público em CSV** (``github.com/mauriciocramos/IDHM``) — réplica
    fiel do mesmo arquivo do PNUD/IPEA/FJP, baixável por HTTP simples, sem
    conta e sem token. Traz as 237 colunas com as siglas originais do Atlas e
    as três coortes do índice (1991, 2000, 2010).

Este módulo usa o espelho: o pipeline do Atlas roda de ponta a ponta em
qualquer máquina, sem passo manual, igual às outras fontes do projeto.
"""

from __future__ import annotations

from pathlib import Path
import time

from loguru import logger
import requests
from requests.exceptions import RequestException

from src.config import EXTERNAL_DATA_DIR, MAX_DOWNLOAD_ATTEMPTS
from src.preprocessing.atlas.schemas import ARQUIVO_BRONZE

EXTERNAL_DIR = EXTERNAL_DATA_DIR / "atlas_desenvolvimento_humano"

URL_ATLAS_MUNICIPAL = "https://raw.githubusercontent.com/mauriciocramos/IDHM/master/municipal.csv"


def _baixar_com_retry(url: str, destino: Path, espera: int = 5) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    for tentativa in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 300)) as resposta:
                resposta.raise_for_status()
                with destino.open("wb") as saida:
                    for chunk in resposta.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            saida.write(chunk)
            logger.info("Transferência concluída: {}", destino)
            return destino
        except RequestException as erro:
            if tentativa == MAX_DOWNLOAD_ATTEMPTS:
                logger.error(
                    "Falha após {} tentativas: {} -> {}", MAX_DOWNLOAD_ATTEMPTS, url, destino
                )
                raise
            logger.warning(
                "Tentativa {}/{} falhou ({}). Retry em {}s...",
                tentativa, MAX_DOWNLOAD_ATTEMPTS, erro, espera,
            )
            time.sleep(espera)
    raise RuntimeError(f"Download falhou: {url}")


def baixar_municipal_atlas() -> Path:
    """Baixa o CSV municipal do Atlas a partir do espelho público."""
    destino = EXTERNAL_DIR / ARQUIVO_BRONZE
    logger.info("Baixando Atlas municipal de {} -> {}", URL_ATLAS_MUNICIPAL, destino)
    return _baixar_com_retry(URL_ATLAS_MUNICIPAL, destino)


def baixar_dados_atlas() -> None:
    """Etapa de download do Atlas: um arquivo, automático."""
    logger.info("Iniciando etapa de download do Atlas do Desenvolvimento Humano...")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    baixar_municipal_atlas()

    logger.success("Etapa de download do Atlas concluída.")


if __name__ == "__main__":
    baixar_dados_atlas()
