"""INEP Alfabetização data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.inep.roles import PAPEIS_ALUNO_CONTEXTO
from src.preprocessing.inep.run import run_pipeline

__all__ = ["PAPEIS_ALUNO_CONTEXTO", "run_pipeline"]
