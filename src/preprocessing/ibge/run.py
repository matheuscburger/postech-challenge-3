"""Orchestrate the IBGE Medallion pipeline: download -> bronze -> silver -> gold."""

from loguru import logger

from src.preprocessing.ibge.bronze import run_bronze
from src.preprocessing.ibge.download import baixar_dados_ibge
from src.preprocessing.ibge.gold import run_gold
from src.preprocessing.ibge.silver import run_silver


def run_pipeline(*, skip_download: bool = False) -> None:
    """Run the full IBGE pipeline into data/processed."""
    if skip_download:
        logger.info("Pulando download; usando o cache da API em data/external/ibge.")
    else:
        baixar_dados_ibge()
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline IBGE concluído: tabelas Gold em data/processed.")


if __name__ == "__main__":
    import sys

    run_pipeline(skip_download="--skip-download" in sys.argv)
