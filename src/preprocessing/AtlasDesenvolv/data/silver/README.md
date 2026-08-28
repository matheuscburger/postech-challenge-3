# Camada Silver — Atlas do Desenvolvimento Humano (tratado)

Arquivo: `atlas_desenvolvimento_humano.csv`
Script gerador: `src/preprocessing/tratar_silver_atlas.py`

## O que foi feito

Partindo do dado bruto em `data/bronze/atlas_desenvolvimento_humano/municipal_raw.csv`
(16.695 linhas, 237 colunas, 3 anos-base):

1. **Seleção de colunas** — de 237 indicadores, foram selecionados 20
   diretamente relevantes ao problema de alfabetização (educação, renda,
   pobreza, infraestrutura), a partir do dicionário de dados oficial.
2. **Renomeação** — colunas renomeadas para nomes legíveis e no padrão do
   projeto (ex: `T_ANALF15M` → `taxa_analfabetismo_15mais`).
3. **Padronização de chaves** — `Codmun7` → `id_municipio` (string,
   7 dígitos, zero-padded), `UF` → `id_uf` (string, 2 dígitos) — mesmo
   padrão de código IBGE usado na tabela `aluno_contexto` da Fase 2,
   viabilizando join futuro.
4. **Filtro de ano-base** — mantido apenas **2010** (ano mais recente
   disponível no Atlas), eliminando ambiguidade de "qual ano usar" e
   duplicidade de município (1 linha por município).
5. **Validação** — checagem de duplicatas por `id_municipio` (nenhuma
   encontrada) e de valores nulos (nenhum encontrado).

## Resultado

- **5.565 linhas** (1 por município brasileiro), **24 colunas**.
- Sem duplicatas, sem valores nulos.
- Nenhuma regra de negócio de alfabetização aplicada aqui (isso fica para
  a camada gold, quando/se este dataset for integrado à base de alunos).

## Colunas

| Coluna | Descrição |
|---|---|
| `ano` | Ano-base (sempre 2010 neste dataset) |
| `id_uf` | Código IBGE da UF (2 dígitos) |
| `id_municipio` | Código IBGE do município (7 dígitos) — chave para join |
| `nome_municipio` | Nome do município |
| `idhm` | IDH Municipal |
| `idhm_educacao` | IDHM — dimensão Educação |
| `idhm_renda` | IDHM — dimensão Renda |
| `idhm_longevidade` | IDHM — dimensão Longevidade |
| `taxa_analfabetismo_11a14` | Taxa de analfabetismo, 11 a 14 anos (%) |
| `taxa_analfabetismo_15a17` | Taxa de analfabetismo, 15 a 17 anos (%) |
| `taxa_analfabetismo_15mais` | Taxa de analfabetismo, 15 anos ou mais (%) |
| `taxa_frequencia_6a14` | Frequência escolar líquida, 6 a 14 anos (%) |
| `taxa_frequencia_4a5` | Frequência escolar, 4 a 5 anos (%) |
| `taxa_frequencia_0a3` | Frequência escolar, 0 a 3 anos (%) |
| `expectativa_anos_estudo` | Expectativa de anos de estudo |
| `taxa_fundamental_incompleto` | % com fundamental incompleto |
| `renda_per_capita` | Renda domiciliar per capita (R$, base 2010) |
| `indice_gini` | Índice de Gini (desigualdade de renda) |
| `percentual_pobres` | % da população pobre |
| `percentual_extremamente_pobres` | % da população extremamente pobre |
| `percentual_vulneraveis_pobreza` | % vulnerável à pobreza |
| `percentual_domicilios_agua` | % domicílios com água encanada |
| `percentual_domicilios_energia` | % domicílios com energia elétrica |
| `taxa_densidade_domiciliar` | Taxa de densidade domiciliar (moradores/dormitório) |

## Como usar / integrar depois

Para juntar com uma base de alunos que tenha `id_municipio` no mesmo
formato (código IBGE 7 dígitos), basta:

```python
import pandas as pd

atlas = pd.read_csv("data/silver/atlas_desenvolvimento_humano.csv", dtype={"id_municipio": str})
alunos = pd.read_csv("caminho/para/base_alunos.csv", dtype={"id_municipio": str})

base_enriquecida = alunos.merge(atlas, on="id_municipio", how="left", suffixes=("", "_atlas"))
```

⚠️ Como o Atlas está fixado em 2010 e a base de alunos da Fase 2 cobre
2023-2025, essa integração assume que os indicadores municipais do Atlas
(estruturais, de lenta mudança) ainda são representativos — uma limitação
a documentar no relatório final do projeto.
