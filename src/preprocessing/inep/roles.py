"""Column roles for the INEP Gold tables, consumed by the ML pipeline.

``gold/aluno`` holds almost no predictors: the public microdata says little
about an anonymised student, and most of what it does say about the exam
(``proficiencia``, ``caderno``) is either the label itself or noise. The
exception is ``dependencia_administrativa``, a pre-exam attribute of the
school's network that is also the grain of the Censo Escolar. Everything else
comes from ``src/preprocessing/join.py``, which joins this table to the
municipal and state tables — and to FUNDEB, Censo Escolar and IBGE — on the
keys below, producing ``processed/base_analitica``.
"""

PAPEIS_ALUNO = {
    "alvo": ["label_alfabetizado"],
    "identificador": ["ano", "id_uf", "id_municipio", "id_escola", "id_aluno"],
    "vazamento": [],
    "constante": [],
    "features": ["dependencia_administrativa"],
}

# How join.py attaches each context table to gold/aluno.
CHAVES_JOIN = {
    "municipio": ["ano", "id_municipio"],
    "ufs": ["ano", "id_uf"],
}

# Context columns that describe the exam these very students sat: joining them
# at the same ``ano`` leaks the answer. ``join.py`` shifts them one year
# (``ctx_inep_mun_taxa_alfabetizacao_lag1`` and friends) and reads this list to
# decide what to shift, so a new result column added to the Gold tables is
# lagged automatically. ``meta`` is exempt: INEP publishes it before the exam.
COLUNAS_LAG_OBRIGATORIO = [
    "taxa_alfabetizacao",
    "media_portugues",
    "percentual_participacao",
    "nivel_alfabetizacao",
]

COLUNAS_SEM_LAG = ["meta"]

# The Gold tables hold only independent measurements. These are derived on
# demand by features/, from the lagged columns above, using the helpers of the
# same name in ``inep.gold``: distancia_meta(taxa, meta), atingiu_meta(...),
# categoria_desempenho(...), faixa_participacao(percentual_participacao).
COLUNAS_DERIVADAS = [
    "distancia_meta",
    "atingiu_meta",
    "categoria_desempenho",
    "faixa_participacao",
]
