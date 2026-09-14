# postech-challenge-3

Tech Challenge da fase 3 da Postech AI Scientist na FIAP — **Predição e
Inteligência Analítica para Alfabetização no Brasil**.

Alunos:

Diego Nascimento.

Matheus C. Bürger

Matheus Candido

---

## Contexto do problema

A alfabetização infantil ao final do 2º ano do ensino fundamental é um dos
indicadores mais sensíveis do desenvolvimento educacional e social do país. O
MEC e o INEP criaram em 2023 o **Indicador Criança Alfabetizada** justamente
para medir isso de forma padronizada — mas medir não é o mesmo que agir:
gestores públicos precisam **antecipar risco**, identificar **quais
municípios e regiões concentram vulnerabilidade educacional**, e entender
**quais fatores realmente pesam** no resultado, antes que o próximo ciclo de
avaliação aconteça.

Este projeto dá continuidade à Fase 2 do Tech Challenge, que construiu o
pipeline de engenharia de dados (Medallion: bronze → silver → gold) que
integra o Indicador Criança Alfabetizada com contexto territorial,
socioeconômico e educacional de cinco fontes públicas. Nesta fase, esses
dados viram análise exploratória, modelos preditivos e recomendações de
política pública.

## Objetivo analítico

Responder cinco perguntas de negócio sobre alfabetização municipal, cada uma
com um alvo formal definido na EDA (`EDA_DMN.ipynb`, seção 12.1):

| Pergunta | Alvo | Tipo |
| --- | --- | --- |
| **Q1** — Quais fatores mais impactam a alfabetização? | `taxa_realizada` | regressão |
| **Q2** — Quais municípios apresentam maior risco educacional? | `risco_educacional = 1[taxa_realizada < 50]` | classificação binária |
| **Q3** — Quais regiões possuem padrões semelhantes? | — | clustering (sem alvo) |
| **Q4** — Como prever municípios que podem não atingir metas futuras? | `risco_nao_atingir_meta = 1[taxa_realizada < meta]` | classificação binária |
| **Q5** — Quais variáveis possuem maior influência nos modelos? | — | interpretabilidade dos modelos acima |

O corte de 50% em Q2 não foi escolhido para maximizar balanceamento: ele
corresponde a uma fronteira já presente na escala oficial de alfabetização
(identifica municípios em que menos da metade das crianças alfabetiza) —
interpretação substantiva, não estatística.

O critério de sucesso não é métrica alta isolada, mas **inteligência
aplicável**: cada resposta acima devia poder virar uma frase que um gestor
público entende e usa para decidir onde agir.

## Descrição da base utilizada

A base final (`data/processed/base_analitica`) integra cinco fontes públicas
via o pipeline Medallion da Fase 2, reescrito em pandas puro (sem AWS):

| Fonte | O que contribui | Prefixo das colunas |
| --- | --- | --- |
| INEP — Alfabetização | microdados de aluno (alvo + `dependencia_administrativa`) | — |
| Censo Escolar (ATU) | razão aluno/turma por etapa de ensino, por município e rede | `ctx_atu_*` |
| Atlas do Desenvolvimento Humano | 35 indicadores socioeconômicos (IDHM, pobreza, saúde infantil, frequência escolar), ano-base 2010 | `ctx_atlas_*` |
| FUNDEB | Nível Socioeconômico (NSE) do ente federado | `ctx_fundeb_*` |
| IBGE | população, área, saneamento, renda domiciliar | `ctx_ibge_*` |
| INEP (gold município/UF) | taxa/média/meta de alfabetização, **defasadas 1 ano** (`_lag1`) | `ctx_inep_*` |

**Grão nominal:** 1 linha por aluno-ano — **5.320.732 linhas × 85 colunas**
(9 colunas próprias do aluno + 76 de contexto `ctx_*`), edições **2023,
2024, 2025**.

**Dois alvos, mutuamente excludentes** (`src/preprocessing/inep/roles.py`):
`label_alfabetizado` (binário) e `label_proficiencia` (contínuo), com
`label_alfabetizado == (label_proficiencia >= 743)` em 100% das linhas — usar
uma como feature da outra é vazamento garantido.

### O achado que redefiniu a unidade de análise

A auditoria de granularidade da EDA (`EDA_DMN.ipynb`, seção 10.1) mediu algo
que muda tudo o que vem depois: a matriz de atributos tem 1,85 milhão de
linhas (aluno-ano em 2024), mas só **cerca de 6,5 mil linhas distintas**.
54 das 76 features de contexto são constantes dentro do município; as 22
restantes (bloco ATU) variam por **município + rede de ensino**, com no
máximo dois valores. A mediana é de **91 alunos compartilhando o mesmo vetor
de atributos**, e o máximo chega a 52.622.

