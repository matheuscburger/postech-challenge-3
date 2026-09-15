# Tech Challenge — Fase 3
## Análise didática do desafio e da solução implementada

## 1. O que o desafio pede

O desafio propõe usar a camada Gold produzida na Fase 2 para gerar **inteligência analítica aplicada à alfabetização no Brasil**. O objetivo descrito no enunciado é prever alfabetização com variáveis educacionais, territoriais e socioeconômicas, além de responder perguntas de negócio para apoiar gestores públicos.

O documento exige, em especial:

- análise exploratória para compreender distribuições, padrões, correlações e fatores associados;
- uma pipeline de Machine Learning com tratamento de ausentes, transformação de variáveis, *encoding*, prevenção de *data leakage*, treinamento e validação;
- interpretação dos modelos, preferencialmente com Feature Importance e SHAP;
- respostas para fatores associados à alfabetização, municípios em risco, padrões regionais e risco de não atingir metas;
- repositório organizado, notebooks ou scripts, pipeline reproduzível, README, documentação, visualizações e vídeo executivo.

---

## 2. Decisão metodológica: a unidade de análise é município-ano

O enunciado formula o problema conceitualmente em torno da alfabetização do aluno. Entretanto, a base disponível para a etapa de modelagem não oferece atributos individuais que permitam sustentar uma previsão aluno a aluno. Os atributos explicativos disponíveis são predominantemente contextuais: educacionais, socioeconômicos, territoriais e administrativos.

Por esse motivo, a unidade estatística adotada é **município-ano**: cada linha representa um município em um ano de referência.

> As inferências do projeto são municipais, nunca individuais.

Tratar um município como se fosse um aluno, ou replicar indicadores municipais para fabricar uma base individual, introduziria **um erro de granularidade dos dados**, ou seja, uma associação observada entre municípios não pode ser interpretada automaticamente como uma relação válida para cada aluno. Assim, o projeto preserva o objetivo conceitual de identificar risco relacionado à alfabetização, mas o traduz para a escala em que os dados permitem inferência válida e ação pública viável.

Na prática, essa escolha permite responder: “quais municípios demandam maior atenção?” e “quais municípios podem não cumprir suas metas?”, sem alegar classificar alunos individualmente.

---

## 3. Como a pasta `src` constrói a base analítica

A pasta `src` contém a infraestrutura local de engenharia de dados que substitui a execução anterior na AWS. A organização segue a lógica de camadas Bronze, Silver e Gold.

### 3.1 Fontes e processamento

| Componente | Papel no projeto |
|---|---|
| `src/preprocessing/inep/` | Processa a fonte associada ao Indicador Criança Alfabetizada e às tabelas de aluno, município e UF (2023, 2024 e 2025). |
| `src/preprocessing/censoescolar/` | Processa informações do Censo Escolar/ATU para enriquecer o contexto educacional municipal (2023, 2024 e 2025). |
| `src/preprocessing/fundeb/` | Processa o NSE do FUNDEB, acrescentando contexto socioeconômico/administrativo (2024 e 2025). |
| `src/preprocessing/ibge/` | Processa indicadores territoriais e demográficos (Censo 2022), e populacionais municipais (2024 e 2025). |
| `src/preprocessing/atlas/` | Processa indicadores municipais do Atlas do Desenvolvimento Humano (2010). |
| `src/preprocessing/*/{download,bronze,silver,gold,quality}.py` | Implementa download, contratos estruturais, transformação por camada e verificações de qualidade para cada fonte. |

O comando de preparação em `src/preprocessing/prepare.py` executa as pipelines de INEP, FUNDEB, Censo Escolar e IBGE e, em seguida, chama a etapa de integração.

### 3.2 Integração da Gold

`src/preprocessing/join.py` parte de `aluno` e gera `base_analitica`. Os *left joins* preservam uma linha por aluno durante a integração e trazem variáveis de contexto municipal e estadual de ATU, Atlas, FUNDEB, IBGE e INEP.

