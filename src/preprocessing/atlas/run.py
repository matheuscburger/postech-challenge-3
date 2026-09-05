"""Orchestrate the Atlas do Desenvolvimento Humano pipeline: download -> bronze -> silver -> gold.

O passo de download automatiza o que dá (fonte legada, GitHub) e verifica
o que precisa ser manual (Base dos Dados) — ver download.py para detalhes.
"""

from loguru import logger

from src.preprocessing.atlas.bronze import run_bronze
from src.preprocessing.atlas.download import baixar_dados_atlas
from src.preprocessing.atlas.gold import run_gold
from src.preprocessing.atlas.silver import run_silver


def run_pipeline(*, skip_download: bool = False) -> None:
    if skip_download:
        logger.info("Pulando download; usando dados locais em data/external.")
    else:
        baixar_dados_atlas()
    run_bronze()
    run_silver()
    run_gold()
    logger.success("Pipeline Atlas concluído: tabela Gold em data/processed.")


if __name__ == "__main__":
    import sys

    run_pipeline(skip_download="--skip-download" in sys.argv)
