"""INEP Alfabetização data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.inep.run import run_pipeline

__all__ = ["run_pipeline"]