**Decisão consolidada:** a unidade de análise da modelagem é o
**município (× rede) - ano**, não o aluno individual — nenhuma das 76
features de contexto descreve a criança. Essa conclusão foi confirmada de
forma independente por uma segunda EDA (`3.0-mc-eda-base-completa.ipynb`,
Matheus Candido), que mediu o mesmo efeito por outro caminho: um split
aleatório de linhas vaza o mesmo aluno entre treino e teste em 70,9% dos
casos, porque o `id_aluno` não é um identificador de pessoa estável — os
dois primeiros dígitos reproduzem o código da UF em 100% das linhas, e o
mesmo ID aponta para o mesmo município em apenas ~15% dos casos entre
edições. Duas auditorias, dois métodos, a mesma conclusão.

## Etapas de modelagem

A linha adotada como principal é a de Diego Nascimento — uma sequência de
notebooks onde cada decisão de modelagem é registrada com a evidência que a
sustenta, **antes** de seguir para a próxima etapa:

1. **`EDA_DMN.ipynb`** — auditoria de qualidade e granularidade (11
   verificações formais: duplicidade, natureza do `id_aluno`, nulos
   estruturais por ano, targets inválidos, municípios sem meta, features
   constantes, leakage, inconsistência de ano, cobertura entre anos, tamanho
   de amostra por município, distribuição das probabilidades), seleção de
   features (>10% de nulos em 2024 → remove; redundância via Spearman
   municipal com corte `|ρ| ≥ 0,90` → um representante por componente
   conectado), definição formal dos 4 alvos acima.
2. **`Preparacao_para_modelagem_GOLD_analítica.ipynb`** — aplica as decisões
   da EDA sem repeti-las: reconstrói a unidade município-ano, remove as 12
   features por missingness e as 27 por redundância já identificadas, separa
   **2024 (desenvolvimento) / 2025 (teste temporal)** antes de qualquer
   imputação, e preserva os nulos remanescentes para tratamento **dentro do
   `Pipeline`** — nunca antes.
3. **`Q1_ML_Regressao_DMN.ipynb`** a **`Q4_ML_Classificacao_DMN.ipynb`** — um
   notebook por pergunta de negócio, cada um seguindo o mesmo desenho:
   baseline → comparação de modelos por cross-validation em 2024 →
   diagnóstico de overfitting (gap treino/validação) → otimização restrita a
   2024 → ajuste final em 100% de 2024 → **um único** teste em 2025 →
   interpretabilidade (Permutation Importance + SHAP).
4. **Validação cruzada** — duas outras linhas de modelagem foram construídas
   de forma independente sobre o mesmo problema (`modelo_alfabetizacao_municipal_MCB.ipynb`,
   de Matheus Bürger, e `5.0-mc-modelagem-alfabetizacao.ipynb`, de Matheus
   Candido). Nenhuma das duas substitui a linha do Diego — servem para
   checar se os números e os fatores mais importantes se repetem quando o
   pipeline de features e o algoritmo mudam. Ver "Métricas de avaliação".

### Prevenção de vazamento (data leakage)

- `label_alfabetizado` e `label_proficiencia` nunca coexistem como
  feature/alvo (`VAZAMENTO_POR_ALVO` em `roles.py`).
- Resultados do INEP (`taxa`, `média_português`, `nível`, `participação`)
  entram **defasados 1 ano** (`_lag1`); só `meta` entra sem defasagem, porque
  é publicada **antes** da avaliação. Em Q4, `taxa_lag1` é removida de `X`
  porque `esforco_pactuado = meta − taxa_lag1` criaria uma relação algébrica
  perfeita entre três variáveis.
