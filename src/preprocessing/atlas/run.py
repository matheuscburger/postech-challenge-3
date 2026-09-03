"""Orchestrate the Atlas do Desenvolvimento Humano pipeline: bronze -> silver -> gold.

Não há etapa de download automatizado (ver bronze.py) — os arquivos de
origem devem estar em data/external/atlas_desenvolvimento_humano/ antes
de rodar.
"""

from loguru import logger

from src.preprocessing.atlas.bronze import run_bronze
from src.preprocessing.atlas.gold import run_gold
from src.preprocessing.atlas.silver import run_silver


def run_pipeline() -> None:
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline Atlas concluído: tabela Gold em data/processed.")


if __name__ == "__main__":
    run_pipeline()
