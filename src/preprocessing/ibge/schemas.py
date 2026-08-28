"""Structural contracts for the IBGE Bronze layer (column name + Spark-equivalent type)."""

from __future__ import annotations

from typing import NamedTuple

# Níveis territoriais da API de agregados: N1 Brasil, N2 região, N3 UF, N6 município.
NIVEL_MUNICIPIO = "N6"


class ApiJob(NamedTuple):
    """Um pedido à API de agregados.

    ``variavel`` é o NOME da variável, não o id: o id é resolvido contra
    /agregados/{id}/metadados em tempo de execução. Fixar id na mão é o acoplamento
    que quebra em silêncio quando o IBGE republica o agregado.
    """

    entidade: str
    agregado: int
    periodos: tuple[int, ...]
    nivel: str
    variavel: str
    medida: str


# --------------------------------------------------------------------------------------
# Cobertura temporal da SÉRIE: 2024 e 2025, mesmo recorte do FUNDEB.
#
# O IBGE NÃO publicou estimativa municipal de população para 2023 — naquele ano a
# referência oficial passou a ser a contagem do Censo 2022, encaminhada ao TCU para o
# cálculo do FPM. A série municipal do agregado 6579 salta de 2021 para 2024.
# --------------------------------------------------------------------------------------
ANOS_ESTIMATIVA = (2024, 2025)

# A área territorial é ATRIBUTO ESTRUTURAL do município, não série: só muda quando há
# alteração de limites. Vem do Censo 2022 (único período do agregado 4714) e é replicada
# para todos os anos da janela. Por ser constante, não há coluna de ano de referência —
# o valor é sempre de 2022, e este comentário é o registro disso.
ANO_REFERENCIA_AREA = 2022

ENTIDADE_POPULACAO = "populacao_municipios"
ENTIDADE_AREA = "area_municipios"

MEDIDA_POPULACAO = "populacao_residente"
MEDIDA_AREA = "area_km2"

API_JOBS = (
    ApiJob(
        ENTIDADE_POPULACAO,
        6579,  # Estimativas de População
        ANOS_ESTIMATIVA,
        NIVEL_MUNICIPIO,
        "População residente estimada",
        MEDIDA_POPULACAO,
    ),
    ApiJob(
        ENTIDADE_AREA,
        4714,  # Censo Demográfico 2022 — população, área territorial e densidade
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        "Área da unidade territorial",
        MEDIDA_AREA,
    ),
)

JOBS_POR_ENTIDADE = {job.entidade: job for job in API_JOBS}

# Anos da tabela de saída — vêm da série, não dos atributos estruturais.
ANOS_IBGE = tuple(ANOS_ESTIMATIVA)

# Contrato da tabela LONGA normalizada a partir da resposta da API.
# A API devolve uma linha por (variável x localidade x período); a Bronze preserva
# esse formato e o pivot para largo acontece só na Silver.
SCHEMA_SERIE_LONGA = [
    ("NU_ANO", "int"),
    ("CO_LOCALIDADE", "string"),
    ("NO_LOCALIDADE", "string"),
    ("CO_NIVEL", "string"),
    ("CO_VARIAVEL", "string"),
    ("NO_VARIAVEL", "string"),
    ("NO_UNIDADE", "string"),
    ("VL_MEDIDA", "double"),
]

# Valores especiais do SIDRA que chegam como texto e precisam virar nulo.
# "-" zero, "..." não aplicável, "X" sob sigilo, ".." não disponível.
# Um município criado depois da coleta aparece com "..." — é o caso de
# Boa Esperança do Norte (MT), sem estimativa em 2024 e sem área no Censo 2022.
SENTINELAS_SIDRA = ("-", "...", "..", "X", "")

# Silver: nomes semânticos. A medida (VL_MEDIDA) é renomeada por entidade.
COLUMN_MAP_BASE = {
    "NU_ANO": "ano",
    "CO_LOCALIDADE": "id_municipio",
    "NO_LOCALIDADE": "nome_localidade",
}

SILVER_COLS = [
    "ano",
    "id_municipio",
    "nome_municipio",
    "id_uf",
    "sigla_uf",
    "populacao_residente",
    "area_km2",
]

GOLD_COLS = [
    "ano",
    "id_municipio",
    "nome_municipio",
    "id_uf",
    "sigla_uf",
    "populacao_residente",
    "area_km2",
    "porte_municipio",
    "variacao_populacional_pct",
]

# Faixas de porte populacional. Cardinalidade baixa de propósito: entra no
# OneHotEncoder de src/preprocessing/pipeline.py sem explodir a matriz.
FAIXAS_PORTE = (
    (0, 5_000, "Até 5 mil"),
    (5_000, 10_000, "5 a 10 mil"),
    (10_000, 20_000, "10 a 20 mil"),
    (20_000, 50_000, "20 a 50 mil"),
    (50_000, 100_000, "50 a 100 mil"),
    (100_000, 500_000, "100 a 500 mil"),
    (500_000, None, "Mais de 500 mil"),
)

# Piso de municípios por ano usado nos checks. O Brasil tem 5.570 municípios; a série de
# estimativas já traz 5.571 (Boa Esperança do Norte/MT, criado depois do Censo 2022).
# O piso fica abaixo disso para tolerar criação/extinção sem falso positivo.
MIN_MUNICIPIOS_POR_ANO = 5_500
