"""Structural contracts for the FUNDEB Bronze layer (column name + Spark-equivalent type)."""

from __future__ import annotations

SCHEMA_NSE_ENTES = [
    ("Código do Ente", "int"),
    ("Nome do Ente", "string"),
    ("Sigla UF", "string"),
    ("Valor do Nível Socioeconômico", "double"),
    ("Ponderador do NSE entre 0,95 e 1,05", "double"),
]

# (entidade, arquivo, sheet, schema, ano)
XLSX_JOBS = (
    (
        "nse_entes_federados",
        "NSE_Entes_Federados_Fundeb2023.xlsx",
        "NSE",
        SCHEMA_NSE_ENTES,
        2024,
    ),
    (
        "nse_entes_federados",
        "NSE_Entes_Federados_Fundeb_Financeiro_2025.xls",
        "NSE Financeiro 2025",
        SCHEMA_NSE_ENTES,
        2025,
    ),
)

ANOS_FUNDEB = tuple(sorted({ano for *_, ano in XLSX_JOBS}))
