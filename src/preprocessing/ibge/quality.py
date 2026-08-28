"""Declarative data-quality checks for the IBGE Medallion pipeline."""

from __future__ import annotations

import pandas as pd

from src.preprocessing.dq import DataQualityError
from src.preprocessing.dq import checar_qualidade as _checar_qualidade
from src.preprocessing.ibge.schemas import ANOS_IBGE, MIN_MUNICIPIOS_POR_ANO

ANOS_ESPERADOS = list(ANOS_IBGE)

# Piso de linhas: um município por ano, com folga para criação/extinção de municípios.
MIN_LINHAS_CRITICO = len(ANOS_ESPERADOS) * 5_000
MIN_LINHAS_ALERTA = len(ANOS_ESPERADOS) * MIN_MUNICIPIOS_POR_ANO

# População do maior município brasileiro fica na casa dos 11-12 milhões; o teto
# serve para pegar erro de escala (valor em unidade errada), não para censurar dado.
TETO_POPULACAO = 20_000_000

# Os valores especiais do SIDRA ("-", "...", "X") viram nulo legitimamente, então um
# not_null crítico na medida derrubaria o pipeline por um punhado de municípios. O que
# de fato indica quebra é a PROPORÇÃO de ausentes: acima disso, a resposta veio ruim.
MAX_PROPORCAO_NULA = 0.01

# Altamira (PA) é o maior município do país, com cerca de 159.500 km²; Santa Cruz de
# Minas (MG) é o menor, com cerca de 3,5 km². O teto pega erro de escala (m² no lugar
# de km²), não área legítima.
TETO_AREA_KM2 = 200_000

# Área territorial do Brasil segundo o IBGE: 8.510.417,771 km². A soma das áreas
# municipais tem de bater com isso — é o teste mais barato contra erro de unidade ou
# resposta truncada. Tolerância folgada para absorver criação/extinção de municípios.
AREA_BRASIL_KM2 = 8_510_418
TOLERANCIA_AREA_BRASIL = 0.02

__all__ = [
    "ANOS_ESPERADOS",
    "CHECKS_GOLD",
    "CHECKS_SILVER",
    "DataQualityError",
    "checar_qualidade",
]


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "uf_incoerente":
        # Os dois primeiros dígitos do código IBGE do município são o código da UF.
        prefixo = pd.to_numeric(
            df["id_municipio"].astype("string").str.slice(0, 2), errors="coerce"
        ).astype("Int64")
        return prefixo.isna() | (prefixo != df["id_uf"])

    if nome == "populacao_nao_positiva":
        valores = pd.to_numeric(df["populacao_residente"], errors="coerce")
        return valores.notna() & (valores <= 0)

    if nome == "populacao_ausente_excessiva":
        # Marca as linhas nulas só quando elas passam do limite tolerado. Assim o log
        # informa quantas são, e o pipeline só quebra quando a ausência é sistêmica.
        ausentes = pd.to_numeric(df["populacao_residente"], errors="coerce").isna()
        if not len(df) or ausentes.mean() <= MAX_PROPORCAO_NULA:
            return pd.Series(False, index=df.index)
        return ausentes

    if nome == "area_nao_positiva":
        valores = pd.to_numeric(df["area_km2"], errors="coerce")
        return valores.notna() & (valores <= 0)

    if nome == "area_ausente_excessiva":
        # Mesma lógica da população: um município novo sem área no Censo é tolerável,
        # a ausência sistêmica não é.
        ausentes = pd.to_numeric(df["area_km2"], errors="coerce").isna()
        if not len(df) or ausentes.mean() <= MAX_PROPORCAO_NULA:
            return pd.Series(False, index=df.index)
        return ausentes

    if nome == "area_total_implausivel":
        # Marca as linhas do ano cuja soma de áreas se afasta do território brasileiro.
        piso = AREA_BRASIL_KM2 * (1 - TOLERANCIA_AREA_BRASIL)
        teto = AREA_BRASIL_KM2 * (1 + TOLERANCIA_AREA_BRASIL)
        soma = df.groupby("ano")["area_km2"].transform("sum")
        return (soma < piso) | (soma > teto)

    if nome == "cobertura_anual_insuficiente":
        # Marca todas as linhas de um ano cuja contagem de municípios ficou abaixo do
        # piso. Pega resposta truncada da API, que é a falha mais provável aqui.
        por_ano = df.groupby("ano")["id_municipio"].transform("nunique")
        return por_ano < MIN_MUNICIPIOS_POR_ANO

    if nome == "variacao_populacional_implausivel":
        # Estimativa anual não salta 30% num município sem que algo esteja errado.
        variacao = pd.to_numeric(df["variacao_populacional_pct"], errors="coerce")
        return variacao.notna() & (variacao.abs() > 30)

    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    """Run IBGE quality checks with dataset-specific expression rules."""
    return _checar_qualidade(entidade, df, checks, camada, violations_expr=_violations_expr)


