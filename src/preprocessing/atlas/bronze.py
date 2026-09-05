"""Bronze layer: structural contract for Atlas do Desenvolvimento Humano.

Diferente das outras fontes (INEP, FUNDEB, Censo Escolar), o Atlas não tem
um endpoint de download automatizável a partir deste ambiente. Os arquivos
de origem (municipio_raw.csv, uf_raw.csv, brasil_raw.csv) devem ser obtidos
manualmente da Base dos Dados (basedosdados.org, dataset mundo_onu.adh) e
colocados em data/external/atlas_desenvolvimento_humano/ antes de rodar
este pipeline. Ver README do projeto para o passo a passo.

nome_municipio é recuperado de uma fonte legada (municipal_raw.csv, réplica
de github.com/mauriciocramos/IDHM), pois as tabelas da Base dos Dados só
trazem o código IBGE. Essa fonte legada também deve estar em
data/external/atlas_desenvolvimento_humano/.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, EXTERNAL_DATA_DIR
from src.preprocessing.atlas.schemas import ARQUIVOS_BRONZE
from src.preprocessing.io import write_parquet_partitioned

EXTERNAL_DIR = EXTERNAL_DATA_DIR / "atlas_desenvolvimento_humano"
LEGADO_NOMES = EXTERNAL_DIR / "municipal_raw.csv"


def _checar_arquivo(caminho) -> None:
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} não encontrado. Baixe manualmente da Base dos Dados "
            f"(basedosdados.org, dataset mundo_onu.adh) e coloque em {EXTERNAL_DIR}. "
            f"Ver README do projeto para instruções."
        )


def bronze_municipio(ingestion_ts) -> pd.DataFrame:
    caminho = EXTERNAL_DIR / ARQUIVOS_BRONZE["municipio"]
    _checar_arquivo(caminho)
    df = pd.read_csv(caminho, sep=",", decimal=".", encoding="utf-8")
    df["_source_file"] = str(caminho)
    df["_ingestion_timestamp"] = ingestion_ts
    return df


def bronze_nomes_municipio() -> pd.DataFrame:
    """Recupera id_municipio -> nome_municipio da fonte legada."""
    _checar_arquivo(LEGADO_NOMES)
    df = pd.read_csv(LEGADO_NOMES, sep=";", decimal=",", encoding="utf-8")
    df.columns = [c.strip('"') for c in df.columns]
    nomes = df[["Codmun7", "Município"]].drop_duplicates(subset=["Codmun7"])
    nomes = nomes.rename(columns={"Codmun7": "id_municipio", "Município": "nome_municipio"})
    nomes["id_municipio"] = nomes["id_municipio"].astype(str).str.zfill(7)
    nomes["nome_municipio"] = nomes["nome_municipio"].str.strip().str.title()
    return nomes


def run_bronze() -> None:
    ingestion_ts = datetime.now(UTC)
    BRONZE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Bronze Atlas do Desenvolvimento Humano...")

    municipio = bronze_municipio(ingestion_ts)
    municipio["ano"] = pd.to_numeric(municipio["ano"], errors="coerce").astype("Int64")
    write_parquet_partitioned(municipio, BRONZE_DATA_DIR / "atlas_municipio", "ano")
    logger.info("atlas_municipio: {:,} linhas", len(municipio))

    logger.success("Camada Bronze Atlas concluída.")


if __name__ == "__main__":
    run_bronze()
