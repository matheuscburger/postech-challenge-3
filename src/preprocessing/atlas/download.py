"""Download layer: Atlas do Desenvolvimento Humano.

Diferente das outras fontes (INEP, FUNDEB, Censo Escolar, IBGE), o Atlas não
tem um único endpoint automatizável para todo o dado necessário:

  - `municipal_raw.csv` (usado só para nome_municipio) — é uma réplica
    pública em CSV no GitHub, **baixável automaticamente** via HTTP.
  - `municipio_raw.csv` (fonte primária dos 35 indicadores, Base dos Dados
    / dataset mundo_onu.adh) — a Base dos Dados distribui esse dado via
    BigQuery, o que exige uma conta Google Cloud autenticada por pessoa
    (`pip install basedosdados` + billing project). Não é um download HTTP
    simples, e pedir que cada colega configure uma conta GCP só para rodar
    este pipeline localmente não vale o custo — por isso esse arquivo
    continua sendo um passo manual, documentado no README principal.

Este módulo automatiza o que dá para automatizar (o CSV legado do GitHub) e
falha de forma clara e acionável quando o arquivo manual não está presente,
em vez de falhar silenciosamente lá na frente, na camada bronze.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
import requests
from requests.exceptions import RequestException

from src.config import EXTERNAL_DATA_DIR, MAX_DOWNLOAD_ATTEMPTS
import time

EXTERNAL_DIR = EXTERNAL_DATA_DIR / "atlas_desenvolvimento_humano"

URL_MUNICIPAL_LEGADO = "https://raw.githubusercontent.com/mauriciocramos/IDHM/master/municipal.csv"

INSTRUCOES_MUNICIPIO_RAW = f"""
{EXTERNAL_DIR / "municipio_raw.csv"} não encontrado.

Esse arquivo (fonte primária dos indicadores do Atlas) vem da Base dos
Dados (basedosdados.org, dataset mundo_onu.adh), que distribui os dados via
BigQuery — exige uma conta Google Cloud autenticada, então não dá para
baixar automaticamente aqui.

Passo a passo para obter manualmente:
  1. Acesse https://basedosdados.org/dataset/mundo-onu-adh
  2. Baixe a tabela "municipio" (ou rode a query via `pip install basedosdados`,
     ver documentação do pacote para autenticação)
  3. Salve o arquivo como municipio_raw.csv
  4. Coloque em: {EXTERNAL_DIR}

Ver também a seção "Atlas do Desenvolvimento Humano" no README principal do
projeto para o passo a passo completo.
""".strip()


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
                logger.error("Falha após {} tentativas: {} -> {}", MAX_DOWNLOAD_ATTEMPTS, url, destino)
                raise
            logger.warning(
                "Tentativa {}/{} falhou ({}). Retry em {}s...",
                tentativa, MAX_DOWNLOAD_ATTEMPTS, erro, espera,
            )
            time.sleep(espera)
    raise RuntimeError(f"Download falhou: {url}")


def baixar_municipal_legado() -> Path:
    """Baixa automaticamente o CSV legado (usado só para nome_municipio)."""
    destino = EXTERNAL_DIR / "municipal_raw.csv"
    logger.info("Baixando fonte legada (nome_municipio) de {} -> {}", URL_MUNICIPAL_LEGADO, destino)
    return _baixar_com_retry(URL_MUNICIPAL_LEGADO, destino)


def verificar_municipio_raw() -> None:
    """Verifica se o arquivo manual (Base dos Dados) já foi colocado; se não, orienta."""
    destino = EXTERNAL_DIR / "municipio_raw.csv"
    if not destino.exists():
        raise FileNotFoundError(INSTRUCOES_MUNICIPIO_RAW)
    logger.info("municipio_raw.csv encontrado: {}", destino)


def baixar_dados_atlas() -> None:
    """Orquestra a etapa de download: automatiza o que dá, valida o que é manual."""
    logger.info("Iniciando etapa de download do Atlas do Desenvolvimento Humano...")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    baixar_municipal_legado()
    verificar_municipio_raw()

    logger.success("Etapa de download do Atlas concluída (1 automático, 1 manual verificado).")


if __name__ == "__main__":
    baixar_dados_atlas()
