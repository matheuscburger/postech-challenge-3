"""CLI that runs the local Medallion pipelines: download -> bronze -> silver -> gold -> join."""

import typer

from src.preprocessing.censoescolar.run import run_pipeline as run_censoescolar
from src.preprocessing.fundeb.run import run_pipeline as run_fundeb
from src.preprocessing.ibge.run import run_pipeline as run_ibge
from src.preprocessing.inep.run import run_pipeline as run_inep
from src.preprocessing.atlas.run import run_pipeline as run_atlas
from src.preprocessing.join import run_join

app = typer.Typer()


@app.command()
def main(
    skip_download: bool = typer.Option(
        False,
        "--skip-download",
        help="Reuse files already present in data/external and data/raw.",
    ),
):
    """Ingest INEP, FUNDEB, Censo Escolar, IBGE e Atlas em data/processed, depois junta tudo em base_analitica."""
    run_inep(skip_download=skip_download)
    run_fundeb(skip_download=skip_download)
    run_censoescolar(skip_download=skip_download)
    run_ibge(skip_download=skip_download)
    run_atlas(skip_download=skip_download)
    run_join()


if __name__ == "__main__":
    app()
