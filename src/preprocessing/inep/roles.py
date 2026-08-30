"""Column roles for the INEP Gold tables, consumed by the ML pipeline.

``gold/aluno`` holds no predictors: the public microdata says almost nothing
about an anonymised student, and everything it does say about the exam
(``proficiencia``, ``caderno``) is either the label itself or noise. Features
come from ``features/``, which joins this table to the municipal and state
tables — and to FUNDEB, Censo Escolar and IBGE — on the keys below.
"""

PAPEIS_ALUNO = {
    "alvo": ["label_alfabetizado"],
    "identificador": ["ano", "id_uf", "id_municipio", "id_escola", "id_aluno"],
    "vazamento": [],
    "constante": [],
    "features": [],
}

# How features/ joins each context table onto gold/aluno.
CHAVES_JOIN = {
    "municipio": ["ano", "id_municipio"],
    "ufs": ["ano", "id_uf"],
}

# Context columns that describe the exam these very students sat: joining them
# at the same ``ano`` leaks the answer. features/ must shift them one year
# (``taxa_alfabetizacao_lag1``, ``delta_taxa``, ``atingiu_meta_lag1``, ...).
# ``meta`` is exempt: INEP publishes it before the exam.
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
