"""Structural contracts for the Atlas do Desenvolvimento Humano Bronze/Silver layers.

Fonte
-----
Espelho público em CSV do Atlas (``github.com/mauriciocramos/IDHM``), réplica
fiel do arquivo do PNUD/IPEA/Fundação João Pinheiro publicado em
``atlasbrasil.org.br``. Um único arquivo, 237 colunas com as **siglas
originais do Atlas**, cobrindo as três coortes do índice — 1991, 2000 e 2010
— com 5.565 municípios em cada uma.

O espelho substituiu a Base dos Dados (dataset ``mundo_onu.adh``) como fonte
deste pipeline: o dado lá é distribuído por BigQuery, o que exige conta Google
Cloud autenticada e billing project por pessoa. Não é download HTTP, então não
dava para automatizar nem para pedir que cada colega configurasse uma conta GCP
só para rodar o pipeline. O espelho é baixável por HTTP simples, traz as mesmas
variáveis e é a mesma origem — ver ``download.py``.

Validação cruzada realizada em 01/09/2026 para 3 municípios x 3 anos-base —
16 indicadores conferidos, sem divergências (tolerância 0.02).

⚠️ Durante essa validação foi corrigido um erro de mapeamento herdado da
primeira versão deste pipeline: os indicadores de pobreza PPOB/PMPOB/PIND
estavam com os rótulos trocados. Ver INDICADORES abaixo para o mapeamento
correto, conferido contra o dicionário oficial de dados. O que **prova** o
mapeamento não é o nome e sim o aninhamento PIND ⊆ PMPOB ⊆ PPOB: extremamente
pobres são um subconjunto dos pobres, que são um subconjunto dos vulneráveis.
A relação vale nos 5.565 municípios de 2010 — se as siglas girarem de novo,
ela quebra.
"""

from __future__ import annotations

ANO_BASE_ATLAS = 2010  # ano mais recente disponível no Atlas (Censo 2010)

# Nome do arquivo baixado por download.py. Uma constante só, usada tanto por
# quem grava quanto por quem lê: a divergência entre os dois nomes é o que
# deixou um CSV com o dialeto errado passar pela checagem de existência.
ARQUIVO_BRONZE = "municipal_raw.csv"

# Dialeto em que a fonte publica o arquivo. Explícito porque ler com o dialeto
# errado não falha na primeira linha: as coortes têm quantidades diferentes de
# células vazias, então o parser só quebra lá pela linha 5.567, na virada de
# 1991 para 2000, com um "Expected 115 fields, saw 159" que não diz nada sobre
# a causa real.
DIALETO_BRONZE = {"sep": ";", "decimal": ",", "encoding": "utf-8"}

# Colunas de identificação (sigla do Atlas -> nome final do projeto).
COLUNAS_IDENTIFICACAO = {
    "ANO": "ano",
    "Codmun7": "id_municipio",
    "Município": "nome_municipio",
}

# Indicadores selecionados (sigla do Atlas -> nome final do projeto).
# Cada mapeamento foi conferido contra o dicionário oficial de dados do Atlas.
#
# Lista expandida em 04/09/2026 com 16 indicadores adicionais, escolhidos
# para responder diretamente às perguntas de negócio do desafio — em
# especial "quais municípios apresentam maior risco educacional?" e "quais
# fatores mais impactam a alfabetização?" — cobrindo saúde da infância,
# trabalho infantil, frequência escolar por faixa etária e capital
# educacional dos pais/responsáveis (ver seções abaixo).
INDICADORES = {
    # Síntese
    "IDHM": "idhm",
    "IDHM_E": "idhm_educacao",
    "IDHM_R": "idhm_renda",
    "IDHM_L": "idhm_longevidade",
    # Educação
    "T_ANALF11A14": "taxa_analfabetismo_11a14",
    "T_ANALF15A17": "taxa_analfabetismo_15a17",
    "T_ANALF15M": "taxa_analfabetismo_15mais",
    "T_FREQ6A14": "taxa_frequencia_6a14",
    "T_FREQ4A5": "taxa_frequencia_4a5",
    "T_FREQ0A3": "taxa_frequencia_0a3",
    "E_ANOSESTUDO": "expectativa_anos_estudo",
    # T_FUNDIN_TODOS: % de pessoas em domicílios em que ninguém tem
    # fundamental completo (não é "taxa de fundamental incompleto" da pessoa).
    "T_FUNDIN_TODOS": "taxa_fundamental_incompleto",
    # Renda e desigualdade
    "RDPC": "renda_per_capita",
    "GINI": "indice_gini",
    "THEIL": "indice_theil",
    "R1040": "razao_10_ricos_40_pobres",
    # ⚠️ Mapeamento corrigido — conferido contra o dicionário oficial:
    #   PIND  (% extremamente pobres)     -> percentual_extremamente_pobres
    #   PMPOB (% pobres)                  -> percentual_pobres
    #   PPOB  (% vulneráveis à pobreza)   -> percentual_vulneraveis_pobreza
    # Os três são percentuais legítimos na mesma faixa: nenhuma checagem de
    # tipo ou range pega uma rotação entre eles. Só o aninhamento pega.
    "PMPOB": "percentual_pobres",
    "PIND": "percentual_extremamente_pobres",
    "PPOB": "percentual_vulneraveis_pobreza",
    "PMPOBCRI": "percentual_pobres_criancas",
    "PINDCRI": "percentual_extremamente_pobres_criancas",
    "PPOBCRI": "percentual_vulneraveis_pobreza_criancas",
    # Saúde da infância (óbitos por mil nascidos vivos — não é percentual)
    "MORT1": "mortalidade_ate_1_ano",
    "MORT5": "mortalidade_ate_5_anos",
    # Trabalho infantil e vulnerabilidade da criança
    "T_ATIV1014": "taxa_trabalho_infantil_10a14",
    "T_M10A14CF": "taxa_maes_10a14",
    "T_MULCHEFEFIF014": "taxa_maes_chefes_familia",
    # Frequência escolar por faixa etária
    "T_FORA4A5": "taxa_fora_escola_4a5",
    "T_FORA6A14": "taxa_fora_escola_6a14",
    "T_FLFUND": "taxa_frequencia_liquida_fundamental",
    # Capital educacional dos pais/responsáveis
    "T_FUNDIN_TODOS_MMEIO": "taxa_domicilios_vulneraveis_sem_fundamental",
    "T_CRIFUNDIN_TODOS": "taxa_criancas_em_domicilios_sem_fundamental",
    # Infraestrutura / habitação
    # T_DENS: % da população em domicílios com densidade > 2 moradores por
    # dormitório (adensamento excessivo).
    "T_AGUA": "percentual_domicilios_agua",
    "T_LUZ": "percentual_domicilios_energia",
    "T_DENS": "taxa_densidade_domiciliar",
}

COLUNAS_GOLD = list(INDICADORES.values())
MUN_KEYS = ["ano", "id_municipio"]
