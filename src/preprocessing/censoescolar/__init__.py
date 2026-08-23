"""Censo Escolar ATU data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.censoescolar.run import run_pipeline

__all__ = ["run_pipeline"]
