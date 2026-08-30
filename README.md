# postech-challenge-3

Tech Challenge da fase 3 da Postech AI Scientist na FIAP.

Alunos:

Diego Nascimento.

Matheus C. Bürger

Matheus Candido

## Pipeline de dados (local, pandas)

A fase 3 reutiliza o pipeline Medallion da fase 2 **sem AWS**. Os jobs Glue/S3
foram reescritos em pandas e gravam no layout cookiecutter:

| Fase 2 (S3) | Fase 3 (disco) |
|---|---|
| `s3://raw/zip/` | `data/external/{ano}/` (ZIPs do INEP) |
| `s3://raw/extracted/{ano}/` | `data/raw/{ano}/` |
| `s3://bronze/{entidade}/` | `data/interim/bronze/{entidade}/` |
| `s3://silver/{tabela}/` | `data/interim/silver/{tabela}/` |
| `s3://gold/{tabela}/` | `data/processed/{tabela}/` |

Tabelas Gold:

- `indicadores_municipio` — taxa, meta, distância e atingimento por município
- `indicadores_uf` — o mesmo recorte por UF
- `aluno_contexto` — microdados com contexto municipal e `label_alfabetizado`
- `aluno_joined` — `aluno_contexto` enriquecido com joins (ex.: ATU)

Os dicionários `PAPEIS_ALUNO_CONTEXTO` e `PAPEIS_ALUNO_JOINED` em
`src/preprocessing/roles.py` marcam `proficiencia` e `gap_proficiencia` como
**vazamento** — não usar como feature.


### Como gerar os dados

```bash
python -m pip install -r requirements.txt
make data
```


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
    │   ├── prepare.py          <- CLI (pipelines + join)
    │   ├── join.py             <- Joins sobre aluno_contexto -> aluno_joined
    │   ├── roles.py            <- Papéis de colunas para ML (contexto e joined)
    │   └── inep/               <- Pipeline Medallion INEP Alfabetização
    │       ├── download.py     <- Download INEP + unzip seletivo
    │       ├── schemas.py      <- Contratos Bronze
    │       ├── bronze.py       <- CSV/XLSX -> Parquet
    │       ├── silver.py       <- Conformação semântica
    │       ├── gold.py         <- Tabelas analíticas
    │       ├── quality.py      <- Checks de qualidade
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
