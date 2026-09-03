"""Structural contracts for the Atlas do Desenvolvimento Humano Bronze/Silver layers.

Fonte primária: Base dos Dados (basedosdados.org), dataset mundo_onu.adh.
Fonte legada (auxiliar, apenas nome_municipio): réplica pública em CSV de
github.com/mauriciocramos/IDHM. Ambas derivam do arquivo oficial do
PNUD/IPEA/Fundação João Pinheiro (atlasbrasil.org.br). Validação cruzada
realizada em 01/09/2026 para 3 municípios x 3 anos-base — 16 indicadores
conferidos, sem divergências (tolerância 0.02).

⚠️ Durante essa validação foi corrigido um erro de mapeamento herdado da
primeira versão deste pipeline: os indicadores de pobreza PPOB/PMPOB/PIND
estavam com os rótulos trocados. Ver INDICADORES abaixo para o mapeamento
correto, conferido contra o dicionário oficial de dados.
"""

from __future__ import annotations

ANO_BASE_ATLAS = 2010  # ano mais recente disponível no Atlas (Censo 2010)

ARQUIVOS_BRONZE = {
    "municipio": "municipio_raw.csv",
    "uf": "uf_raw.csv",
    "brasil": "brasil_raw.csv",
}

# Colunas de identificação, já no formato Base dos Dados
COLUNAS_IDENTIFICACAO = {
    "ano": "ano",
    "id_municipio": "id_municipio",
}

# Indicadores selecionados (nome Base dos Dados -> nome final do projeto).
# Cada mapeamento foi validado numericamente contra a fonte legada e
# conferido contra o dicionário oficial de dados (dicionario_raw.csv).
INDICADORES = {
    # Síntese
    "idhm": "idhm",
    "idhm_e": "idhm_educacao",
    "idhm_r": "idhm_renda",
    "idhm_l": "idhm_longevidade",
    # Educação
    "taxa_analfabetismo_11_a_14": "taxa_analfabetismo_11a14",
    "taxa_analfabetismo_15_a_17": "taxa_analfabetismo_15a17",
    "taxa_analfabetismo_15_mais": "taxa_analfabetismo_15mais",
    "taxa_freq_6_14": "taxa_frequencia_6a14",
    "taxa_freq_4_5": "taxa_frequencia_4a5",
    "taxa_freq_0_3": "taxa_frequencia_0a3",
    "expectativa_anos_estudo": "expectativa_anos_estudo",
    "taxa_dom_sem_fund": "taxa_fundamental_incompleto",
    # Renda e desigualdade
    "renda_pc": "renda_per_capita",
    "indice_gini": "indice_gini",
    # ⚠️ Mapeamento corrigido — conferido contra dicionario_raw.csv:
    #   PPOB (% vulneráveis à pobreza) -> percentual_vulneraveis_pobreza
    #   PMPOB (% pobres) -> percentual_pobres
    #   PIND (% extremamente pobres) -> percentual_extremamente_pobres
    "prop_pobreza": "percentual_pobres",
    "prop_pobreza_extrema": "percentual_extremamente_pobres",
    "prop_vulner_pobreza": "percentual_vulneraveis_pobreza",
    # Infraestrutura / habitação
    "taxa_agua_encanada": "percentual_domicilios_agua",
    "taxa_energia_eletrica": "percentual_domicilios_energia",
    "taxa_densidade_2_mais": "taxa_densidade_domiciliar",
}

COLUNAS_GOLD = list(INDICADORES.values())
MUN_KEYS = ["ano", "id_municipio"]
