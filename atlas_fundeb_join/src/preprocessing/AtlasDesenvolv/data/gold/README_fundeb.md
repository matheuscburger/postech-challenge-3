# Camada Gold — Integração com FUNDEB (NSE)

Script: `src/preprocessing/gerar_gold_fundeb.py`

## O que faz

Segunda etapa da integração: parte do resultado de `gerar_gold_atlas.py`
(`aluno_contexto_enriquecido_atlas.csv`) e adiciona o Nível
Socioeconômico (NSE) do FUNDEB — tanto de município quanto de UF.

Fonte: tabela gold `nse_entes_federados` do pipeline FUNDEB
(`src/preprocessing/fundeb/gold.py`, repositório principal).

## Novas colunas

| Coluna | Descrição |
|---|---|
| `ctx_nse_municipio` | NSE do município do aluno |
| `ctx_ponderador_nse_municipio` | Ponderador do NSE (0,95–1,05) |
| `ctx_nse_municipio_proxy_2023` | `True` se o valor veio do proxy (ver abaixo) |
| `ctx_nse_uf` | NSE da UF do aluno (contexto adicional) |
| `ctx_ponderador_nse_uf` | Ponderador do NSE da UF |
| `ctx_nse_uf_proxy_2023` | `True` se o valor veio do proxy |

## Decisões de design (já validadas com você)

1. **Gap temporal 2023:** o FUNDEB só cobre 2024-2025; o ano de 2023 do
   INEP recebe o valor de **2024 como proxy** (NSE muda pouco ano a ano).
   As colunas `*_proxy_2023` marcam exatamente quais linhas usaram
   proxy — importante documentar isso no README final do projeto
   (seção "Limitações").
2. **NSE da UF como coluna separada** (não como fallback do NSE do
   município) — os dois convivem lado a lado.

## Teste realizado

Com dados sintéticos (200 alunos, reaproveitando os municípios do teste
do Atlas + NSE sintético para 2024/2025):

```
Cobertura NSE município: 100.0%
Cobertura NSE UF:        100.0%
Linhas usando proxy 2023: 58 de 200 (todas em ano=2023, nenhuma em 2024/2025)
Nulos introduzidos: 0
Linhas preservadas: 200 -> 200
Colunas: 33 -> 39
```

## Como rodar com dados reais

```bash
python src/preprocessing/gerar_gold_fundeb.py \
    caminho/aluno_contexto_enriquecido_atlas.csv \
    caminho/data/processed/nse_entes_federados
```

O segundo argumento pode ser o parquet particionado gerado pelo
`fundeb/gold.py` do repositório principal, ou um CSV equivalente.

## Ordem recomendada do pipeline completo

```
1. inep/gold.py               -> aluno_contexto (base real)
2. fundeb/gold.py              -> nse_entes_federados (base real)
3. gerar_gold_atlas.py          -> aluno_contexto_enriquecido_atlas.csv
4. gerar_gold_fundeb.py          -> aluno_contexto_enriquecido_atlas_fundeb.csv  (dataset final para modelagem)
```
