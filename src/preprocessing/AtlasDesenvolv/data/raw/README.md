# Camada Raw — Dados Oficiais do INEP

Esta pasta guarda os arquivos **exatamente como publicados pelo INEP**,
sem nenhuma transformação — espelhando a camada "Raw" do pipeline oficial
da Fase 2 ([postech-challenge-2](https://github.com/diego-nasc/postech-challenge-2)).

## ⚠️ Rodar localmente (não no ambiente do Claude)

O ambiente de execução do Claude tem a rede restrita a poucos domínios
(GitHub, PyPI, npm etc.) e **não consegue acessar `download.inep.gov.br`**.
Por isso, o download precisa ser feito na sua máquina local.

## Como baixar

### Opção 1 — script automatizado (recomendado)

```bash
cd tech-challenge-fase3
pip install requests
python src/preprocessing/download_raw_inep.py            # baixa 2023, 2024 e 2025
python src/preprocessing/download_raw_inep.py --ano 2024  # baixa só um ano
```

O script baixa os ZIPs de microdados, extrai apenas os 3 arquivos usados
no projeto (`TS_ALUNO.csv`, `TS_ESTADO.csv`, `TS_MUNICIPIO.csv`) e baixa
as planilhas de metas — tudo salvo em `data/raw/inep/`.

> **Atenção ao tamanho:** os ZIPs de microdados contêm registros de
> milhões de alunos e podem ter centenas de MB a alguns GB cada. Garanta
> espaço em disco e uma conexão estável.

### Opção 2 — download manual pelo navegador

| Ano | Tipo | URL |
|---|---|---|
| 2023 | Microdados | https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2023.zip |
| 2024 | Microdados | https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2024.zip |
| 2025 | Microdados | https://download.inep.gov.br/dados_abertos/microdados_AEEB_2025.zip |
| 2023 | Metas — municípios | https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_municipios.xlsx |
| 2023 | Metas — UFs | https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_ufs.xlsx |
| 2024 | Metas — municípios | https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_municipios_2024.xlsx |
| 2024 | Metas — UFs | https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_ufs_2024_2.xlsx |
| 2025 | Metas — municípios | https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_municipios_2025_v2.xlsx |
| 2025 | Metas — UFs | https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_ufs_2025_v1.xlsx |

De cada ZIP de microdados, extraia apenas:
- `DADOS/TS_ALUNO.csv` — microdados individuais dos alunos
- `DADOS/TS_ESTADO.csv` — indicadores agregados por UF
- `DADOS/TS_MUNICIPIO.csv` — indicadores agregados por município

## Estrutura esperada após o download

```
data/raw/inep/
├── microdados/
│   ├── 2023/
│   │   ├── microdados_avaliacao_da_alfabetizacao_2023.zip
│   │   └── DADOS/
│   │       ├── TS_ALUNO.csv
│   │       ├── TS_ESTADO.csv
│   │       └── TS_MUNICIPIO.csv
│   ├── 2024/ (mesma estrutura)
│   └── 2025/ (mesma estrutura, arquivo TS_ALUNO.csv pode ter nome AEEB)
└── metas/
    ├── 2023/
    │   ├── resultados_e_metas_municipios.xlsx
    │   └── resultados_e_metas_ufs.xlsx
    ├── 2024/ (mesma estrutura)
    └── 2025/ (mesma estrutura)
```

## Depois de baixar — próximos passos

1. **Confirme a leitura local:** os arquivos `TS_ALUNO.csv` costumam ser
   grandes (milhões de linhas). Ao ler localmente com pandas, considere
   usar `dtype` explícito ou ler em chunks se a memória for um problema.
2. **Camada bronze:** aplicar o mesmo contrato estrutural do pipeline
   oficial (schema explícito, seleção de colunas, conversão para Parquet)
   — ver `src/aws/glue_elt_bronze.py` no repositório da Fase 2 como
   referência da lógica (schemas por ano, tratamento de diferenças de
   layout entre 2023/2024/2025).
3. **Camada silver → gold:** replicar a lógica de `glue_elt_silver.py` e
   `glue_elt_gold.py` do repositório da Fase 2 (localmente com pandas ou
   PySpark local, sem AWS) para chegar à tabela final `aluno_contexto`
   com o schema já documentado em `data/bronze/../README` deste projeto.

## Sobre o schema alvo (`aluno_contexto`)

Depois de rodar sua própria pipeline local (bronze → silver → gold), o
dataset final deve ter o mesmo formato usado no projeto oficial:

| Papel | Colunas |
|---|---|
| Identificador | `id_aluno`, `ano`, `id_municipio`, `id_uf` |
| Atributos do aluno | `rede`, `caderno` |
| Contexto municipal | `ctx_taxa_municipio`, `ctx_media_municipio`, `ctx_meta_municipio`, `ctx_distancia_meta_municipio`, `ctx_atingiu_meta_municipio`, `ctx_participacao_municipio`, `ctx_categoria_municipio`, `ctx_faixa_participacao_municipio` |
| ⚠️ Vazamento — nunca usar como feature | `proficiencia`, `gap_proficiencia` |
| Alvo | `label_alfabetizado` |

Assim que você tiver esse CSV/Parquet final, é só me enviar (upload no
chat) que eu adapto toda a pipeline de modelagem para ele.
