# Camada Bronze — Dados Brutos

A camada bronze armazena os dados **exatamente como extraídos da fonte
original**, sem qualquer limpeza, renomeação ou regra de negócio aplicada.
O objetivo é ter um ponto de partida rastreável e reprodutível para as
camadas seguintes (silver/gold).

## Fontes disponíveis

### `atlas_desenvolvimento_humano/`

Dados do **Atlas do Desenvolvimento Humano no Brasil**, produzido por
PNUD, IPEA e Fundação João Pinheiro ([atlasbrasil.org.br](http://www.atlasbrasil.org.br)).

| Arquivo | Conteúdo | Linhas | Colunas |
|---|---|---|---|
| `municipal_raw.csv` | Indicadores por município (IDHM e 232 indicadores associados) | 16.695 (5.330 municípios × 3 anos-base) | 237 |
| `estadual_raw.csv` | Indicadores por UF | 81 (27 UFs × 3 anos-base) | 235 |
| `dicionario_raw.csv` | Dicionário de dados — nome, definição, categoria de cada indicador | 237 | 7 |
| `_metadata.json` | Metadados de proveniência (fonte, data de extração, URLs) | — | — |

- **Cobertura temporal:** anos-base 1991, 2000 e 2010 (Censos Demográficos).
- **Formato:** CSV separado por `;`, decimais com vírgula, encoding UTF-8.
- **Como foi obtido:** os dados foram baixados de uma réplica pública em
  CSV do dado bruto oficial ([github.com/mauriciocramos/IDHM](https://github.com/mauriciocramos/IDHM)),
  já que o ambiente de execução não tem acesso direto ao domínio
  `atlasbrasil.org.br`. **Recomenda-se ao time validar/rebaixar o arquivo
  oficial** (`atlas2013_dadosbrutos_pt.xlsx`) quando tiver acesso, e
  substituir os arquivos desta pasta mantendo a mesma estrutura.
- **Script de ingestão:** `src/preprocessing/ingest_bronze_atlas.py`
  (valida os arquivos e gera/atualiza `_metadata.json`).

## Indicadores mais relevantes para o Tech Challenge

Do dicionário (`dicionario_raw.csv`), os indicadores mais diretamente
relacionados ao problema de alfabetização são:

| Sigla | Nome | Categoria |
|---|---|---|
| `IDHM` | IDH Municipal | síntese |
| `IDHM_E` | IDHM — dimensão Educação | síntese |
| `T_ANALF11A14` | Taxa de analfabetismo de 11 a 14 anos | educação |
| `T_ANALF15A17` | Taxa de analfabetismo de 15 a 17 anos | educação |
| `T_ANALF15M` | Taxa de analfabetismo 15 anos ou mais | educação |
| `T_FREQ6A14` | Frequência escolar líquida de 6 a 14 anos | educação |
| `E_ANOSESTUDO` | Expectativa de anos de estudo | educação |
| `RDPC` | Renda domiciliar per capita | renda |
| `GINI` | Índice de Gini (desigualdade de renda) | renda |
| `PPOB` / `PMPOB` | % de pobres / extremamente pobres | vulnerabilidade |
| `T_AGUA` / `T_LUZ` | % domicílios com água / energia elétrica | habitação |

> Consulte `dicionario_raw.csv` para a lista completa dos 232 indicadores
> disponíveis.

## Regra da camada bronze

⚠️ **Nada de transformação aqui.** Limpeza de dados, padronização de
nomes de colunas, conversão de tipos, filtros de período ou joins com
outras fontes (como a base do Tech Challenge Fase 2) devem acontecer na
próxima camada (silver), não nesta.

## Próximos passos sugeridos

1. **Camada silver:** limpar tipos, padronizar nomes de município/UF
   (para permitir join com a base da Fase 2), filtrar para o ano-base mais
   recente (2010) ou interpolar/atualizar com fontes mais novas, selecionar
   apenas os indicadores relevantes ao problema.
2. **Integração com a camada gold:** juntar os indicadores do Atlas
   (nível município) com a base de alunos da Fase 2, usando `UF` +
   `Município` (ou código IBGE) como chave.