As novas variáveis de contexto são prefixadas com `ctx_`. Esse padrão é importante porque `src/features/roles.py` usa os prefixos efetivamente presentes no dataframe para separar contexto, alvos, identificadores e metadados, evitando listas estáticas de colunas que possam ficar desatualizadas.

### 3.3 Prevenção de vazamento

A prevenção de *data leakage* aparece em mais de uma etapa:

1. `src/preprocessing/inep/roles.py` declara os alvos `label_alfabetizado` e `label_proficiencia` como alternativas. Como a classificação é derivada da proficiência usando o corte `743`, um alvo não pode entrar como feature do outro.
2. Indicadores INEP que refletem o resultado da avaliação entram defasados em um ano (`lag1`), enquanto informações disponíveis antes da prova podem entrar no ano corrente.
3. `src/preprocessing/pipeline.py` implementa `build_preprocessor`, com imputação por mediana e padronização para variáveis numéricas, e imputação pela moda com One-Hot Encoding para categóricas. O próprio código orienta que o ajuste seja feito apenas no treino ou dentro da `Pipeline` do scikit-learn.

Essas decisões evitam que o modelo tenha acesso, durante o treinamento, a informações que só seriam conhecidas após o resultado que se pretende antecipar.

---

## 4. Da base individual à base municipal de modelagem

O notebook `Preparacao_para_modelagem_GOLD_analítica.ipynb` faz a ponte entre a Gold analítica e os modelos de negócio.

Ele consolida a base em **município-ano**, preserva os recortes temporais e adiciona `nome_municipio` para tornar rankings e resultados interpretáveis por gestores. A saída registrada tem:

- **11.073 linhas e 50 colunas**;
- **5.517 municípios em 2024**, usados para desenvolvimento;
- **5.556 municípios em 2025**, reservados para teste temporal final.

A imputação não é feita antecipadamente nessa preparação. Ela é ajustada dentro das pipelines e dos *folds* de validação, reduzindo vazamento entre desenvolvimento e teste.

---

## 5. EDA e perguntas analíticas

`EDA_DMN.ipynb` estabelece a base empírica para a modelagem. A EDA examina qualidade, valores ausentes, duplicidades, comportamento dos alvos, diferenças entre anos, correlações, redundância entre features e riscos de vazamento.

A análise detalhada de 2024 trabalha inicialmente com a Gold analítica individual, que registra **1.851.828 linhas e 84 colunas** antes da agregação municipal. A etapa seguinte transforma os achados da EDA em regras de preparação e modelagem municipal.

A distinção é importante: a EDA não é apenas descritiva. Ela justifica a seleção de variáveis, a defasagem temporal, a exclusão de variáveis que revelam o resultado corrente e a escolha de 2024/2025 como divisão temporal.

---

## 6. Resposta integrada às perguntas de negócio

Os notebooks Q1–Q4 respondem a dimensões complementares do desafio.

| Pergunta de negócio | Abordagem | Resposta e uso prático |
|---|---|---|
| Quais fatores ajudam a explicar ou prever a alfabetização futura? | Q1: regressão da taxa municipal de alfabetização. | Identifica variáveis com maior poder preditivo por Permutation Importance e SHAP. Os achados orientam monitoramento de dimensões educacionais e contextuais; não estabelecem causalidade. |
| Quais municípios apresentam maior risco educacional? | Q2: classificação de `risco_educacional`, com classe positiva quando `taxa_realizada < 50`. | Produz um escore para ordenar municípios por prioridade de acompanhamento. |
| Quais regiões possuem padrões semelhantes? | Q3: K-Means, testando de 2 a 8 clusters. | Não encontrou uma estrutura de agrupamentos robusta. O projeto evita forçar uma segmentação sem validade interna suficiente. |
| Como antecipar municípios que podem não atingir metas futuras? | Q4: classificação de `risco_nao_atingir_meta`, com classe positiva quando `taxa_realizada < meta`. | Sinaliza municípios com maior risco de ficar abaixo da meta e apoia ações preventivas. |

