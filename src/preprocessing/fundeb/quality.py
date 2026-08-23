"""Declarative data-quality checks for the FUNDEB NSE Medallion pipeline."""

from __future__ import annotations

import pandas as pd

from src.preprocessing.dq import DataQualityError, checar_qualidade as _checar_qualidade
from src.preprocessing.fundeb.schemas import ANOS_FUNDEB

ANOS_ESPERADOS = list(ANOS_FUNDEB)

__all__ = [
    "ANOS_ESPERADOS",
    "CHECKS_GOLD",
    "CHECKS_SILVER",
    "DataQualityError",
    "checar_qualidade",
]


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "codigo_ente_invalido":
        codigo = pd.to_numeric(df["codigo_ente"], errors="coerce")
        known = codigo.notna()
        uf = codigo < 100
        municipio = codigo >= 1_000_000
        return known & ~uf & ~municipio
    if nome == "tipo_ente_outro":
        return df["tipo_ente"].astype("string") == "outro"
    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    """Run FUNDEB quality checks with dataset-specific expression rules."""
    return _checar_qualidade(
        entidade, df, checks, camada, violations_expr=_violations_expr
    )


CHECKS_SILVER = {
    "nse_entes_federados": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "codigo_ente", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "codigo_ente"], "critico": True},
        {"tipo": "regex", "coluna": "sigla_uf", "valor": r"^[A-Z]{2}$", "critico": True},
        {"tipo": "range", "coluna": "valor_nse", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "ponderador_nse", "valor": (0.95, 1.05), "critico": True},
        {"tipo": "expr", "nome": "codigo_ente_invalido", "critico": True},
    ],
}

CHECKS_GOLD = {
    "nse_entes_federados": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "codigo_ente", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "not_null", "coluna": "tipo_ente", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "codigo_ente"], "critico": True},
        {"tipo": "regex", "coluna": "sigla_uf", "valor": r"^[A-Z]{2}$", "critico": True},
        {"tipo": "range", "coluna": "valor_nse", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "ponderador_nse", "valor": (0.95, 1.05), "critico": True},
        {"tipo": "expr", "nome": "codigo_ente_invalido", "critico": True},
        {"tipo": "expr", "nome": "tipo_ente_outro", "critico": True},
    ],
}
