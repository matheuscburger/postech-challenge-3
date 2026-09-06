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

# Os DOIS alvos da gold/aluno. São a mesma medição em duas escalas:
# ``label_alfabetizado == (label_proficiencia >= CORTE_PROFICIENCIA)`` bate em
# 100,0000% das linhas. Logo são alternativos, nunca simultâneos.
ALVO_CLASSIFICACAO = "label_alfabetizado"
ALVO_REGRESSAO = "label_proficiencia"

PAPEIS_ALUNO = {
    "alvo": [ALVO_CLASSIFICACAO, ALVO_REGRESSAO],
    "identificador": ["ano", "id_uf", "id_municipio", "id_escola", "id_aluno"],
    "vazamento": [],
    "constante": [],
    "features": ["dependencia_administrativa"],
}

# O vazamento aqui não é uma lista fixa: ele DEPENDE de qual alvo se escolheu.
# Modelar a nota com o rótulo dentro (ou vice-versa) dá AUC 1,0 / R² 1,0 — a
# resposta entrando pela janela. O ``features/`` monta a matriz assim:
#
#     alvo = PAPEIS_ALUNO["alvo"][0]                      # ou [1]
#     fora = set(PAPEIS_ALUNO["identificador"]) | set(VAZAMENTO_POR_ALVO[alvo])
#     X = df.drop(columns=[alvo, *fora])
#
# Escrever a lista na mão em cada notebook é como isso se perde.
VAZAMENTO_POR_ALVO = {
    ALVO_CLASSIFICACAO: [ALVO_REGRESSAO],
    ALVO_REGRESSAO: [ALVO_CLASSIFICACAO],
}

# Por que a nota entrou como segundo alvo (EDA de 04-05/09/2026):
# com as mesmas features e o mesmo grão (município+rede), o teto do oráculo é
# +6,4 pontos de acurácia na binária contra R² de 19,5% na contínua. A
# informação é a mesma; a acurácia é que não a expressa. E o corte 743 cai no
# percentil 41,6 — errar a nota por 10 pontos troca a classe de 17% dos alunos.
# Prever a nota e cortar depois recupera o classificador E devolve o limiar
# como parâmetro ajustável. O caminho inverso não existe.

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