Q1 prevê um resultado contínuo; Q2 mede vulnerabilidade absoluta; Q3 avalia se existem perfis naturais de municípios; Q4 avalia risco relativo à meta pactuada. Juntas, essas análises convertem dados públicos em priorização territorial.

---

## 7. Modelos, validação e resultados

### 7.1 Estratégia temporal comum

Nos notebooks supervisionados, **2024** é utilizado para desenvolvimento, comparação de modelos, validação cruzada e decisões de modelagem. **2025** é mantido para teste temporal final. Essa separação é mais próxima do uso real: prever um período futuro usando informações disponíveis anteriormente.

### 7.2 Q1 — regressão da taxa municipal de alfabetização

`Q1_ML_Regressao_DMN.ipynb` compara baselines, modelos lineares, Ridge e Random Forest. A Random Forest é interpretada com Permutation Importance e SHAP global.

No teste temporal de 2025, o desempenho registrado foi:

| Métrica | Resultado |
|---|---:|
| MAE | 10,375 |
| RMSE | 13,075 |
| $R^2$ | 0,311 |

Na importância por permutação, as variáveis mais relevantes na execução registrada incluem `proficiencia_lag1`, `ctx_inep_uf_percentual_participacao_lag1`, `ctx_inep_uf_media_portugues_lag1`, `taxa_lag1` e `participacao_lag1`. Isso deve ser interpretado como **importância preditiva municipal**, não como evidência causal.

### 7.3 Q2 — classificação do risco educacional municipal

Q2 define risco educacional como `taxa_realizada < 50`. A Regressão Logística balanceada foi avaliada com validação OOF em 2024 e teste temporal em 2025.

| Período | Recall | Precisão | F1 | PR-AUC | ROC-AUC | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Validação OOF — 2024 | 0,775 | 0,608 | 0,681 | 0,739 | 0,882 | 0,813 |
| Teste temporal — 2025 | 0,843 | 0,239 | 0,372 | 0,409 | 0,867 | 0,746 |

Em 2025, a classe positiva representou 8,9% dos municípios, contra 25,8% em 2024. Por isso, embora o modelo mantenha recall alto e ROC-AUC elevado, a precisão cai: muitos alertas não correspondem ao risco observado no período posterior.

A decisão metodológica registrada no notebook é usar `probabilidade_risco` como **score de priorização**, e não usar a classe resultante do limiar padrão de 0,50 como uma decisão definitiva. Quanto maior o score, maior a prioridade de análise e possível apoio público.

### 7.4 Q3 — padrões entre municípios

Q3 aplica K-Means com imputação por mediana e padronização. São examinados *inertia*, *silhouette score*, tamanho dos grupos e percentuais de silhueta negativa para $K = 2$ até $8$.

A conclusão é negativa, mas válida: não houve evidência suficiente de clusters coesos e claramente separados. Portanto, não é metodologicamente adequado afirmar que existam grupos naturais de regiões semelhantes com base nesta configuração de K-Means. Essa decisão evita uma interpretação excessiva dos dados.

### 7.5 Q4 — risco de não atingir a meta

Q4 define `risco_nao_atingir_meta = 1` quando `taxa_realizada < meta`. Diferentemente de Q2, a variável `meta` pode ser usada como preditora porque é conhecida antes do resultado. Também é considerada `esforco_pactuado = meta - taxa_lag1`.

| Período | PR-AUC | ROC-AUC | Recall | Precisão | F1 | Balanced Accuracy | Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Desenvolvimento OOF — 2024 | 0,673 | 0,738 | 0,844 | 0,576 | 0,685 | 0,661 | 0,645 |
| Teste temporal — 2025 | 0,555 | 0,737 | 0,805 | 0,375 | 0,512 | 0,648 | 0,578 |

A Regressão Logística é usada com limiar operacional de 0,400. No teste temporal de 2025, foram sinalizados 3.216 municípios (59,0% da amostra), com 1.207 verdadeiros positivos e 293 falsos negativos. O alto recall favorece uma estratégia preventiva.


