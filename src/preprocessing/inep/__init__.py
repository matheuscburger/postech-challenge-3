"""INEP Alfabetização data pipeline (download, bronze, silver, gold)."""

from src.preprocessing.inep.roles import (
    CHAVES_JOIN,
    COLUNAS_DERIVADAS,
    COLUNAS_LAG_OBRIGATORIO,
    COLUNAS_SEM_LAG,
    PAPEIS_ALUNO,
)
from src.preprocessing.inep.run import run_pipeline

__all__ = [
    "CHAVES_JOIN",
    "COLUNAS_DERIVADAS",
    "COLUNAS_LAG_OBRIGATORIO",
    "COLUNAS_SEM_LAG",
    "PAPEIS_ALUNO",
    "run_pipeline",
]
