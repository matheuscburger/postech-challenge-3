"""CLI that runs the local Medallion pipelines: download -> bronze -> silver -> gold."""

import typer

from src.preprocessing.fundeb.run import run_pipeline as run_fundeb
from src.preprocessing.inep.run import run_pipeline as run_inep

app = typer.Typer()


@app.command()
def main(
    skip_download: bool = typer.Option(
        False,
        "--skip-download",
        help="Reuse files already present in data/external and data/raw.",
    ),
):
    """Ingest INEP and FUNDEB data and materialize Gold tables under data/processed."""
    run_inep(skip_download=skip_download)
    run_fundeb(skip_download=skip_download)


if __name__ == "__main__":
    app()
