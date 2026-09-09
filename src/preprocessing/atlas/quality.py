"""Declarative data-quality checks for the Atlas do Desenvolvimento Humano pipeline."""

from __future__ import annotations

import pandas as pd

from src.preprocessing.atlas.schemas import COLUNAS_GOLD, MUN_KEYS
from src.preprocessing.dq import DataQualityError, checar_qualidade as _checar_qualidade

__all__ = ["CHECKS_SILVER", "DataQualityError", "checar_qualidade"]


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "indicador_fora_de_faixa":
        out = pd.Series(False, index=df.index)
        for col in COLUNAS_GOLD:
            if col not in df.columns or not col.startswith(("idhm", "taxa_", "percentual_")):
                continue
            valores = pd.to_numeric(df[col], errors="coerce")
            out = out | (valores < 0) | (valores > 100)
        return out
    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    return _checar_qualidade(entidade, df, checks, camada, violations_expr=_violations_expr)


CHECKS_SILVER = {
    "atlas_desenvolvimento_humano": [
        {"tipo": "min_count", "valor": 5000, "critico": True},
        *[{"tipo": "not_null", "coluna": c, "critico": True} for c in MUN_KEYS],
        {"tipo": "not_null", "coluna": "nome_municipio", "critico": False},
        {"tipo": "unique", "coluna": list(MUN_KEYS), "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
    ],
}
