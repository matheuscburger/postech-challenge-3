# Resumo da Análise Exploratória — Indicador Criança Alfabetizada

> Base utilizada: `data/gold_alfabetizacao_simulado.csv` (simulada, 8.000
> registros). **Este relatório deve ser refeito com a base real da camada
> Gold assim que disponível** — a estrutura de análise (notebook
> `01_analise_exploratoria.ipynb`) já está pronta para isso, bastando trocar
> a fonte de dados.

## 1. Visão geral
- 8.000 registros, 21 colunas (identificação, território, socioeconômicas,
  educacionais, populacionais e alvo).
- Variável-alvo: `alfabetizado` (0 = não alfabetizado, 1 = alfabetizado).
- Distribuição do alvo: ~62% não alfabetizado / ~38% alfabetizado —
  desbalanceamento moderado.

## 2. Valores faltantes
- `renda_per_capita`, `inse_escola` e `frequencia_escolar_pct` possuem
  faltantes (entre 3% e 5%), simulando o que normalmente ocorre em bases
  públicas reais. Estratégia recomendada: imputação por mediana (numéricas)
  dentro do pipeline do Scikit-learn, após o split treino/teste.

## 3. Correlações com o alvo (nesta simulação)
| Variável | Correlação com `alfabetizado` |
|---|---|
| inse_escola | 0.106 |
| taxa_pobreza | -0.098 |
| professores_formacao_adequada_pct | 0.077 |
| infraestrutura_escola | 0.063 |
| taxa_frequencia_creche_pre | 0.061 |
| idh_municipio | 0.053 |
| frequencia_escolar_pct | 0.050 |
| renda_per_capita | 0.034 |
| razao_aluno_professor | -0.022 |
| meta_estadual_alfabetizacao | 0.008 |

Correlações individuais fracas são esperadas nesse tipo de problema — reforça
a necessidade de um modelo multivariado e de técnicas de interpretabilidade
(Feature Importance / SHAP) para capturar efeitos combinados.

## 4. Recortes territoriais
- Taxas de alfabetização variam por região, zona (urbana/rural) e porte do
  município (ver `images/06_taxa_por_categoria.png`).
- Regiões Norte e Nordeste tendem a apresentar taxas mais baixas na
  simulação — hipótese a validar com dado real.

## 5. Hipóteses para a etapa de modelagem
1. Efeito multifatorial — nenhuma variável isolada é suficiente.
2. INSE da escola e taxa de pobreza do município se destacam entre os
   fatores mais associados ao desfecho.
3. Formação docente e infraestrutura escolar têm relação positiva moderada.
4. Heterogeneidade regional relevante — sugere políticas regionalizadas.
5. Desbalanceamento de classes deve orientar a escolha de métricas
   (F1 / recall / AUC em vez de acurácia pura).

## 6. Cuidados para a próxima etapa (data leakage)
Variáveis que só ficam disponíveis **depois** de se saber se o aluno foi
alfabetizado (ex: resultado de avaliação de alfabetização do próprio ano de
referência) **não podem** ser usadas como preditoras — apenas variáveis
conhecidas *antes* ou *independentemente* do desfecho.

## 7. Próximos passos
- Testar hipóteses estatisticamente (teste t / qui-quadrado).
- Construir `ColumnTransformer` (imputação + encoding + scaling) integrado
  a um `Pipeline` do Scikit-learn.
- Treinar modelos baseline e avançados, validar com cross-validation.
- Aplicar Feature Importance / SHAP.
- Responder às perguntas de negócio do desafio (municípios de maior risco,
  clusters regionais, previsão de metas futuras).
