"""Papéis das colunas da ``processed/base_analitica``, para montar a matriz de ML.

`inep/roles.py` declara os papéis da ``gold/aluno`` — 9 colunas, os dois alvos e a
regra de vazamento entre eles. Este módulo cobre o que sobra: as **76 colunas de
contexto** que o `join.py` acrescenta, e a separação numérica/categórica que o
`preprocessing.pipeline.build_preprocessor` pede.

Nada aqui enumera as 76 colunas, e isso é o ponto
-------------------------------------------------
O antecessor deste arquivo (``src/preprocessing/roles.py``, apagado em 06/09/2026)
listava as features nome a nome. Apodreceu em silêncio: declarava um alvo só,
colunas de vazamento que não existiam mais e features que a base nunca teve. Nada
o importava, então ninguém notou.

A prevenção não é revisar a lista com mais cuidado — é não ter lista. Aqui a
associação é derivada do **prefixo**, lido das colunas que o dataframe realmente
tem:

    ctx_*      -> feature de contexto
    label_*    -> alvo (o escolhido entra; o outro é vazamento)
    o resto    -> identificador ou metadado, fora da matriz

Uma fonte nova no `join.py` chega com seu prefixo e entra sozinha. Uma coluna
renomeada não deixa um nome órfão para trás. E `papeis()` não pode discordar do
parquet, porque lê o dataframe em vez de uma constante.

O que precisa ser declarado à mão
---------------------------------
Só uma coisa: **as colunas cujo dtype mente**. Medido na base de 06/09/2026, as 76
``ctx_*`` são todas numéricas (74 ``double``, 2 ``int64``) — mas ser ``int`` não
quer dizer que a aritmética signifique alguma coisa. São duas as exceções, e elas
não são o mesmo caso.
"""

from __future__ import annotations

import pandas as pd

from src.preprocessing.inep.roles import (
    ALVO_CLASSIFICACAO,
    ALVO_REGRESSAO,
    PAPEIS_ALUNO,
    VAZAMENTO_POR_ALVO,
)

__all__ = [
    "ALVO_CLASSIFICACAO",
    "ALVO_REGRESSAO",
    "CATEGORICAS_NOMINAIS",
    "CATEGORICAS_ORDINAIS",
    "PREFIXO_CONTEXTO",
    "papeis",
]

PREFIXO_CONTEXTO = "ctx_"
PREFIXO_ALVO = "label_"

# Carimbo da camada Gold. Não é feature nem identificador: é metadado de
# processamento, e entra na matriz como uma constante disfarçada de data.
COL_METADADO = "_gold_processed_at"

# --- as colunas cujo dtype mente -------------------------------------------
#
# NOMINAL: não tem ordem. One-hot é a codificação certa; padronizar é ruído.
CATEGORICAS_NOMINAIS = {
    "dependencia_administrativa": (
        "2 = estadual, 3 = municipal. São dois rótulos de rede, não uma quantidade: "
        "a média entre eles não existe e a distância 2->3 não mede nada."
    ),
}

# ORDINAL: tem ordem, e one-hot a DESTRÓI. Codificar como inteiro preserva a ordem
# mas assume espaçamento uniforme. Nenhuma das duas é obviamente certa — a escolha
# é da modelagem, não deste arquivo; aqui elas só ficam separadas das nominais para
# que a decisão seja tomada de propósito.
CATEGORICAS_ORDINAIS = {
    "ctx_inep_mun_nivel_alfabetizacao_lag1": (
        "níveis 0 a 5 do INEP, defasados. A ordem é real (5 é mais alfabetizado que "
        "1), mas o espaçamento entre níveis não é medido: 0->1 não vale o mesmo que "
        "4->5."
    ),
}

CATEGORICAS = {**CATEGORICAS_NOMINAIS, **CATEGORICAS_ORDINAIS}


def papeis(
    df: pd.DataFrame,
    alvo: str = ALVO_REGRESSAO,
    *,
    ano_como_feature: bool = False,
) -> dict[str, list[str]]:
    """Particiona as colunas de ``df`` nos papéis da matriz de ML.

    ``alvo`` escolhe entre os dois alvos mutuamente excludentes. O outro sai como
    vazamento — ``label_alfabetizado == (label_proficiencia >= 743)`` bate em
    100,0000% das linhas, então usar um como feature do outro dá AUC 1,0.

    ``ano_como_feature`` fica **False** por padrão, seguindo
    ``PAPEIS_ALUNO["identificador"]``. Não é uma decisão fechada: 2023 tem 14 das
    76 colunas de contexto vazias contra 0 em 2024-2025, então o modelo pode
    aprender "tudo faltando = 2023" como proxy de calendário, e incluir ``ano``
    lhe dá o atalho de graça. O contrato da ``base_analitica`` registra as três
    estratégias e o acordo de medir o impacto sobre a validação temporal antes de
    escolher. Ligue de propósito, com a métrica na mão.

    Devolve as listas prontas para ``build_preprocessor(numeric, categorical)``.
    """
    if alvo not in VAZAMENTO_POR_ALVO:
        raise ValueError(
            f"alvo desconhecido: {alvo!r}. Os alvos declarados em inep/roles são "
            f"{sorted(VAZAMENTO_POR_ALVO)}."
        )
    if alvo not in df.columns:
        raise ValueError(f"o alvo {alvo!r} não está no dataframe.")

    fora = {
        alvo,
        COL_METADADO,
        *VAZAMENTO_POR_ALVO[alvo],
        *PAPEIS_ALUNO["identificador"],
    }
    if ano_como_feature:
        fora.discard("ano")

    features = [c for c in df.columns if c not in fora]

    # Guard: uma exceção declarada que sumiu do frame é uma coluna que passou a ser
    # escalada como contínua sem ninguém decidir isso — exatamente o erro que este
    # arquivo existe para impedir. Renomeou? Atualize a constante junto.
    perdidas = sorted(set(CATEGORICAS) - set(df.columns) - fora)
    if perdidas:
        raise AssertionError(
            f"colunas declaradas como categóricas não existem no dataframe: {perdidas}. "
            "Se foram renomeadas no join, atualize CATEGORICAS_NOMINAIS/ORDINAIS; se "
            "saíram de vez, remova-as de lá. Deixar como está faz cada uma voltar "
            "silenciosamente para as numéricas."
        )

    categoricas = [c for c in features if c in CATEGORICAS]
    numericas = [c for c in features if c not in CATEGORICAS]

    return {
        "alvo": [alvo],
        "identificador": [c for c in PAPEIS_ALUNO["identificador"] if c in df.columns],
        "vazamento": [c for c in VAZAMENTO_POR_ALVO[alvo] if c in df.columns],
        "features_numericas": numericas,
        "features_categoricas": categoricas,
        "contexto": [c for c in features if c.startswith(PREFIXO_CONTEXTO)],
    }
