"""FUNDEB NSE data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.fundeb.run import run_pipeline

__all__ = ["run_pipeline"]
