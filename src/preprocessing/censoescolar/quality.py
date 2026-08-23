"""Declarative data-quality checks for the Censo Escolar ATU Medallion pipeline."""

from __future__ import annotations

import pandas as pd

from src.preprocessing.censoescolar.schemas import ANOS_CENSO
from src.preprocessing.censoescolar.schemas import METRIC_COLS, MUN_KEYS, UF_KEYS
from src.preprocessing.dq import DataQualityError, checar_qualidade as _checar_qualidade

ANOS_ESPERADOS = list(ANOS_CENSO)
TIPOS_GEOGRAFIA = frozenset({"brasil", "regiao", "uf"})

__all__ = [
    "ANOS_ESPERADOS",
    "CHECKS_GOLD",
    "CHECKS_SILVER",
    "DataQualityError",
    "checar_qualidade",
]


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "media_negativa":
        out = pd.Series(False, index=df.index)
        for col in METRIC_COLS:
            if col not in df.columns:
                continue
            out = out | (pd.to_numeric(df[col], errors="coerce") < 0)
        return out
    if nome == "tipo_geografia_invalida":
        tipo = df["tipo_geografia"].astype("string")
        return tipo.isna() | ~tipo.isin(TIPOS_GEOGRAFIA)
    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    """Run Censo Escolar quality checks with dataset-specific expression rules."""
    return _checar_qualidade(
        entidade, df, checks, camada, violations_expr=_violations_expr
    )


CHECKS_SILVER = {
    "atu_brasil_regioes_ufs": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        *[{"tipo": "not_null", "coluna": c, "critico": True} for c in UF_KEYS],
        {"tipo": "unique", "coluna": list(UF_KEYS), "critico": True},
        {
            "tipo": "range",
            "coluna": "media_fundamental",
            "valor": (0, 80),
            "critico": False,
        },
        {"tipo": "expr", "nome": "media_negativa", "critico": True},
    ],
    "atu_municipios": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "min_count", "valor": 5000, "critico": False},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        *[{"tipo": "not_null", "coluna": c, "critico": True} for c in MUN_KEYS],
        {"tipo": "unique", "coluna": list(MUN_KEYS), "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "regex", "coluna": "sigla_uf", "valor": r"^[A-Z]{2}$", "critico": True},
        {"tipo": "expr", "nome": "media_negativa", "critico": True},
    ],
}

CHECKS_GOLD = {
    "atu_brasil_regioes_ufs": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        *[{"tipo": "not_null", "coluna": c, "critico": True} for c in UF_KEYS],
        {"tipo": "not_null", "coluna": "tipo_geografia", "critico": True},
        {"tipo": "unique", "coluna": list(UF_KEYS), "critico": True},
        {
            "tipo": "range",
            "coluna": "media_fundamental",
            "valor": (0, 80),
            "critico": False,
        },
        {"tipo": "expr", "nome": "media_negativa", "critico": True},
        {"tipo": "expr", "nome": "tipo_geografia_invalida", "critico": True},
    ],
    "atu_municipios": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "min_count", "valor": 5000, "critico": False},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        *[{"tipo": "not_null", "coluna": c, "critico": True} for c in MUN_KEYS],
        {"tipo": "unique", "coluna": list(MUN_KEYS), "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "regex", "coluna": "sigla_uf", "valor": r"^[A-Z]{2}$", "critico": True},
        {"tipo": "expr", "nome": "media_negativa", "critico": True},
    ],
}
