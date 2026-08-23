"""Structural contracts for the Bronze layer (column name + Spark-equivalent type)."""

from __future__ import annotations


def metas(tipo: str) -> list[tuple[str, str]]:
    """Generate META_FINAL_2024..2030 with a shared type."""
    return [(f"META_FINAL_{a}", tipo) for a in range(2024, 2031)]


SCHEMA_TS_ALUNO = [
    ("NU_ANO_AVALIACAO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("ID_ALUNO", "string"),
    ("TP_SERIE", "string"),
    ("ID_ESCOLA", "string"),
    ("TP_DEPENDENCIA", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("IN_PRESENCA_LP", "int"),
    ("IN_PREENCHIMENTO_LP", "int"),
    ("CO_CADERNO_LP", "string"),
    ("VL_PESO_ALUNO_LP", "double"),
    ("VL_PROFICIENCIA_LP", "double"),
    ("IN_ALFABETIZADO", "int"),
]

SCHEMA_TS_MUNICIPIO = [
    ("NU_ANO_AVALIACAO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("TP_SERIE", "string"),
    ("ID_TIPO_REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO", "double"),
    ("VL_MEDIA_LP", "double"),
]

SCHEMA_TS_ESTADO = [
    ("NU_ANO_AVALIACAO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("TP_SERIE", "string"),
    ("ID_TIPO_REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO", "double"),
    ("VL_MEDIA_LP", "double"),
]

SCHEMA_METAS_MUN_2023 = [
    ("ANO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("NO_TP_REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO", "double"),
    ("META_FINAL_2024", "double"),
    ("META_FINAL_2025", "double"),
    ("META_FINAL_2026", "double"),
    ("META_FINAL_2027", "double"),
    ("META_FINAL_2028", "double"),
    ("META_FINAL_2029", "double"),
    ("META_FINAL_2030", "double"),
    ("NIVEIS_ALFABETIZACAO_2023", "int"),
    ("PC_AVALIADOS_LP", "double"),
]

SCHEMA_METAS_UF_2023 = [
    ("ANO", "int"),
    ("CD_UF", "string"),
    ("SIGLA_UF", "string"),
    ("NOME_UF", "string"),
    ("REDE", "string"),
    ("SAEB_2019", "double"),
    ("SAEB_2021", "double"),
    ("PC_ALUNO_ALFABETIZADO", "double"),
    ("META_FINAL_2024", "string"),
    ("META_FINAL_2025", "string"),
    ("META_FINAL_2026", "string"),
    ("META_FINAL_2027", "string"),
    ("META_FINAL_2028", "string"),
    ("META_FINAL_2029", "string"),
    ("META_FINAL_2030", "string"),
    ("PC_AVALIADOS_LP", "double"),
]

SCHEMA_METAS_MUN_2024 = [
    ("ANO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("NO_TP_REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO_2023", "double"),
    ("PC_ALUNO_ALFABETIZADO_2024", "double"),
    *metas("double"),
    ("CO_NIVEL_ALFABETIZACAO", "int"),
    ("PC_AVALIADOS_LP", "double"),
]

SCHEMA_METAS_MUN_2025 = [
    ("ANO", "int"),
    ("CO_UF", "string"),
    ("SG_UF", "string"),
    ("CO_MUNICIPIO", "string"),
    ("NO_MUNICIPIO", "string"),
    ("NO_TP_REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO_2023", "double"),
    ("PC_ALUNO_ALFABETIZADO_2024", "double"),
    ("PC_ALUNO_ALFABETIZADO_2025", "double"),
    *metas("double"),
    ("CO_NIVEL_ALFABETIZACAO", "int"),
    ("PC_AVALIADOS_LP", "double"),
]

SCHEMA_METAS_UF_2024 = [
    ("ANO", "int"),
    ("CD_UF", "string"),
    ("SIGLA_UF", "string"),
    ("NOME_UF", "string"),
    ("REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO_2023", "double"),
    ("PC_ALUNO_ALFABETIZADO_2024", "double"),
    *metas("string"),
    ("PC_AVALIADOS_LP", "double"),
]

SCHEMA_METAS_UF_2025 = [
    ("ANO", "int"),
    ("CD_UF", "string"),
    ("SIGLA_UF", "string"),
    ("NOME_UF", "string"),
    ("REDE", "string"),
    ("PC_ALUNO_ALFABETIZADO_2023", "double"),
    ("PC_ALUNO_ALFABETIZADO_2024", "double"),
    ("PC_ALUNO_ALFABETIZADO_2025", "double"),
    *metas("string"),
    ("PC_AVALIADOS_LP", "double"),
]

CSV_JOBS = (
    ("ts_aluno", "TS_ALUNO.csv", SCHEMA_TS_ALUNO),
    ("ts_municipio", "TS_MUNICIPIO.csv", SCHEMA_TS_MUNICIPIO),
    ("ts_estado", "TS_ESTADO.csv", SCHEMA_TS_ESTADO),
)

# (entidade, arquivo, sheet, schema, ano)
XLSX_JOBS = (
    (
        "metas_municipios",
        "resultados_e_metas_municipios.xlsx",
        "Divulgação Alfabet Municipio",
        SCHEMA_METAS_MUN_2023,
        2023,
    ),
    (
        "metas_ufs",
        "resultados_e_metas_ufs.xlsx",
        "Divulgação Alfabet UF e Brasil",
        SCHEMA_METAS_UF_2023,
        2023,
    ),
    (
        "metas_municipios",
        "resultados_e_metas_municipios_2024.xlsx",
        "Divulgação Alfabet Municipio",
        SCHEMA_METAS_MUN_2024,
        2024,
    ),
    (
        "metas_ufs",
        "resultados_e_metas_ufs_2024_2.xlsx",
        "Divulgação Alfabet UF e Brasil",
        SCHEMA_METAS_UF_2024,
        2024,
    ),
    (
        "metas_municipios",
        "resultados_e_metas_municipios_2025_v2.xlsx",
        "Divulgação Alfabet Municipio",
        SCHEMA_METAS_MUN_2025,
        2025,
    ),
    (
        "metas_ufs",
        "resultados_e_metas_ufs_2025_v1.xlsx",
        "Divulgação Alfabet UF e Brasil",
        SCHEMA_METAS_UF_2025,
        2025,
    ),
)
