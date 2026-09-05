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
#
# Lista expandida em 04/09/2026 com 16 indicadores adicionais, escolhidos
# para responder diretamente às perguntas de negócio do desafio — em
# especial "quais municípios apresentam maior risco educacional?" e "quais
# fatores mais impactam a alfabetização?" — cobrindo saúde da infância,
# trabalho infantil, frequência escolar por faixa etária e capital
# educacional dos pais/responsáveis (ver seções abaixo).
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
    "indice_theil": "indice_theil",
    "razao_10_ricos_40_pobres": "razao_10_ricos_40_pobres",
    # ⚠️ Mapeamento corrigido — conferido contra dicionario_raw.csv:
    #   PPOB (% vulneráveis à pobreza) -> percentual_vulneraveis_pobreza
    #   PMPOB (% pobres) -> percentual_pobres
    #   PIND (% extremamente pobres) -> percentual_extremamente_pobres
    "prop_pobreza": "percentual_pobres",
    "prop_pobreza_extrema": "percentual_extremamente_pobres",
    "prop_vulner_pobreza": "percentual_vulneraveis_pobreza",
    "prop_pobreza_criancas": "percentual_pobres_criancas",
    "prop_pobreza_extrema_criancas": "percentual_extremamente_pobres_criancas",
    "prop_vulner_pobreza_criancas": "percentual_vulneraveis_pobreza_criancas",
    # Saúde da infância
    "mortalidade_1": "mortalidade_ate_1_ano",
    "mortalidade_5": "mortalidade_ate_5_anos",
    # Trabalho infantil e vulnerabilidade da criança
    "taxa_atividade_10_14": "taxa_trabalho_infantil_10a14",
    "taxa_mulheres_com_filho_10_14": "taxa_maes_10a14",
    "taxa_mulheres_chefe_filho_15m": "taxa_maes_chefes_familia",
    # Frequência escolar por faixa etária
    "taxa_criancas_fora_escola_4_5": "taxa_fora_escola_4a5",
    "taxa_criancas_fora_escola_6_14": "taxa_fora_escola_6a14",
    "taxa_freq_liquida_fundamental": "taxa_frequencia_liquida_fundamental",
    # Capital educacional dos pais/responsáveis
    "taxa_dom_vulner_sem_fund": "taxa_domicilios_vulneraveis_sem_fundamental",
    "taxa_criancas_dom_sem_fund": "taxa_criancas_em_domicilios_sem_fundamental",
    # Infraestrutura / habitação
    "taxa_agua_encanada": "percentual_domicilios_agua",
    "taxa_energia_eletrica": "percentual_domicilios_energia",
    "taxa_densidade_2_mais": "taxa_densidade_domiciliar",
}

COLUNAS_GOLD = list(INDICADORES.values())
MUN_KEYS = ["ano", "id_municipio"]