CHECKS_SILVER = {
    "populacao_municipios": [
        {"tipo": "min_count", "valor": MIN_LINHAS_CRITICO, "critico": True},
        {"tipo": "min_count", "valor": MIN_LINHAS_ALERTA, "critico": False},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "not_null", "coluna": "id_uf", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "regex", "coluna": "sigla_uf", "valor": r"^[A-Z]{2}$", "critico": False},
        {"tipo": "unique", "coluna": ["ano", "id_municipio"], "critico": True},
        {
            "tipo": "range",
            "coluna": "populacao_residente",
            "valor": (1, TETO_POPULACAO),
            "critico": False,
        },
        {"tipo": "expr", "nome": "uf_incoerente", "critico": True},
        {"tipo": "expr", "nome": "populacao_nao_positiva", "critico": True},
        {"tipo": "expr", "nome": "populacao_ausente_excessiva", "critico": True},
        {"tipo": "not_null", "coluna": "area_km2", "critico": False},
        {
            "tipo": "range",
            "coluna": "area_km2",
            "valor": (0.1, TETO_AREA_KM2),
            "critico": False,
        },
        {"tipo": "expr", "nome": "area_nao_positiva", "critico": True},
        {"tipo": "expr", "nome": "area_ausente_excessiva", "critico": True},
        {"tipo": "expr", "nome": "area_total_implausivel", "critico": False},
        {"tipo": "expr", "nome": "cobertura_anual_insuficiente", "critico": False},
    ],
}

CHECKS_GOLD = {
    "populacao_municipios": [
        {"tipo": "min_count", "valor": MIN_LINHAS_CRITICO, "critico": True},
        {"tipo": "min_count", "valor": MIN_LINHAS_ALERTA, "critico": False},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "not_null", "coluna": "id_uf", "critico": True},
        # Medida derivada de fonte com sentinelas: alerta, não bloqueio. O corte
        # crítico é a proporção de ausentes, no expr populacao_ausente_excessiva.
        {"tipo": "not_null", "coluna": "populacao_residente", "critico": False},
        {"tipo": "not_null", "coluna": "porte_municipio", "critico": False},
        {"tipo": "not_null", "coluna": "area_km2", "critico": False},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio"], "critico": True},
        {
            "tipo": "range",
            "coluna": "populacao_residente",
            "valor": (1, TETO_POPULACAO),
            "critico": False,
        },
        {"tipo": "expr", "nome": "uf_incoerente", "critico": True},
        {"tipo": "expr", "nome": "populacao_nao_positiva", "critico": True},
        {"tipo": "expr", "nome": "populacao_ausente_excessiva", "critico": True},
        {
            "tipo": "range",
            "coluna": "area_km2",
            "valor": (0.1, TETO_AREA_KM2),
            "critico": False,
        },
        {"tipo": "expr", "nome": "area_nao_positiva", "critico": True},
        {"tipo": "expr", "nome": "area_ausente_excessiva", "critico": True},
        {"tipo": "expr", "nome": "area_total_implausivel", "critico": False},
        {"tipo": "expr", "nome": "cobertura_anual_insuficiente", "critico": False},
        {"tipo": "expr", "nome": "variacao_populacional_implausivel", "critico": False},
    ],
}
