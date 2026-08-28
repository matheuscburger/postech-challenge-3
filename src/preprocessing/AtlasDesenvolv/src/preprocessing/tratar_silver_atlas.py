"""
Tratamento — Camada Silver: Atlas do Desenvolvimento Humano no Brasil
=========================================================================

Lê o dado bruto da camada bronze (data/bronze/atlas_desenvolvimento_humano/)
e aplica limpeza, padronização e seleção de indicadores, entregando uma
base pronta para ser usada em EDA/modelagem ou integrada (join) com a
base de alunos, usando `id_municipio` (código IBGE de 7 dígitos) como
chave — o mesmo padrão usado na tabela `aluno_contexto` da Fase 2.

Transformações aplicadas:
  1. Renomeia colunas de identificação para o padrão do projeto
     (id_municipio, id_uf, nome_municipio, ano).
  2. Seleciona apenas os indicadores relevantes ao problema de
     alfabetização (educação, renda, pobreza, infraestrutura), a partir
     do dicionário de dados.
  3. Filtra para o ano-base mais recente disponível (2010), evitando
     ambiguidade de "qual ano usar" numa futura integração.
  4. Valida tipos, duplicidades e nulos.
  5. Salva o resultado em data/silver/atlas_desenvolvimento_humano.csv.

Nada de regra de negócio do domínio de alfabetização (ex: cálculo de
metas, comparação com resultados de alunos) é aplicado aqui — isso fica
para quando este dataset for integrado à base de alunos (camada gold).
"""

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
BRONZE_DIR = BASE_DIR / "data" / "bronze" / "atlas_desenvolvimento_humano"
SILVER_DIR = BASE_DIR / "data" / "silver"

ANO_BASE = 2010  # ano mais recente disponível no Atlas (Censo 2010)

# Indicadores selecionados do dicionário (dicionario_raw.csv), relevantes
# ao problema de alfabetização: educação, renda, pobreza e infraestrutura.
# Mapeia SIGLA (nome original) -> nome final, mais legível, no padrão do projeto.
COLUNAS_INDICADORES = {
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
    "T_FUNDIN_TODOS": "taxa_fundamental_incompleto",
    # Renda e desigualdade
    "RDPC": "renda_per_capita",
    "GINI": "indice_gini",
    "PPOB": "percentual_pobres",
    "PMPOB": "percentual_extremamente_pobres",
    "PIND": "percentual_vulneraveis_pobreza",
    # Infraestrutura / habitação
    "T_AGUA": "percentual_domicilios_agua",
    "T_LUZ": "percentual_domicilios_energia",
    "T_DENS": "taxa_densidade_domiciliar",
}

COLUNAS_IDENTIFICACAO = {
    "ANO": "ano",
    "UF": "id_uf",
    "Codmun7": "id_municipio",
    "Município": "nome_municipio",
}


def carregar_bronze() -> pd.DataFrame:
    caminho = BRONZE_DIR / "municipal_raw.csv"
    df = pd.read_csv(caminho, sep=";", decimal=",", encoding="utf-8")
    return df


def tratar(df: pd.DataFrame) -> pd.DataFrame:
    colunas_selecionadas = list(COLUNAS_IDENTIFICACAO.keys()) + list(COLUNAS_INDICADORES.keys())
    faltantes = [c for c in colunas_selecionadas if c not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas esperadas não encontradas no bronze: {faltantes}")

    df_silver = df[colunas_selecionadas].copy()

    # Renomeia para o padrão do projeto
    df_silver = df_silver.rename(columns={**COLUNAS_IDENTIFICACAO, **COLUNAS_INDICADORES})

    # Padroniza tipos de identificação
    df_silver["id_municipio"] = df_silver["id_municipio"].astype(str).str.zfill(7)
    df_silver["id_uf"] = df_silver["id_uf"].astype(str).str.zfill(2)
    df_silver["nome_municipio"] = df_silver["nome_municipio"].str.strip().str.title()

    # Filtra para o ano-base mais recente (evita ambiguidade em joins futuros)
    df_silver = df_silver[df_silver["ano"] == ANO_BASE].reset_index(drop=True)

    # Validações básicas de qualidade
    dup = df_silver.duplicated(subset=["id_municipio"]).sum()
    if dup > 0:
        raise ValueError(f"{dup} município(s) duplicado(s) após filtro de ano — verifique a fonte.")

    nulos = df_silver.isnull().sum()
    nulos = nulos[nulos > 0]
    if len(nulos) > 0:
        print("Aviso — colunas com valores nulos após tratamento:")
        print(nulos)

    return df_silver


def main():
    print(f"Lendo camada bronze de: {BRONZE_DIR}")
    df_bronze = carregar_bronze()
    print(f"Bronze: {df_bronze.shape[0]} linhas, {df_bronze.shape[1]} colunas")

    df_silver = tratar(df_bronze)
    print(f"Silver (ano-base {ANO_BASE}): {df_silver.shape[0]} municípios, {df_silver.shape[1]} colunas")

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    destino = SILVER_DIR / "atlas_desenvolvimento_humano.csv"
    df_silver.to_csv(destino, index=False)
    print(f"Salvo em: {destino}")

    print("\nAmostra:")
    print(df_silver.head())

    return df_silver


if __name__ == "__main__":
    main()
