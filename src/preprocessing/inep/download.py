"""Download INEP microdata and metas, then extract CSVs into data/raw."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import shutil
import time
import zipfile

from loguru import logger
import requests
from requests.exceptions import RequestException
import urllib3

from src.config import EXTERNAL_DATA_DIR, RAW_DATA_DIR
from src.config import ANOS, MAX_DOWNLOAD_ATTEMPTS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ARQUIVOS_ALVO = [
    "DADOS/TS_ALUNO.csv",
    "DADOS/TS_ESTADO.csv",
    "DADOS/TS_MUNICIPIO.csv",
]

MICRODADOS_INEP = {
    2023: [
        "https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2023.zip"
    ],
    2024: [
        "https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2024.zip"
    ],
    2025: ["https://download.inep.gov.br/dados_abertos/microdados_AEEB_2025.zip"],
}

METAS_INEP = {
    2023: [
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_municipios.xlsx",
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_ufs.xlsx",
    ],
    2024: [
        "https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_municipios_2024.xlsx",
        "https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_ufs_2024_2.xlsx",
    ],
    2025: [
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_municipios_2025_v2.xlsx",
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_ufs_2025_v1.xlsx",
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _destino(base: Path, ano: int, nome_arquivo: str) -> Path:
    pasta = base / str(ano)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / nome_arquivo


def baixar_arquivo(url: str, destino: Path, espera: int = 5) -> Path:
    """Download ``url`` to ``destino`` with retries."""
    logger.info(f"Transferindo {url} -> {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            with requests.get(
                url,
                headers=HEADERS,
                stream=True,
                timeout=(30, 300),
                verify=False,
            ) as resposta:
                resposta.raise_for_status()
                with destino.open("wb") as saida:
                    for chunk in resposta.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            saida.write(chunk)
            logger.info(f"Transferência concluída: {destino}")
            return destino
        except RequestException as erro:
            if tentativa == MAX_DOWNLOAD_ATTEMPTS:
                logger.error(f"Falha após {MAX_DOWNLOAD_ATTEMPTS} tentativas: {url} -> {destino}")
                raise
            logger.warning(
                f"Tentativa {tentativa}/{MAX_DOWNLOAD_ATTEMPTS} falhou ({erro}). "
                f"Retry em {espera}s..."
            )
            time.sleep(espera)
    raise RuntimeError(f"Download falhou: {url}")


def baixar_lista(ano_to_url: dict[int, list[str]], base: Path) -> dict[int, list[Path]]:
    paths: dict[int, list[Path]] = defaultdict(list)
    for ano, urls in ano_to_url.items():
        if ano not in ANOS:
            continue
        for url in urls:
            nome_arquivo = url.split("/")[-1]
            logger.info(f"Ano {ano}:")
            destino = _destino(base, ano, nome_arquivo)
            baixar_arquivo(url, destino)
            paths[ano].append(destino)
    return paths


def _membro_zip(arquivo_zip: zipfile.ZipFile, alvo: str) -> str:
    nomes = [n.replace("\\", "/") for n in arquivo_zip.namelist()]
    original = dict(zip(nomes, arquivo_zip.namelist(), strict=False))
    if alvo in original:
        return original[alvo]
    basename = alvo.rsplit("/", 1)[-1].upper()
    matches = [n for n in nomes if n.upper().endswith("/" + basename) or n.upper() == basename]
    if not matches:
        raise FileNotFoundError(f"{alvo} não encontrado no ZIP")
    dados = [m for m in matches if "DADOS" in m.upper()]
    escolhido = dados[0] if dados else matches[0]
    return original[escolhido]


def descompactar(
    zips_por_ano: dict[int, list[Path]],
    destino_base: Path,
    arquivos_alvo: list[str] = ARQUIVOS_ALVO,
) -> dict[int, list[Path]]:
    """Extract the contracted CSVs from each INEP zip into data/raw/{ano}/."""
    output_paths: dict[int, list[Path]] = defaultdict(list)
    for ano, zips in zips_por_ano.items():
        for zip_path in zips:
            with zipfile.ZipFile(zip_path) as arquivo_zip:
                for alvo in arquivos_alvo:
                    membro = _membro_zip(arquivo_zip, alvo)
                    basename = Path(membro.replace("\\", "/")).name
                    destino = _destino(destino_base, ano, basename)
                    with arquivo_zip.open(membro) as fonte, destino.open("wb") as saida:
                        shutil.copyfileobj(fonte, saida)
                    logger.info(f"{alvo} extraído (ano {ano}) -> {destino}")
                    output_paths[ano].append(destino)
    return output_paths


def baixar_dados_inep() -> None:
    """Download ZIPs to data/external and extract CSVs/XLSX into data/raw."""
    logger.info("Iniciando extração dos arquivos do INEP...")
    EXTERNAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Baixando microdados (ZIP) para data/external...")
    zip_paths = baixar_lista(MICRODADOS_INEP, EXTERNAL_DATA_DIR)
    logger.info(
        "ZIPs baixados: {}",
        json.dumps({k: [str(p) for p in v] for k, v in zip_paths.items()}, indent=4),
    )

    logger.info("Extraindo CSVs dos microdados para data/raw...")
    csv_paths = descompactar(zip_paths, RAW_DATA_DIR, ARQUIVOS_ALVO)
    logger.info(
        "CSVs extraídos: {}",
        json.dumps({k: [str(p) for p in v] for k, v in csv_paths.items()}, indent=4),
    )

    logger.info("Baixando planilhas de metas para data/raw...")
    metas_paths = baixar_lista(METAS_INEP, RAW_DATA_DIR)
    logger.info(
        "Metas baixadas: {}",
        json.dumps({k: [str(p) for p in v] for k, v in metas_paths.items()}, indent=4),
    )
    logger.success("Extração dos arquivos do INEP concluída.")


if __name__ == "__main__":
    baixar_dados_inep()
