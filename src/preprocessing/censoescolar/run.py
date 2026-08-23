"""Orchestrate the Censo Escolar ATU Medallion pipeline: download -> bronze -> silver -> gold."""

from loguru import logger

from src.preprocessing.censoescolar.bronze import run_bronze
from src.preprocessing.censoescolar.download import baixar_dados_censoescolar
from src.preprocessing.censoescolar.gold import run_gold
from src.preprocessing.censoescolar.silver import run_silver


def run_pipeline(*, skip_download: bool = False) -> None:
    """Run the full Censo Escolar ATU pipeline into data/processed."""
    if skip_download:
        logger.info("Pulando download; usando dados locais em data/raw.")
    else:
        baixar_dados_censoescolar()
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline Censo Escolar concluído: tabelas Gold em data/processed.")


if __name__ == "__main__":
    import sys

    run_pipeline(skip_download="--skip-download" in sys.argv)
