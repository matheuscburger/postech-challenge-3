"""IBGE municipal data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.ibge.run import run_pipeline

__all__ = ["run_pipeline"]
