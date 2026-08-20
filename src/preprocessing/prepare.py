"""CLI that runs the local Medallion pipeline: download -> bronze -> silver -> gold."""

import typer

from src.preprocessing.inep.run import run_pipeline

app = typer.Typer()


@app.command()
def main(
    skip_download: bool = typer.Option(
        False,
        "--skip-download",
        help="Reuse files already present in data/external and data/raw.",
    ),
):
    """Ingest INEP data and materialize Gold tables under data/processed."""
    run_pipeline(skip_download=skip_download)


if __name__ == "__main__":
    app()
