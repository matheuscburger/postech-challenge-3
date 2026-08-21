"""Orchestrate the FUNDEB Medallion pipeline: download -> bronze -> silver -> gold."""

from loguru import logger

from src.preprocessing.fundeb.bronze import run_bronze
from src.preprocessing.fundeb.download import baixar_dados_fundeb
from src.preprocessing.fundeb.gold import run_gold
from src.preprocessing.fundeb.silver import run_silver


def run_pipeline(*, skip_download: bool = False) -> None:
    """Run the full FUNDEB pipeline into data/processed."""
    if skip_download:
        logger.info("Pulando download; usando dados locais em data/raw.")
    else:
        baixar_dados_fundeb()
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline FUNDEB concluído: tabelas Gold em data/processed.")


if __name__ == "__main__":
    import sys

    run_pipeline(skip_download="--skip-download" in sys.argv)
