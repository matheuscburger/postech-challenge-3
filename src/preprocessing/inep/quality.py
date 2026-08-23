"""Declarative data-quality checks for the INEP Medallion pipeline."""

from __future__ import annotations

import pandas as pd

from src.config import ANOS, CORTE_PROFICIENCIA
from src.preprocessing.dq import DataQualityError, checar_qualidade as _checar_qualidade

ANOS_ESPERADOS = list(ANOS)

__all__ = [
    "ANOS_ESPERADOS",
    "CHECKS_GOLD",
    "CHECKS_SILVER",
    "DataQualityError",
    "checar_qualidade",
]


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "rede_uf_invalida":
        return df["rede"].isna() | (df["rede"] != 5)
    if nome == "rede_municipio_invalida":
        return df["rede"].isna() | (df["rede"] != 3)
    if nome == "dependencia_administrativa_invalida":
        return df["dependencia_administrativa"].isna() | ~df["dependencia_administrativa"].isin(
            [2, 3]
        )
    if nome == "meta_ausente_em_ano_alvo":
        return df["ano"].isin([2024, 2025]) & df["meta"].isna()
    if nome == "atingiu_meta_incoerente":
        previsto = (df["taxa_alfabetizacao"] - df["meta"]) >= 0
        return df["meta"].notna() & (previsto != df["atingiu_meta"])
    if nome == "label_incoerente_com_corte":
        return (df["proficiencia"] >= CORTE_PROFICIENCIA) != (df["label_alfabetizado"] == 1)
    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    """Run INEP quality checks with dataset-specific expression rules."""
    return _checar_qualidade(
        entidade, df, checks, camada, violations_expr=_violations_expr
    )


CHECKS_SILVER = {
    "meta_alfabetizacao_brasil": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "meta_alfabetizacao_uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "sigla_uf", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "meta_alfabetizacao_municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_uf", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_uf", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "media_portugues", "valor": (0, 1000), "critico": False},
        {"tipo": "expr", "nome": "rede_uf_invalida", "critico": True},
    ],
    "municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "media_portugues", "valor": (0, 1000), "critico": False},
        {"tipo": "expr", "nome": "rede_municipio_invalida", "critico": True},
    ],
    "alunos": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_aluno", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_aluno"], "critico": True},
        {"tipo": "range", "coluna": "proficiencia", "valor": (0, 1500), "critico": False},
        {"tipo": "expr", "nome": "dependencia_administrativa_invalida", "critico": True},
    ],
}

CHECKS_GOLD = {
    "indicadores_municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "meta", "valor": (0, 100), "critico": False},
        {"tipo": "expr", "nome": "meta_ausente_em_ano_alvo", "critico": False},
        {
            "tipo": "range",
            "coluna": "percentual_participacao",
            "valor": (0, 100),
            "critico": False,
        },
        {"tipo": "expr", "nome": "atingiu_meta_incoerente", "critico": True},
    ],
    "indicadores_uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "sigla_uf"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "meta", "valor": (0, 100), "critico": False},
        {"tipo": "expr", "nome": "meta_ausente_em_ano_alvo", "critico": False},
        {
            "tipo": "range",
            "coluna": "percentual_participacao",
            "valor": (0, 100),
            "critico": False,
        },
        {"tipo": "expr", "nome": "atingiu_meta_incoerente", "critico": True},
    ],
    "aluno_contexto": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "id_aluno", "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "proficiencia", "critico": True},
        {"tipo": "not_null", "coluna": "label_alfabetizado", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_aluno"], "critico": True},
        {"tipo": "range", "coluna": "proficiencia", "valor": (0, 1500), "critico": False},
        {"tipo": "expr", "nome": "label_incoerente_com_corte", "critico": True},
    ],
}
