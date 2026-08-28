"""
Ingestão — Camada Bronze: Atlas do Desenvolvimento Humano no Brasil
=====================================================================

Camada BRONZE = dado bruto, o mais próximo possível da fonte original,
sem transformação de regras de negócio. Aqui apenas:
  - baixamos o dado da fonte;
  - preservamos o arquivo original (ou uma cópia fiel);
  - registramos metadados de proveniência (fonte, data de extração, URL).

Qualquer limpeza, padronização de nomes de coluna, filtro de período,
tratamento de tipos etc. deve acontecer na camada SILVER (próxima etapa),
nunca aqui.

Fonte original dos dados
-------------------------
Atlas do Desenvolvimento Humano no Brasil — dados brutos municipais.
Autoria: PNUD, IPEA e Fundação João Pinheiro.
Site oficial: http://www.atlasbrasil.org.br
Arquivo oficial (xlsx): http://www.atlasbrasil.org.br/2013/data/rawData/atlas2013_dadosbrutos_pt.xlsx

Como o ambiente de execução deste projeto não tem acesso direto ao domínio
atlasbrasil.org.br, foi utilizada uma réplica em CSV do mesmo dado bruto,
publicada no repositório público:
https://github.com/mauriciocramos/IDHM (arquivos municipal.csv,
estadual.csv e dicionario.csv), extraída em conjunto com o Atlas
do Desenvolvimento Humano oficial.

⚠️ Se possível, recomenda-se ao time validar/baixar o arquivo oficial
diretamente de atlasbrasil.org.br e substituir os arquivos desta pasta,
mantendo a mesma estrutura de colunas.

Cobertura: 5.330 municípios brasileiros, 27 UFs, anos-base 1991, 2000 e
2010 (Censos Demográficos), 237 indicadores (demografia, educação, renda,
trabalho, habitação, vulnerabilidade).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BRONZE_DIR = Path(__file__).resolve().parents[2] / "data" / "bronze" / "atlas_desenvolvimento_humano"

SOURCES = {
    "municipal_raw.csv": {
        "descricao": "Indicadores municipais do Atlas do Desenvolvimento Humano (IDHM e componentes)",
        "url_replica": "https://raw.githubusercontent.com/mauriciocramos/IDHM/main/municipal.csv",
        "url_oficial": "http://www.atlasbrasil.org.br/2013/data/rawData/atlas2013_dadosbrutos_pt.xlsx",
    },
    "estadual_raw.csv": {
        "descricao": "Indicadores estaduais do Atlas do Desenvolvimento Humano",
        "url_replica": "https://raw.githubusercontent.com/mauriciocramos/IDHM/main/estadual.csv",
        "url_oficial": "http://www.atlasbrasil.org.br/2013/data/rawData/atlas2013_dadosbrutos_pt.xlsx",
    },
    "dicionario_raw.csv": {
        "descricao": "Dicionário de dados: nome, definição, categoria e subcategoria de cada indicador",
        "url_replica": "https://raw.githubusercontent.com/mauriciocramos/IDHM/main/dicionario.csv",
        "url_oficial": "http://www.atlasbrasil.org.br",
    },
}


def validar_arquivos():
    """Valida se os arquivos brutos existem e reporta shape/colunas básicas."""
    relatorio = {}
    for nome, meta in SOURCES.items():
        caminho = BRONZE_DIR / nome
        if not caminho.exists():
            raise FileNotFoundError(
                f"Arquivo {nome} não encontrado em {BRONZE_DIR}. "
                f"Baixe de: {meta['url_replica']}"
            )
        df = pd.read_csv(caminho, sep=";", decimal=",", encoding="utf-8")
        relatorio[nome] = {
            "linhas": len(df),
            "colunas": len(df.columns),
        }
    return relatorio


def gerar_metadata():
    """Gera o arquivo de metadados de proveniência da camada bronze."""
    relatorio = validar_arquivos()

    metadata = {
        "camada": "bronze",
        "assunto": "Atlas do Desenvolvimento Humano no Brasil (IDHM e indicadores associados)",
        "data_extracao_utc": datetime.now(timezone.utc).isoformat(),
        "autoria_dado_original": "PNUD, IPEA e Fundação João Pinheiro",
        "site_oficial": "http://www.atlasbrasil.org.br",
        "observacao": (
            "Dados baixados via réplica pública em CSV (github.com/mauriciocramos/IDHM), "
            "pois o ambiente de execução não tem acesso direto a atlasbrasil.org.br. "
            "Recomenda-se validar contra o arquivo oficial quando possível."
        ),
        "arquivos": {
            nome: {**meta, **relatorio[nome]} for nome, meta in SOURCES.items()
        },
        "cobertura": {
            "anos": [1991, 2000, 2010],
            "granularidade": "município",
            "unidade_federativa": "todas as 27 UFs",
        },
        "regra_camada_bronze": (
            "Nenhuma transformação de regra de negócio deve ser aplicada aqui. "
            "Limpeza, renomeação de colunas, filtros e joins ficam na camada silver."
        ),
    }

    with open(BRONZE_DIR / "_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return metadata


if __name__ == "__main__":
    meta = gerar_metadata()
    print("Metadados da camada bronze gerados com sucesso:")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
