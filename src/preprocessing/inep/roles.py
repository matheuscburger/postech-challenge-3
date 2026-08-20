"""Column roles for gold/aluno_contexto consumed by the ML pipeline."""

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