### 7.6 Q5 — quais variáveis possuem maior influência nos modelos?

A resposta deve ser interpretada na escala **município-ano** e como **influência preditiva**, não como causalidade. Para Q1, o notebook combina Permutation Importance e SHAP global: a primeira mede quanto o erro aumenta quando uma variável é embaralhada; o segundo resume a magnitude média da contribuição da variável para as previsões. A convergência entre os dois métodos é a evidência mais apropriada para destacar variáveis relevantes.

Na execução registrada de Q1, a Permutation Importance aponta a seguinte ordem de maior relevância para prever a taxa municipal de alfabetização:

| Posição | Variável | Interpretação no projeto | Aumento do MAE ao embaralhar |
|---:|---|---|---:|
| 1 | `proficiencia_lag1` | Proficiência municipal observada no período anterior. | 1,061 |
| 2 | `ctx_inep_uf_percentual_participacao_lag1` | Percentual de participação da UF no período anterior. | 0,456 |
| 3 | `ctx_inep_uf_media_portugues_lag1` | Média estadual de Língua Portuguesa no período anterior. | 0,415 |
| 4 | `taxa_lag1` | Taxa municipal de alfabetização no período anterior. | 0,407 |
| 5 | `participacao_lag1` | Participação municipal na avaliação no período anterior. | 0,191 |

Em menor magnitude, mas ainda presentes no ranking, aparecem variáveis contextuais como densidade domiciliar, renda domiciliar per capita, longevidade, trabalho infantil, frequência escolar de crianças de 4 a 5 anos, área territorial, analfabetismo de pessoas com 15 anos ou mais, expectativa de anos de estudo e NSE da UF.

A principal conclusão é que os **indicadores educacionais históricos** — proficiência, taxa de alfabetização e participação anteriores — concentram o maior poder preditivo. Os indicadores socioeconômicos e territoriais complementam a explicação, mas tiveram contribuição menor na execução observada.

Essa conclusão não autoriza afirmar que elevar isoladamente qualquer uma dessas variáveis causará melhora na alfabetização. Por exemplo, `proficiencia_lag1` e `taxa_lag1` são fortes porque carregam persistência temporal do desempenho municipal; elas são especialmente úteis para antecipação e priorização. Já os indicadores de contexto ajudam a caracterizar condições associadas ao risco e podem orientar investigação e planejamento de políticas públicas.

Em Q2, a Regressão Logística balanceada fornece coeficientes padronizados. Um coeficiente positivo está associado a **maior risco estimado**; um coeficiente negativo, a **menor risco estimado**, mantendo-se as demais variáveis constantes no modelo. Os coeficientes de maior magnitude observados foram:

| Variável | Coeficiente | Associação no modelo |
|---|---:|---|
| `ctx_inep_uf_media_portugues_lag1` | -1,232 | Menor risco estimado |
| `proficiencia_lag1` | -0,776 | Menor risco estimado |
| `ctx_atlas_taxa_analfabetismo_11a14` | 0,528 | Maior risco estimado |
| `participacao_lag1` | -0,371 | Menor risco estimado |
| `ctx_atlas_taxa_fora_escola_4a5` | 0,256 | Maior risco estimado |
| `ctx_inep_uf_percentual_participacao_lag1` | -0,193 | Menor risco estimado |

Assim, melhor desempenho e participação históricos aparecem associados a menor risco municipal estimado, enquanto o analfabetismo entre 11 e 14 anos e a proporção de crianças de 4 a 5 anos fora da escola aparecem associados a maior risco. Essas associações devem ser lidas no nível municipal e não constituem relações causais.

Em Q4, a variável mais influente é `meta`, o que é coerente com a definição do problema: metas mais exigentes aumentam, mantidas as demais condições, o risco estimado de não atingi-las. Os principais coeficientes observados foram:

