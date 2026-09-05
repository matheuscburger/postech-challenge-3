# postech-challenge-3

Tech Challenge da fase 3 da Postech AI Scientist na FIAP.

Alunos:

Diego Nascimento.

Matheus C. Bürger

Matheus Candido

## Pipeline de dados (local, pandas)

A fase 3 reutiliza o pipeline Medallion da fase 2 **sem AWS**. Os jobs Glue/S3
foram reescritos em pandas e gravam no layout cookiecutter:

| Fase 2 (S3)                   | Fase 3 (disco)                          |
| ----------------------------- | --------------------------------------- |
| `s3://raw/zip/`             | `data/external/{ano}/` (ZIPs do INEP) |
| `s3://raw/extracted/{ano}/` | `data/raw/{ano}/`                     |
| `s3://bronze/{entidade}/`   | `data/interim/bronze/{entidade}/`     |
| `s3://silver/{tabela}/`     | `data/interim/silver/{tabela}/`       |
| `s3://gold/{tabela}/`       | `data/processed/{tabela}/`            |

Tabelas Gold:

- `indicadores_municipio` — taxa, meta, distância e atingimento por município
- `indicadores_uf` — o mesmo recorte por UF
- `aluno_contexto` — microdados com contexto municipal e `label_alfabetizado`

O dicionário `PAPEIS_ALUNO_CONTEXTO` em `src/preprocessing/inep/roles.py` marca
`proficiencia` e `gap_proficiencia` como **vazamento** — não usar como feature.

### Como gerar os dados

```bash
python -m pip install -r requirements.txt
make data
```

## Atlas do Desenvolvimento Humano

Diferente das outras fontes (INEP, FUNDEB, Censo Escolar, IBGE), o Atlas do
Desenvolvimento Humano **não tem download automatizado** — o site oficial
(`atlasbrasil.org.br`) bloqueia acesso automatizado (scraping), então os
arquivos de origem precisam ser baixados manualmente uma vez, antes de
rodar o pipeline.

### De onde baixar

Os dados vêm de duas fontes, cruzadas e validadas entre si (ver
`src/preprocessing/atlas/schemas.py` para detalhes da validação):

1. **Fonte primária — Base dos Dados** (dataset `mundo_onu.adh`):
   - Acesse [basedosdados.org/dataset/mundo-onu-adh](https://basedosdados.org/dataset/mundo-onu-adh)
   - Baixe a tabela **`municipio`** (indicadores municipais — IDHM e ~230
     variáveis socioeconômicas)
   - Salve como `municipio_raw.csv`

2. **Fonte legada — apenas para nome do município** (a Base dos Dados só
   traz o código IBGE, não o nome):
   - [github.com/mauriciocramos/IDHM](https://github.com/mauriciocramos/IDHM)
   - Baixe `municipal.csv`
   - Renomeie para `municipal_raw.csv`

### Onde colocar

Crie a pasta (se não existir) e coloque os dois arquivos exatamente aqui:

```
data/external/atlas_desenvolvimento_humano/
├── municipio_raw.csv
└── municipal_raw.csv
```

```bash
mkdir -p data/external/atlas_desenvolvimento_humano
# depois, mova/copie os dois arquivos baixados para essa pasta
```

### Como rodar

```bash
python -m pip install -r requirements.txt

# 1. Gera a tabela Gold do Atlas (bronze -> silver -> gold)
python -m src.preprocessing.atlas.run

# 2. (Se ainda não rodou) Gera as outras tabelas Gold necessárias para o join
python -m src.preprocessing.inep.run
python -m src.preprocessing.fundeb.run
python -m src.preprocessing.censoescolar.run
python -m src.preprocessing.ibge.run

# 3. Junta tudo (aluno + Atlas + FUNDEB + Censo Escolar + IBGE + INEP) em base_analitica
python -m src.preprocessing.join
```

O resultado final fica em `data/processed/base_analitica/` (particionado
por ano), pronto para a etapa de modelagem.

### O que o Atlas adiciona à `base_analitica`

35 indicadores municipais (prefixo `ctx_atlas_`), cobrindo IDHM e seus 3
subíndices, analfabetismo por faixa etária, saúde da infância (mortalidade
até 1 e 5 anos), trabalho infantil, frequência escolar por idade,
vulnerabilidade familiar, renda e desigualdade. Ver a lista completa em
`src/preprocessing/atlas/schemas.py` (dicionário `INDICADORES`).

⚠️ **Limitação conhecida**: o Atlas está fixo no ano-base **2010** (Censo
Demográfico) — o mesmo valor é usado para todos os anos de `aluno`
(2023-2025), assumindo que indicadores socioeconômicos municipais mudam
devagar. Documentar isso na seção de Limitações do relatório final.

## Organização do Projeto

```
├── Makefile           <- Makefile with convenience commands like `make data` or `make train`
├── README.md          <- The top-level README for developers using this project.
├── data
│   ├── external       <- ZIPs originais do INEP
│   ├── interim
│   │   ├── bronze     <- Contrato estrutural (Parquet)
│   │   └── silver     <- Dados conformados (Parquet)
│   ├── processed      <- Tabelas Gold para modelagem
│   └── raw            <- CSV/XLSX extraídos da fonte
│
├── docs               <- A default mkdocs project; see www.mkdocs.org for details
│
├── models             <- Trained and serialized models, model predictions, or model summaries
│
├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),
│                         the creator's initials, and a short `-` delimited description, e.g.
│                         `1.0-jqp-initial-data-exploration`.
│
├── pyproject.toml     <- Project configuration file with package metadata for
│                         src and configuration for tools like black
│
├── references         <- Data dictionaries, manuals, and all other explanatory materials.
│
├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.
│   └── figures        <- Generated graphics and figures to be used in reporting
│
├── requirements.txt   <- The requirements file for reproducing the analysis environment, e.g.
│                         generated with `pip freeze > requirements.txt`
│
├── setup.cfg          <- Configuration file for flake8
│
└── src   <- Source code for use in this project.
    │
    ├── __init__.py             <- Makes src a Python module
    │
    ├── config.py               <- Paths do projeto e constantes INEP
    │
    ├── preprocessing           <- I/O genérico, sklearn preprocessor e pipeline INEP
    │   ├── __init__.py
    │   ├── io.py               <- Parquet particionado, apply_schema
    │   ├── load.py             <- Load CSV/Parquet from raw/processed
    │   ├── pipeline.py         <- ColumnTransformer factory (impute/encode/scale)
    │   ├── prepare.py          <- CLI (delega para inep.run_pipeline)
    │   └── inep/               <- Pipeline Medallion INEP Alfabetização
    │       ├── download.py     <- Download INEP + unzip seletivo
    │       ├── schemas.py      <- Contratos Bronze
    │       ├── bronze.py       <- CSV/XLSX -> Parquet
    │       ├── silver.py       <- Conformação semântica
    │       ├── gold.py         <- Tabelas analíticas
    │       ├── quality.py      <- Checks de qualidade
    │       ├── roles.py        <- Papéis de colunas para ML
    │       └── run.py          <- Orquestrador download -> gold
    │
    ├── modeling
    │   ├── __init__.py
    │   ├── predict.py          <- Code to run model inference with trained models
    │   └── train.py            <- Code to train models
    │
    ├── evaluation              <- Metrics, validation, and interpretability
    │
    └── visualization
        ├── __init__.py
        └── plots.py            <- Code to create visualizations
```

---

Projeto baseado no template [cookiecutter data science](https://drivendata.github.io/cookiecutter-data-science/).   #cookiecutterdatascience
