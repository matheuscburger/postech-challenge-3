"""Column roles for ML: which columns are target, id, leakage, or features."""

from src.preprocessing.censoescolar.schemas import METRIC_COLS

CTX_ATU_FEATURES = [f"ctx_atu_{c.removeprefix('media_')}" for c in METRIC_COLS]

PAPEIS_ALUNO_CONTEXTO = {
    "alvo": ["label_alfabetizado"],
    "identificador": ["id_aluno", "ano", "id_municipio", "id_uf"],
    "vazamento": ["proficiencia", "gap_proficiencia"],
    "constante": [],
    "features": [
        "dependencia_administrativa",
        "caderno",
        "ctx_taxa_municipio",
        "ctx_media_municipio",
        "ctx_meta_municipio",
        "ctx_distancia_meta_municipio",
        "ctx_atingiu_meta_municipio",
        "ctx_participacao_municipio",
        "ctx_categoria_municipio",
        "ctx_faixa_participacao_municipio",
    ],
}

PAPEIS_ALUNO_JOINED = {
    "alvo": PAPEIS_ALUNO_CONTEXTO["alvo"],
    "identificador": PAPEIS_ALUNO_CONTEXTO["identificador"],
    "vazamento": PAPEIS_ALUNO_CONTEXTO["vazamento"],
    "constante": PAPEIS_ALUNO_CONTEXTO["constante"],
    "features": [
        *PAPEIS_ALUNO_CONTEXTO["features"],
        *CTX_ATU_FEATURES,
    ],
}
