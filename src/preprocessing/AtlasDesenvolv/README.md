# Tech Challenge — Fase 3
## Predição e Inteligência Analítica para Alfabetização no Brasil

> 🚧 Projeto em construção. Este README será completado conforme as etapas
> avançam (contexto, objetivo, base, modelagem, métricas, insights,
> limitações, aplicação prática e evoluções futuras — conforme exigido pelo
> enunciado do desafio).

## Status atual

- [x] Estrutura do repositório
- [x] Base simulada para desenvolvimento (`data/gold_alfabetizacao_simulado.csv`)
- [x] Camada bronze — dados reais do Atlas do Desenvolvimento Humano (`data/bronze/atlas_desenvolvimento_humano/`)
- [x] Camada silver — tratamento do Atlas do Desenvolvimento Humano (`data/silver/atlas_desenvolvimento_humano.csv`)
- [x] Análise Exploratória de Dados (`notebooks/01_analise_exploratoria.ipynb`)
- [x] Schema real da Fase 2 mapeado (repositório [postech-challenge-2](https://github.com/diego-nasc/postech-challenge-2)) — tabela `aluno_contexto`
- [x] Script + instruções para baixar os dados brutos oficiais do INEP (`data/raw/README.md`)
- [ ] Base real da Fase 2 (`aluno_contexto`) — aguardando você rodar o download local e enviar o resultado
- [ ] Camada silver (limpeza/padronização + integração Atlas x base Fase 2)
- [ ] Pipeline de pré-processamento (Scikit-learn)
- [ ] Treinamento e validação do modelo
- [ ] Interpretabilidade (Feature Importance / SHAP)
- [ ] Respostas às perguntas de negócio
- [ ] README final
- [ ] Vídeo executivo

## Arquitetura de dados (medalhão)

```
data/
├── raw/        # Dado oficial do INEP, sem nenhuma transformação (baixar localmente — ver data/raw/README.md)
├── bronze/     # Dado bruto de fontes externas, fiel à fonte original (ex: Atlas do Desenvolvimento Humano)
├── silver/     # (próxima etapa) dado limpo, tipado e padronizado
└── gold_alfabetizacao_simulado.csv     # Base analítica pronta para modelagem (simulada por ora)
```

Veja `data/raw/README.md` (como baixar os dados oficiais do INEP) e
`data/bronze/README.md` (proveniência do Atlas do Desenvolvimento Humano).

## Schema real de referência (`aluno_contexto`, Fase 2)

Mapeado a partir do repositório oficial da Fase 2. **A base simulada
atual ainda não usa esses nomes** — isso é o próximo ajuste planejado,
assim que os dados reais estiverem disponíveis.

| Papel | Colunas |
|---|---|
| Identificador | `id_aluno`, `ano`, `id_municipio`, `id_uf` |
| Atributos do aluno | `rede`, `caderno` |
| Contexto municipal | `ctx_taxa_municipio`, `ctx_media_municipio`, `ctx_meta_municipio`, `ctx_distancia_meta_municipio`, `ctx_atingiu_meta_municipio`, `ctx_participacao_municipio`, `ctx_categoria_municipio`, `ctx_faixa_participacao_municipio` |
| ⚠️ Vazamento — nunca usar como feature | `proficiencia`, `gap_proficiencia` |
| Alvo | `label_alfabetizado` |

## ⚠️ Sobre a base de dados

Os dados em `data/gold_alfabetizacao_simulado.csv` são **simulados**,
gerados por `src/preprocessing/gerar_dados_simulados.py`, e servem apenas
para viabilizar o desenvolvimento da EDA e da pipeline antes da base real
da camada Gold (Fase 2) estar disponível. **Assim que a base real existir,
substitua o arquivo em `data/` e ajuste os nomes de coluna, se necessário**
— o restante do código não deve precisar de grandes mudanças.

## Estrutura do repositório

```
tech-challenge-fase3/
├── data/
│   ├── bronze/                # Dados brutos (ex: Atlas do Desenvolvimento Humano)
│   └── gold_*.csv             # Base analítica (simulada por ora)
├── notebooks/                 # Notebooks de análise
├── src/
│   ├── preprocessing/         # Ingestão, geração/tratamento de dados
│   ├── modeling/               # Pipeline de ML
│   ├── evaluation/              # Métricas e validação
│   └── visualization/           # Funções de visualização reutilizáveis
├── reports/                   # Relatórios em markdown
├── images/                    # Gráficos exportados
├── requirements.txt
└── .gitignore
```

## Como rodar

```bash
pip install -r requirements.txt
jupyter notebook notebooks/01_analise_exploratoria.ipynb
```

## Próximos passos

Ver seção "Status atual" acima e o relatório detalhado em
`reports/01_eda_resumo.md`.
