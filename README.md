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

São cinco pipelines Medallion independentes, um por fonte, e um join que os
reúne. Cada um grava sua própria tabela Gold em `data/processed/`:

| Fonte | Tabela Gold | Grão | Linhas |
| --- | --- | --- | --- |
| INEP Alfabetização | `aluno` | ano × aluno | 5.320.732 |
| INEP Alfabetização | `municipio` | ano × município | 16.396 |
| INEP Alfabetização | `ufs` | ano × UF | 76 |
| Censo Escolar (ATU) | `atu_municipios` | ano × município × rede × localização | 198.903 |
| Censo Escolar (ATU) | `atu_brasil_regioes_ufs` | ano × recorte geográfico | 1.764 |
| IBGE | `populacao_municipios` | ano × município | 16.712 |
| Atlas do Desenv. Humano | `atlas_desenvolvimento_humano` | município (ano-base 2010) | 5.565 |
| FUNDEB (NSE) | `nse_entes_federados` | ano × ente (município e UF) | 11.190 |

`join.py` faz left-join das quatro fontes de contexto sobre `aluno` e grava a
tabela que a modelagem consome:

| Tabela | Grão | Forma |
| --- | --- | --- |
| `base_analitica` | ano × aluno | **5.320.732 × 85** — 9 colunas da `aluno` + 76 de contexto (`ctx_*`) |

O contrato completo da `base_analitica` — regra de defasagem, o que fica nulo em
2023 e por quê — está no doc do projeto, não aqui.

### Os dois alvos

`aluno` e `base_analitica` publicam **duas** colunas com prefixo `label_`, e a
ordem é proposital: a nota vem antes do rótulo porque é ela a medição.

- `label_proficiencia` — nota contínua, alvo de **regressão**
- `label_alfabetizado` — binária, alvo de **classificação**

`label_alfabetizado == (label_proficiencia >= 743)` bate em 100,0000% das linhas.
Logo são **mutuamente excludentes**: usar uma como feature da outra dá AUC 1,0.
Quem monta a matriz lê `VAZAMENTO_POR_ALVO` em `src/preprocessing/inep/roles.py`
— escrever a lista à mão em cada notebook é como isso se perde:

```python
from src.preprocessing.inep.roles import (
    ALVO_CLASSIFICACAO,   # label_alfabetizado
    ALVO_REGRESSAO,       # label_proficiencia
    PAPEIS_ALUNO,
    VAZAMENTO_POR_ALVO,
)

alvo = ALVO_REGRESSAO                                # ou ALVO_CLASSIFICACAO
fora = set(PAPEIS_ALUNO["identificador"]) | set(VAZAMENTO_POR_ALVO[alvo])
X = df.drop(columns=[alvo, *fora])
```

### Conferindo o join sem tocar em `data/`

```bash
python dryrun_join.py
```

Monta tabelas sintéticas em diretório temporário e roda os joins sobre elas.
24 conferências mais um controle negativo que reintroduz o proxy de NSE 2023 e
exige que o pipeline pare.

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
├── dryrun_join.py     <- Harness sintético do join (não toca em data/)
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
    ├── config.py               <- Paths do projeto, ANOS e CORTE_PROFICIENCIA
    │
    ├── preprocessing           <- I/O genérico, os cinco pipelines e o join
    │   ├── __init__.py
    │   ├── io.py               <- Parquet particionado, apply_schema
    │   ├── dq.py               <- Checks de qualidade compartilhados
    │   ├── load.py             <- Load CSV/Parquet from raw/processed
    │   ├── pipeline.py         <- ColumnTransformer factory (impute/encode/scale)
    │   ├── join.py             <- Left-joins de contexto -> base_analitica
    │   ├── prepare.py          <- CLI: os cinco pipelines + o join
    │   │
    │   ├── inep/               <- INEP Alfabetização (alvo + resultados)
    │   │   ├── download.py     <- Download INEP + unzip seletivo
    │   │   ├── schemas.py      <- Contratos Bronze
    │   │   ├── bronze.py       <- CSV/XLSX -> Parquet
    │   │   ├── silver.py       <- Conformação semântica
    │   │   ├── gold.py         <- aluno, municipio, ufs
    │   │   ├── quality.py      <- Checks de qualidade
    │   │   ├── roles.py        <- Papéis de colunas para ML (alvos e vazamento)
    │   │   └── run.py          <- Orquestrador download -> gold
    │   │
    │   ├── censoescolar/       <- Censo Escolar (ATU), mesma estrutura
    │   ├── ibge/               <- População e área municipal, mesma estrutura
    │   ├── atlas/              <- Atlas do Desenvolvimento Humano, mesma estrutura
    │   └── fundeb/             <- NSE dos entes federados, mesma estrutura
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
