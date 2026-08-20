"""Orchestrate the INEP Medallion pipeline: download -> bronze -> silver -> gold."""

from loguru import logger

from src.preprocessing.inep.bronze import run_bronze
from src.preprocessing.inep.download import baixar_dados_inep
from src.preprocessing.inep.gold import run_gold
from src.preprocessing.inep.silver import run_silver


def run_pipeline(*, skip_download: bool = False) -> None:
    """Run the full INEP pipeline into data/processed."""
    if skip_download:
        logger.info("Pulando download; usando dados locais em data/raw.")
    else:
        baixar_dados_inep()
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline INEP concluído: tabelas Gold em data/processed.")
