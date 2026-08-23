"""Structural contracts for the Censo Escolar ATU Bronze layer."""

from __future__ import annotations

METRICAS_ATU = [
    ("ED_INF_CAT_0", "double"),  # Educação Infantil — total
    ("CRE_CAT_0", "double"),  # Creche
    ("PRE_CAT_0", "double"),  # Pré-escola
    ("FUN_CAT_0", "double"),  # Ensino Fundamental — total
    ("FUN_AI_CAT_0", "double"),  # Fundamental — anos iniciais
    ("FUN_AF_CAT_0", "double"),  # Fundamental — anos finais
    ("FUN_01_CAT_0", "double"),  # Fundamental — 1º ano
    ("FUN_02_CAT_0", "double"),  # Fundamental — 2º ano
    ("FUN_03_CAT_0", "double"),  # Fundamental — 3º ano
    ("FUN_04_CAT_0", "double"),  # Fundamental — 4º ano
    ("FUN_05_CAT_0", "double"),  # Fundamental — 5º ano
    ("FUN_06_CAT_0", "double"),  # Fundamental — 6º ano
    ("FUN_07_CAT_0", "double"),  # Fundamental — 7º ano
    ("FUN_08_CAT_0", "double"),  # Fundamental — 8º ano
    ("FUN_09_CAT_0", "double"),  # Fundamental — 9º ano
    ("MULT_ETA_CAT_0", "double"),  # Turmas multietapa / multi / correção de fluxo
    ("MED_CAT_0", "double"),  # Ensino Médio — total
    ("MED_01_CAT_0", "double"),  # Médio — 1ª série
    ("MED_02_CAT_0", "double"),  # Médio — 2ª série
    ("MED_03_CAT_0", "double"),  # Médio — 3ª série
    ("MED_04_CAT_0", "double"),  # Médio — 4ª série
    ("MED_NS_CAT_0", "double"),  # Médio — não-seriado
]

SCHEMA_ATU_BRASIL_REGIOES_UFS = [
    ("NU_ANO_CENSO", "int"),
    ("UNIDGEO", "string"),
    ("NO_CATEGORIA", "string"),
    ("NO_DEPENDENCIA", "string"),
    *METRICAS_ATU,
]

SCHEMA_ATU_MUNICIPIOS = [
    ("NU_ANO_CENSO", "int"),
    ("NO_REGIAO", "string"),
    ("SG_UF", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("NO_CATEGORIA", "string"),
    ("NO_DEPENDENCIA", "string"),
    *METRICAS_ATU,
]

# (entidade, arquivo, sheet, schema, ano)
XLSX_JOBS = tuple(
    job
    for ano in (2023, 2024, 2025)
    for job in (
        (
            "atu_brasil_regioes_ufs",
            f"ATU_BRASIL_REGIOES_UFS_{ano}.xlsx",
            "BRASIL_REGIOES_UFS",
            SCHEMA_ATU_BRASIL_REGIOES_UFS,
            ano,
        ),
        (
            "atu_municipios",
            f"ATU_MUNICIPIOS_{ano}.xlsx",
            "MUNICIPIO",
            SCHEMA_ATU_MUNICIPIOS,
            ano,
        ),
    )
)

ANOS_CENSO = tuple(sorted({ano for *_, ano in XLSX_JOBS}))

# Silver/Gold semantic names (shared by transforms and quality checks)
METRIC_MAP = {
    "ED_INF_CAT_0": "media_educacao_infantil",
    "CRE_CAT_0": "media_creche",
    "PRE_CAT_0": "media_pre_escola",
    "FUN_CAT_0": "media_fundamental",
    "FUN_AI_CAT_0": "media_fundamental_anos_iniciais",
    "FUN_AF_CAT_0": "media_fundamental_anos_finais",
    "FUN_01_CAT_0": "media_fundamental_1_ano",
    "FUN_02_CAT_0": "media_fundamental_2_ano",
    "FUN_03_CAT_0": "media_fundamental_3_ano",
    "FUN_04_CAT_0": "media_fundamental_4_ano",
    "FUN_05_CAT_0": "media_fundamental_5_ano",
    "FUN_06_CAT_0": "media_fundamental_6_ano",
    "FUN_07_CAT_0": "media_fundamental_7_ano",
    "FUN_08_CAT_0": "media_fundamental_8_ano",
    "FUN_09_CAT_0": "media_fundamental_9_ano",
    "MULT_ETA_CAT_0": "media_multietapa",
    "MED_CAT_0": "media_medio",
    "MED_01_CAT_0": "media_medio_1_serie",
    "MED_02_CAT_0": "media_medio_2_serie",
    "MED_03_CAT_0": "media_medio_3_serie",
    "MED_04_CAT_0": "media_medio_4_serie",
    "MED_NS_CAT_0": "media_medio_nao_seriado",
}

METRIC_COLS = list(METRIC_MAP.values())
UF_KEYS = ["ano", "unidade_geografica", "localizacao", "dependencia_administrativa"]
MUN_KEYS = ["ano", "id_municipio", "localizacao", "dependencia_administrativa"]