- `id_aluno` não é estável entre edições (achado da seção "Descrição da
  base") — por isso a validação é temporal (2024→2025), nunca um split
  aleatório por aluno.
- Todo pré-processamento que aprende parâmetros (imputação, scaling,
  encoding) fica dentro do `Pipeline`, ajustado só no fold/partição de
  treino; o teste de 2025 é acessado **uma única vez**, depois de a
  configuração do modelo estar congelada.

## Escolha do algoritmo

Cada pergunta comparou explicitamente um baseline, um modelo linear e um
modelo de árvore/boosting, por cross-validation em 2024 — a escolha final
não é a mesma em todas:

| Pergunta | Candidatos comparados | Vencedor | Por quê |
| --- | --- | --- | --- |
| Q1 (regressão da taxa) | média constante, `taxa_lag1` como previsão, linear simples, OLS múltipla, Ridge, Random Forest | **Random Forest** (com `max_depth`/`min_samples_*` ajustados após diagnóstico de overfitting) | menor MAE de CV (8,597 vs 10,007 do Ridge); a relação entre histórico municipal e taxa atual não é linear |
| Q2 (risco educacional) | classe majoritária, Regressão Logística (padrão/balanceada), Árvore, Random Forest (padrão/balanceada) | **Regressão Logística balanceada** | maior Recall de CV (0,775 vs 0,600 da versão padrão) com boa estabilidade (`gap_Recall` = 0,006) — sem precisar da complexidade da árvore |
| Q3 (padrões municipais) | K-Means (k=2 a 8), avaliado por Inertia + Silhouette | **nenhum k declarado ótimo** | cotovelo sem inflexão clara e silhueta baixa/próxima em todo o intervalo testado — decisão metodológica deliberada de não forçar uma segmentação que os dados não sustentam |
| Q4 (risco de não atingir meta) | `DummyClassifier`, regra de negócio (`esforco_pactuado > 0`), Regressão Logística balanceada, Árvore de Decisão | **Regressão Logística balanceada**, threshold operacional ajustado para **0,40** (não 0,5) via probabilidades out-of-fold | a regra de negócio sinaliza muito mas discrimina pouco (Balanced Accuracy ≈ 0,50); a Logística equilibra Recall e Precision melhor que a árvore |

Não é uma preferência cega por modelos complexos: a escolha caiu para o
linear sempre que ele entregou desempenho comparável com mais
transparência, e para a árvore só quando o ganho foi real e mensurável (Q1).

**Validação cruzada:** as outras duas abordagens usaram predominantemente
Random Forest/HistGradientBoosting e chegaram a números próximos aos do
Diego na Q4 (ver tabela abaixo) — evidência de que a escolha por modelos
mais simples nas Q2/Q4 não deixou desempenho relevante na mesa.

## Métricas de avaliação

**Q1 — regressão da taxa de alfabetização municipal**

| Etapa | MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| Baseline `taxa_lag1` (CV 2024) | 12,514 | — | — |
| Random Forest (CV 2024) | 8,597 | — | — |
| Baseline `taxa_lag1` (teste 2025, 5.441 obs. comparáveis) | 13,100 | 17,130 | −0,182 |
| **Random Forest otimizada (teste 2025)** | **10,319** | **13,052** | **0,314** |

Ganho da Random Forest sobre o baseline de persistência: **2,78 p.p. de MAE
(21,2% relativo)**. No teste completo de 2025: MAE 10,362 / RMSE 13,104 / R²
0,316.

**Q2 — classificação de risco educacional (`taxa < 50%`)**

| | Recall | Precision | F1 | PR-AUC | ROC-AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| CV 2024 | 0,775 | 0,608 | 0,681 | 0,741 | 0,883 |
| Teste temporal 2025 | **0,843** | 0,239 | — | — | 0,867 |

A prevalência do risco caiu de 25,8% (2024) para 8,9% (2025) — mudança
temporal relevante que reduz a Precision no teste sem comprometer o Recall.

**Q4 — classificação de risco de não atingir a meta**

| | PR-AUC | ROC-AUC | Recall (thr=0,40) | Precision |
| --- | ---: | ---: | ---: | ---: |
| OOF 2024 | 0,673 | 0,738 | 0,844 | 0,576 |
| **Teste temporal 2025 (linha oficial, Diego)** | **0,555** | **0,737** | **0,805** | 0,375 |
| Validação cruzada — HistGB balanceado (Matheus Candido, `5.0`) | 0,534 | 0,747 | 0,790 | 0,400 |
| Validação cruzada — classificador derivado da regressão de taxa, em vez de dedicado (`5.0`) | 0,471 | 0,667 | 0,797 | — |

O ROC-AUC praticamente não se move entre a linha oficial e a validação
cruzada (0,737 vs 0,747) apesar de features e algoritmo diferentes — sinal
de que a dificuldade real do problema, não a escolha de pipeline, é o que
limita o resultado.

**Critério de escolha de métrica:** Recall/PR-AUC priorizados sobre
Accuracy/Precision em todos os classificadores — o custo de negócio de não
sinalizar um município em risco (falso negativo) é maior que o de investigar
um que não precisava (falso positivo).

## Interpretação dos resultados

**Q1 (Permutation Importance + SHAP, com forte concordância entre os dois
métodos — as 5 variáveis mais importantes aparecem na mesma ordem nos
dois):**

1. `proficiencia_lag1` — desempenho/proficiência anterior do município
2. `ctx_inep_uf_media_portugues_lag1` — desempenho médio anterior em Língua
   Portuguesa, no contexto da UF
3. `taxa_lag1` — taxa de alfabetização anterior do município

**Q2/Q4 (coeficientes padronizados da Regressão Logística):** coeficiente
positivo aumenta o escore de risco, negativo reduz; maior valor absoluto,
maior peso na decisão linear. Leitura sempre preditiva, nunca causal.

**Leitura de negócio, reforçada pela seção "Separação de classes por
feature" da EDA (`EDA_DMN.ipynb`, seção 5.1):** com quase 1,9 milhão de
linhas, quase toda variável é estatisticamente significativa a 5% — mas
significância não é relevância. O maior tamanho de efeito isolado medido foi
**~0,27** (desempenho municipal defasado do INEP): nenhuma feature sozinha
separa bem as classes, o ganho vem da combinação de features feita pelo
modelo. O melhor preditor de alfabetização futura de um município é o seu
**próprio desempenho passado** — persistência regional, não nível
socioeconômico isolado.

**Validação cruzada:** a mesma família de fatores (histórico municipal
defasado + meta pactuada) aparece no topo do ranking de importância também
na abordagem do `5.0`, com um pipeline de features e algoritmo
independentes — segunda confirmação do mesmo achado.

## Insights encontrados

- **Nenhuma feature isolada explica a alfabetização — o histórico municipal
  defasado é o que mais se aproxima disso**, com tamanho de efeito ~0,27
  contra o alvo. Índices socioeconômicos (IDHM, renda) entram no modelo, mas
  raramente no topo do ranking de importância.
- **Cumprir a meta é uma dimensão diferente de alfabetizar bem.** Em 2025, o
  Rio Grande do Sul tem taxa de alfabetização de 64,9% mas meta de 71,6% —
  71,6% dos seus municípios não cumpriram; Alagoas alfabetiza menos em
  termos absolutos (70,0%) mas pactuou meta de 56,0% — só 4,9% não
  cumpriram. No Brasil todo, 27,3% dos municípios com meta válida em 2025
  não a atingiram, incluindo 1.129 municípios já no nível 2 ou superior de
  alfabetização — cumprir/não cumprir a meta não é um proxy de qualidade
  educacional absoluta.
- **A prevalência do alvo muda entre as edições** — de 58,4% (2023) para
  59,8% (2024) e 66,3% (2025) — o que torna a validação temporal obrigatória
  e explica por que os modelos, calibrados em 2024, perdem Precision (não
  Recall) quando testados em 2025.
- **O grão real da base é município×rede, não aluno.** Uma auditoria
  detectou isso pela estrutura da matriz (6,5 mil vetores distintos em 1,85
  milhão de linhas); uma segunda EDA, independente, chegou à mesma conclusão
  medindo vazamento de split (70,9% de linhas de teste com aluno já visto no
  treino). Toda a estratégia de modelagem — grão, features, validação —
  decorre desse achado.
- **Classificador dedicado bate o derivado** (validação cruzada, `5.0`,
  seção 6): treinar o risco de não atingir a meta como classificador próprio
  supera aplicar um corte sobre a regressão da taxa, nas duas métricas
  (PR-AUC 0,534 vs 0,471; ROC-AUC 0,747 vs 0,667) — reforça a decisão do
  Diego de tratar Q2 e Q4 como problemas de classificação dedicados, e não
  como derivações de Q1.
- **Municípios pequenos distorcem taxas municipais brutas**: 23% dos
  municípios têm menos de 50 alunos avaliados, e a taxa observada nessas
  faixas é sistematicamente mais extrema (mais perto de 0% ou 100%) por
  ruído amostral — qualquer ranking de risco por município precisa
  considerar o tamanho da amostra, não só a taxa pontual.

## Limitações do projeto

- **Grão municipal (ou município×rede), não individual.** O que os modelos
  preveem é o comportamento esperado do território, não do aluno.
- **Q3 não tem resposta fechada.** A linha oficial (Diego, K-Means k=2 a 8)
  concluiu que os dados não sustentam nenhum k ótimo — cotovelo sem
  inflexão clara, silhueta baixa em todo o intervalo. Uma segmentação
  alternativa (K-Means, k=4, Matheus Candido — `4.0-mc-kmeans-clusterizacao-municipios.ipynb`)
  chegou a uma leitura de negócio útil (municípios de IDHM médio superando
  municípios de IDHM alto em taxa de alfabetização), mas com a mesma
  ressalva: separação absolutamente fraca (silhueta 0,21). Tratar qualquer
  leitura de cluster como hipótese exploratória, não como tipologia rígida.
- **Atlas fixo em 2010** (Censo Demográfico) — 13-15 anos de defasagem em
  relação aos dados de aluno (2023-2025). Vale como contexto estrutural, não
  medida contemporânea.
- **FUNDEB sem NSE em 2023** (publicado só a partir de 2024).
- **`id_aluno` não é um identificador de pessoa estável entre edições** —
  limita qualquer análise longitudinal no nível do aluno; a EDA recomenda
  explicitamente não usá-lo como grupo de cross-validation nem como
  histórico por pessoa.
- **As duas linhas de validação cruzada (`modelo_alfabetizacao_municipal_MCB`
  e `5.0`) não recebem o mesmo nível de polimento e revisão que a linha
  oficial** — servem para checar direção e magnitude dos achados, não como
  entregável de igual peso.
- **A abordagem de validação cruzada `5.0` performou pior que o `Q1` oficial
  na regressão da taxa** (R² −0,03 vs 0,316) — a poda de colinearidade usada
  nela removeu `taxa_lag1` bruta em favor de um proxy, o que pode ter
  custado sinal; ainda não isolado se a causa é essa ou o efeito do salto de
  2025 afetando esse pipeline mais que o outro.
- **`requirements.txt` e `pyproject.toml` já sincronizados** (corrigido
  nesta fase) — antes disso, `pip install -r requirements.txt` seguido de
  `make data` quebrava por falta de `xlrd`/`statsmodels`.

## Aplicação prática para políticas públicas

- **Antecipação, não só descrição**: o modelo de risco de meta (Q4)
  permite agir **antes** do resultado do ciclo corrente, priorizando os
  municípios com maior `P(não atinge meta)` — não apenas reportar depois.
- **Ranking de priorização, não um corte rígido**: a resposta a Q2 é
  entregue como `probabilidade_risco` ordenada (Top 20/Top 100 municípios
  nomeados), porque o threshold de 0,5 não é uma fronteira natural entre
  "em risco" e "fora de risco" — dá ao gestor a flexibilidade de escolher
  quantos municípios atender conforme o orçamento disponível.
- **Meta pactuada precisa de contexto**: recomendar que o INEP/MEC olhem
  `taxa` e `cumprimento de meta` como duas dimensões separadas na
  comunicação com gestores estaduais/municipais — o exemplo RS vs. AL mostra
  que meta mais ambiciosa produz mais "não-cumprimento" mesmo com desempenho
  absoluto melhor.
- **Cuidado ao comparar municípios pequenos**: qualquer política que ranqueie
  municípios por taxa bruta deve ponderar pelo tamanho da amostra (nº de
  alunos avaliados) — caso contrário super-representa municípios minúsculos
  nos dois extremos do ranking.
- **Investimento em índice socioeconômico, sozinho, tem retorno limitado**:
  já que o histórico municipal domina o sinal preditivo, políticas que só
  mexem no nível de renda/IDHM têm efeito indireto e lento sobre a
  alfabetização — vale complementar com intervenção pedagógica direta.

## Possíveis evoluções futuras

1. Fechar uma resposta para Q3 que o time considere suficientemente
   sustentada — hoje há uma divergência documentada (nenhum k ótimo vs.
   k=4) que nenhum dos dois lados resolveu sozinho.
2. Investigar por que a validação cruzada `5.0` teve desempenho pior que o
   `Q1` oficial — repor `taxa_lag1` bruta fora da poda de colinearidade e
   medir o efeito isoladamente.
3. Investigar a mudança de prevalência do alvo entre 2024 e 2025 com a
   própria fonte (INEP) antes do relatório final — hoje é medida, não
   totalmente explicada.
4. Adicionar uma dimensão de tendência temporal ao ranking de risco da Q2,
   hoje baseado só na taxa do ano corrente.
5. Reavaliar se algum elemento das abordagens de validação cruzada (ex.: o
   classificador dedicado de meta do `5.0`) vale incorporar à linha oficial.
6. Preencher `src/modeling/train.py`/`predict.py` com a versão de modelo
   escolhida, hoje só nos notebooks.
7. Gravar o vídeo executivo e consolidar os `LEIA-ME.md` soltos num único
   documento técnico em `reports/`.

---

## Pipeline de dados (documentação técnica)

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

O projeto usa [`uv`](https://docs.astral.sh/uv/) para gerenciar ambiente e
dependências (`pyproject.toml` + `uv.lock`) — é a forma recomendada de rodar
o projeto; instalar dependências manualmente com `pip` num ambiente à parte
foi a origem de erros de ambiente para quem tentou de outra forma.

```bash
uv sync
uv run make data
```

`uv sync` cria o `.venv` e instala exatamente as versões travadas em
`uv.lock`. `uv run make data` executa o target `data` do `Makefile` dentro
desse ambiente (equivalente a `python -m src.preprocessing.prepare`).

## Atlas do Desenvolvimento Humano

O Atlas roda igual às outras fontes do projeto: sem passo manual, sem conta em
serviço nenhum.

```bash
python -m pip install -r requirements.txt
python -m src.preprocessing.atlas.run
```

### De onde vem o dado

O Atlas não tem API, e o site oficial (`atlasbrasil.org.br`) bloqueia acesso
automatizado. O pipeline consome o **espelho público em CSV** mantido em
[github.com/mauriciocramos/IDHM](https://github.com/mauriciocramos/IDHM) —
réplica fiel do mesmo arquivo do PNUD/IPEA/Fundação João Pinheiro, baixável por
HTTP simples. `download.py` busca `municipal.csv` e grava em
`data/external/atlas_desenvolvimento_humano/municipal_raw.csv`.

São 237 colunas com as siglas originais do Atlas (`IDHM`, `T_ANALF11A14`,
`PMPOB`...) e as três coortes do índice — 1991, 2000 e 2010 —, 5.565 municípios
em cada uma. A Bronze ingere o arquivo inteiro; a Silver seleciona os 35
indicadores do contrato, traduz as siglas e recorta 2010.

> **Por que não a Base dos Dados.** O dataset `mundo_onu.adh` traz as mesmas
> variáveis, mas é distribuído por BigQuery: exige conta Google Cloud
> autenticada e billing project por pessoa. Virava um passo manual por colega —
> e um CSV com o dialeto errado colocado na pasta passava batido pela checagem
> de existência e só quebrava lá na Bronze, com um `ParserError` na linha 5.567
> que não dizia nada sobre a causa. O espelho eliminou os dois problemas.

⚠️ O arquivo é publicado com separador `;` e decimal `,` (`DIALETO_BRONZE` em
`schemas.py`). Lido com o dialeto errado ele **não** falha na primeira linha: as
coortes têm quantidades diferentes de células vazias, então o parser atravessa
1991 inteiro antes de quebrar. Por isso a Bronze confere as colunas logo após a
leitura.

### Como rodar o pipeline completo

```bash
python -m pip install -r requirements.txt

# Todas as fontes + join, de uma vez
python -m src.preprocessing.prepare

# ou, fonte por fonte:
python -m src.preprocessing.inep.run
python -m src.preprocessing.fundeb.run
python -m src.preprocessing.censoescolar.run
python -m src.preprocessing.ibge.run
python -m src.preprocessing.atlas.run
python -m src.preprocessing.join
```

Use `--skip-download` para reaproveitar o que já está em `data/external` e
`data/raw`. O resultado final fica em `data/processed/base_analitica/`
(particionado por ano), pronto para a etapa de modelagem.

### O que o Atlas adiciona à `base_analitica`

35 indicadores municipais (prefixo `ctx_atlas_`), cobrindo IDHM e seus 3
subíndices, analfabetismo por faixa etária, saúde da infância (mortalidade
até 1 e 5 anos), trabalho infantil, frequência escolar por idade,
vulnerabilidade familiar, renda e desigualdade. Ver a lista completa em
`src/preprocessing/atlas/schemas.py` (dicionário `INDICADORES`).

Taxa de match contra `gold/aluno`: **99,96%**. Os 6 municípios sem dado foram
criados depois do Censo 2010 e não existem no Atlas — ausência de origem, não
falha de join: Mojuí dos Campos/PA, Pescaria Brava/SC, Balneário Rincão/SC,
Pinto Bandeira/RS, Paraíso das Águas/MS e Boa Esperança do Norte/MT.

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