| Variável | Coeficiente | Associação no modelo |
|---|---:|---|
| `meta` | 1,406 | Maior risco estimado |
| `ctx_inep_uf_media_portugues_lag1` | -0,838 | Menor risco estimado |
| `proficiencia_lag1` | -0,648 | Menor risco estimado |
| `ctx_atu_fundamental_anos_iniciais` | 0,436 | Maior risco estimado |
| `ctx_atlas_taxa_analfabetismo_11a14` | 0,355 | Maior risco estimado |
| `ctx_inep_uf_percentual_participacao_lag1` | -0,253 | Menor risco estimado |
| `participacao_lag1` | -0,234 | Menor risco estimado |

Também se destacam, com associação positiva ao risco estimado, densidade domiciliar e percentual de crianças de 4 a 5 anos fora da escola. As variáveis históricas de proficiência e participação voltam a aparecer como fatores protetivos no sentido preditivo.

Os rankings de Q2 e Q4 são interpretações dos respectivos modelos de classificação. Eles devem ser usados para compreender o escore municipal de risco e apoiar priorização, sem transformar a importância estatística em afirmação causal ou individual.

De forma geral, os modelos indicam que as variáveis de maior influência são os indicadores educacionais históricos, especialmente a proficiência anterior, a média de Língua Portuguesa da UF, a taxa de alfabetização do período anterior e os percentuais de participação municipal e estadual, que aparecem de forma recorrente entre os principais preditores de Q1, Q2 e Q4. Nos modelos de risco, também ganham relevância variáveis contextuais de vulnerabilidade, como a taxa de analfabetismo entre 11 e 14 anos e a proporção de crianças de 4 a 5 anos fora da escola, enquanto, em Q4, a meta municipal é a variável isolada de maior influência, pois metas mais exigentes elevam o risco estimado de não cumprimento. Assim, a evidência conjunta mostra que o desempenho educacional passado e a participação nas avaliações concentram o maior poder preditivo, enquanto fatores socioeconômicos, territoriais e de vulnerabilidade complementam a explicação do risco. Esses resultados devem ser interpretados como influência preditiva no nível município-ano, e não como relações causais.

---

## 8. Pipeline reproduzível em notebooks

A entrega reproduzível será organizada em notebooks Jupyter, formato aceito pelo enunciado (“Notebooks ou scripts”). A sequência analítica é:

1. `EDA_DMN.ipynb` — entendimento da Gold, qualidade, hipóteses e decisões de modelagem;
2. `Preparacao_para_modelagem_GOLD_analítica.ipynb` — geração da base município-ano;
3. `Q1_ML_Regressao_DMN.ipynb` — previsão da taxa municipal;
4. `Q2_ML_Classificacao_DMN.ipynb` — risco educacional municipal;
5. `Q3_ML_Kmeans_DMN.ipynb` — avaliação de padrões entre municípios;
6. `Q4_ML_Classificacao_DMN.ipynb` — risco de não atingir a meta.

Os outros arquivos presentes nas pastas representam outras tentativas de resolver o problema do desafio e são mantido como legado.

Os scripts em `src` reproduzem a obtenção e o enriquecimento da Gold localmente. Os notebooks reproduzem a preparação municipal, o treinamento, a validação temporal, as métricas e a interpretação dos modelos.

---

## 9. Github


---

## 10. Conclusão

A solução possui duas camadas complementares. A primeira, implementada em `src`, reconstrói e integra dados públicos em uma Gold analítica com controles de qualidade e regras explícitas contra vazamento. A segunda, implementada nos notebooks, converte essa base para município-ano, executa EDA, constrói modelos supervisionados, avalia a generalização temporal e produz interpretações voltadas à decisão pública.

A resposta final ao desafio é, portanto, territorial: o projeto não classifica alunos individualmente, mas estima e prioriza riscos municipais de alfabetização e de não cumprimento de metas. Essa é a inferência compatível com os dados disponíveis e a escala adequada para apoiar a formulação de políticas educacionais.

---

## Referências internas

- **Enunciado:** `[IAST] - Tech Challenge - Fase 3.pdf`, especialmente páginas 2–8.
- **Engenharia de dados:** pasta `src`.
- **Análise e modelagem:** pasta `Notebooks`.
