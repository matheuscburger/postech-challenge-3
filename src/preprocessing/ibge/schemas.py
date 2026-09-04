"""Structural contracts for the IBGE Bronze layer (column name + Spark-equivalent type)."""

from __future__ import annotations

from typing import NamedTuple

# Níveis territoriais da API de agregados: N1 Brasil, N2 região, N3 UF, N6 município.
NIVEL_MUNICIPIO = "N6"


class ApiJob(NamedTuple):
    """Um pedido à API de agregados.

    ``variavel`` e os nomes em ``classificacoes`` são NOMES, não ids: os ids são
    resolvidos contra /agregados/{id}/metadados em tempo de execução. Fixar id na mão
    é o acoplamento que quebra em silêncio quando o IBGE republica o agregado.

    ``classificacoes`` é ``((nome_da_classificacao, (nome_da_categoria, ...)), ...)``.
    Um agregado pode ter várias — o 10295 cruza sexo × cor ou raça × grupo de idade —
    e a API aceita todas no mesmo pedido, separadas por ``|``.

    UMA variável por job. Pedir duas na mesma chamada traria duas linhas por
    município na Bronze, e a desduplicação da Silver ficaria com a primeira em
    silêncio. Duas medidas = dois jobs.
    """

    entidade: str
    agregado: int
    periodos: tuple[int, ...]
    nivel: str
    variavel: str
    medida: str
    classificacoes: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def celula_unica(self) -> bool:
        """True quando o pedido devolve um valor por município.

        É o caso sem classificação (população, área) e também o do 10295, onde cada
        classificação pede só ``Total``: ali a classificação existe para CONSTRANGER
        o pedido, não para virar coluna. A Silver usa isso para escolher entre
        ``pivotar`` e ``pivotar_categorias``.
        """
        return all(len(categorias) == 1 for _, categorias in self.classificacoes)


# --------------------------------------------------------------------------------------
# Cobertura temporal da SÉRIE: 2024 e 2025, mesmo recorte do FUNDEB.
#
# O IBGE NÃO publicou estimativa municipal de população para 2023 — naquele ano a
# referência oficial passou a ser a contagem do Censo 2022, encaminhada ao TCU para o
# cálculo do FPM. A série municipal do agregado 6579 salta de 2021 para 2024.
# --------------------------------------------------------------------------------------
ANOS_ESTIMATIVA = (2024, 2025)

# A área territorial é ATRIBUTO ESTRUTURAL do município, não série: só muda quando há
# alteração de limites. Vem do Censo 2022 (único período do agregado 4714) e é replicada
# para todos os anos da janela. Por ser constante, não há coluna de ano de referência —
# o valor é sempre de 2022, e este comentário é o registro disso.
ANO_REFERENCIA_AREA = 2022

ENTIDADE_POPULACAO = "populacao_municipios"
ENTIDADE_AREA = "area_municipios"
ENTIDADE_SITUACAO = "censo_situacao_domicilio"
ENTIDADE_ESGOTO = "censo_esgotamento_sanitario"
ENTIDADE_RENDA_MEDIANA = "censo_renda_domiciliar_mediana"
ENTIDADE_RENDA_MEDIA = "censo_renda_domiciliar_media"

MEDIDA_POPULACAO = "populacao_residente"
MEDIDA_AREA = "area_km2"
MEDIDA_SITUACAO = "populacao_censo"
MEDIDA_ESGOTO = "domicilios_censo"

# Sufixo explicito nas duas: com media e mediana na mesma tabela, uma coluna
# "renda_domiciliar_per_capita" sem qualificador seria adivinhacao para quem le.
MEDIDA_RENDA_MEDIANA = "renda_domiciliar_per_capita_mediana"
MEDIDA_RENDA_MEDIA = "renda_domiciliar_per_capita_media"
MEDIDA_PCT_RURAL = "pct_populacao_rural"
MEDIDA_PCT_ESGOTO = "pct_esgoto_adequado"

# --------------------------------------------------------------------------------------
# Categorias do Censo 2022, pelo NOME publicado no SIDRA.
#
# Os ids numéricos NÃO são fixados aqui de propósito: são resolvidos contra os
# metadados do agregado a cada execução, como já é feito com a variável. Se o IBGE
# renomear uma categoria, o pipeline para e lista as disponíveis — em vez de somar
# a categoria errada em silêncio.
#
# Confira os nomes contra a fonte com:
#     python -m src.preprocessing.ibge.download --inspecionar
# --------------------------------------------------------------------------------------
CLASSIFICACAO_SITUACAO = "Situação do domicílio"
CAT_SITUACAO_TOTAL = "Total"
CAT_SITUACAO_URBANA = "Urbana"
CAT_SITUACAO_RURAL = "Rural"

# Agregado 10295 — Censo 2022, rendimento domiciliar per capita. Confirmado por
# --inspecionar: períodos [2022], níveis N1/N2/N3/**N6**, e três classificações.
# Pedimos "Total" nas três: o recorte por sexo/cor/idade não interessa aqui, e é
# a combinação Total x Total x Total que dá o valor do município inteiro.
#
# Nome COMPLETO, não prefixo. O SIDRA publica média e mediana como variáveis irmãs
# que só diferem em "médio"/"mediano" — sem acento e em minúsculas, "medio" e
# "mediano". Um prefixo curto casaria, mas deixaria o --conferir avisando PREFIXO em
# toda execução, e aviso permanente é aviso ignorado. Com o nome inteiro o casamento
# é exato e a ambiguidade entre as duas some.
_SUFIXO_RENDA = (
    " dos moradores em domicílios particulares permanentes ocupados, exclusive os cuja "
    "condição no domicílio era pensionista, empregado(a) doméstico(a) ou parente do(a) "
    "empregado(a) doméstico(a)"
)
VARIAVEL_RENDA_MEDIANA = (
    "Valor do rendimento nominal mediano mensal domiciliar per capita" + _SUFIXO_RENDA
)
VARIAVEL_RENDA_MEDIA = (
    "Valor do rendimento nominal médio mensal domiciliar per capita" + _SUFIXO_RENDA
)

# As DUAS entram na Gold. Não são deriváveis uma da outra — são medições
# independentes —, então cabem na camada sem ferir a regra.
#
# A MEDIANA descreve o município típico: renda é assimétrica à direita, e em
# município pequeno a média é deslocada por meia dúzia de famílias ricas.
#
# A MÉDIA entra pelo que a razão média/mediana revela: a assimetria da distribuição,
# que é um proxy de desigualdade municipal. Importa porque o Índice de Gini
# municipal NÃO existe — o agregado 10301 só publica até UF.
#
# Como níveis as duas correlacionam altíssimo; o sinal está na razão, que é derivada
# e nasce no features/ (``assimetria_renda = media / mediana``).
CLASSIFICACAO_SEXO = "Sexo"
CLASSIFICACAO_COR_RACA = "Cor ou raça"
CLASSIFICACAO_GRUPO_IDADE = "Grupo de idade"
CAT_TOTAL = "Total"

# As duas rendas pedem o mesmo recorte: Total nas três dimensões.
CLASSIFICACOES_RENDA = (
    (CLASSIFICACAO_SEXO, (CAT_TOTAL,)),
    (CLASSIFICACAO_COR_RACA, (CAT_TOTAL,)),
    (CLASSIFICACAO_GRUPO_IDADE, (CAT_TOTAL,)),
)

CLASSIFICACAO_ESGOTO = "Tipo de esgotamento sanitário"
CAT_ESGOTO_TOTAL = "Total"
# NUMERADOR de pct_esgoto_adequado: a categoria pronta, publicada pelo IBGE. É a
# definição da própria fonte, e evita o risco de dupla contagem ao somar parcelas.
CAT_ESGOTO_ADEQUADO = "Rede geral, rede pluvial ou fossa ligada à rede"
# As duas parcelas dessa categoria. NÃO entram na conta: são pedidas só para conferir
# que a categoria-pai é mesmo a soma delas — é o que prova que resolvemos o nome certo.
CAT_ESGOTO_REDE = "Rede geral ou pluvial"
CAT_ESGOTO_FOSSA_LIGADA = "Fossa séptica ou fossa filtro ligada à rede"
CAT_ESGOTO_SEM_BANHEIRO = "Não tinham banheiro nem sanitário"

API_JOBS = (
    ApiJob(
        ENTIDADE_POPULACAO,
        6579,  # Estimativas de População
        ANOS_ESTIMATIVA,
        NIVEL_MUNICIPIO,
        "População residente estimada",
        MEDIDA_POPULACAO,
    ),
    ApiJob(
        ENTIDADE_AREA,
        4714,  # Censo Demográfico 2022 — população, área territorial e densidade
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        "Área da unidade territorial",
        MEDIDA_AREA,
    ),
    ApiJob(
        ENTIDADE_SITUACAO,
        9923,  # Censo 2022 — População residente, por situação do domicílio
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        "População residente",
        MEDIDA_SITUACAO,
        ((CLASSIFICACAO_SITUACAO, (CAT_SITUACAO_TOTAL, CAT_SITUACAO_URBANA, CAT_SITUACAO_RURAL)),),
    ),
    ApiJob(
        ENTIDADE_ESGOTO,
        6805,  # Censo 2022 — Domicílios particulares permanentes ocupados, por esgoto
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        "Domicílios particulares permanentes ocupados",
        MEDIDA_ESGOTO,
        (
            (
                CLASSIFICACAO_ESGOTO,
                (
                    CAT_ESGOTO_TOTAL,
                    CAT_ESGOTO_ADEQUADO,
                    CAT_ESGOTO_REDE,
                    CAT_ESGOTO_FOSSA_LIGADA,
                    CAT_ESGOTO_SEM_BANHEIRO,
                ),
            ),
        ),
    ),
    ApiJob(
        ENTIDADE_RENDA_MEDIANA,
        10295,  # Censo 2022 — rendimento domiciliar per capita, médio e mediano
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        VARIAVEL_RENDA_MEDIANA,
        MEDIDA_RENDA_MEDIANA,
        CLASSIFICACOES_RENDA,
    ),
    # Mesmo agregado, outra variável: dois jobs porque pedir as duas variáveis na
    # mesma chamada traria duas linhas por município na Bronze, e a desduplicação
    # da Silver ficaria com a primeira em silêncio.
    ApiJob(
        ENTIDADE_RENDA_MEDIA,
        10295,
        (ANO_REFERENCIA_AREA,),
        NIVEL_MUNICIPIO,
        VARIAVEL_RENDA_MEDIA,
        MEDIDA_RENDA_MEDIA,
        CLASSIFICACOES_RENDA,
    ),
)

JOBS_POR_ENTIDADE = {job.entidade: job for job in API_JOBS}

# --------------------------------------------------------------------------------------
# Anos SEM estimativa publicada. A tabela cobre a mesma janela do INEP (2023-2025), mas
# 2023 entra com ``populacao_residente`` NULA, de propósito.
#
# A alternativa seria repetir a contagem do Censo 2022 como se fosse 2023. Isso não é
# replicar um atributo estável — é inventar um ponto de uma série anual que o IBGE
# deliberadamente não publicou, e o modelo leria o número como medição. Nulo é a
# afirmação honesta: "não existe estimativa para este ano". O ``features/`` marca a
# ausência com a flag ``tem_ibge`` em vez de escondê-la.
#
# A área continua replicada para 2023: é atributo estrutural, não série — só muda com
# alteração de limites territoriais. Preencher a área de 2023 com o valor do Censo 2022
# é dar o valor certo; preencher a população seria dar um valor errado.
# --------------------------------------------------------------------------------------
ANOS_SEM_ESTIMATIVA = (2023,)

# Anos da tabela de saída: a série mais os anos sem estimativa.
ANOS_IBGE = tuple(sorted({*ANOS_SEM_ESTIMATIVA, *ANOS_ESTIMATIVA}))

# Contrato da tabela LONGA normalizada a partir da resposta da API.
# A API devolve uma linha por (variável x localidade x período); a Bronze preserva
# esse formato e o pivot para largo acontece só na Silver.
# As colunas de classificação vêm nulas nos agregados sem classificação (população,
# área) — a Bronze sempre as emite, para o contrato ser um só.
SCHEMA_SERIE_LONGA = [
    ("NU_ANO", "int"),
    ("CO_LOCALIDADE", "string"),
    ("NO_LOCALIDADE", "string"),
    ("CO_NIVEL", "string"),
    ("CO_VARIAVEL", "string"),
    ("NO_VARIAVEL", "string"),
    ("NO_UNIDADE", "string"),
    ("CO_CLASSIFICACAO", "string"),
    ("NO_CLASSIFICACAO", "string"),
    ("CO_CATEGORIA", "string"),
    ("NO_CATEGORIA", "string"),
    ("VL_MEDIDA", "double"),
]

# Valores especiais do SIDRA que chegam como texto e precisam virar nulo.
# "-" zero, "..." não aplicável, "X" sob sigilo, ".." não disponível.
# Um município criado depois da coleta aparece com "..." — é o caso de
# Boa Esperança do Norte (MT), sem estimativa em 2024 e sem área no Censo 2022.
SENTINELAS_SIDRA = ("-", "...", "..", "X", "")

# "-" é ZERO, não ausência — e a diferença não é cosmética. Num município onde nenhum
# domicílio tem esgoto adequado, o SIDRA escreve "-": a medição existe e vale 0.
# Tratá-lo como nulo apaga justamente os municípios de pior saneamento, o que enviesa
# a coluna inteira: sobrariam só os que têm alguma cobertura.
SENTINELA_ZERO = "-"

# Estes sim são ausência de medição, cada um por um motivo:
# "..." não disponível, ".." não aplicável, "X" sob sigilo.
SENTINELAS_AUSENTE = ("...", "..", "X", "")

# Silver: nomes semânticos. A medida (VL_MEDIDA) é renomeada por entidade.
COLUMN_MAP_BASE = {
    "NU_ANO": "ano",
    "CO_LOCALIDADE": "id_municipio",
    "NO_LOCALIDADE": "nome_localidade",
}

# Contagens brutas do Censo que alimentam as razões. Ficam na SILVER, não na Gold:
# a Silver é camada de conformidade e guardar as pontas permite auditar a conta; a
# Gold é a camada de medição, onde ter as pontas E a razão seria redundância.
CONTAGENS_CENSO = [
    "pop_urbana_censo",
    "pop_rural_censo",
    "dom_total_censo",
    "dom_esgoto_adequado_censo",  # numerador (categoria publicada)
    "dom_rede_geral_censo",  # parcela — conferência
    "dom_fossa_ligada_censo",  # parcela — conferência
    "dom_sem_banheiro_censo",
]

# Tudo que é atributo do município e não série anual: vem do Censo 2022 e é replicado
# na janela, com a mesma justificativa da área (não muda, ou muda devagar).
COLS_ESTRUTURAIS = [
    MEDIDA_AREA,
    *CONTAGENS_CENSO,
    MEDIDA_PCT_RURAL,
    MEDIDA_PCT_ESGOTO,
    MEDIDA_RENDA_MEDIANA,
    MEDIDA_RENDA_MEDIA,
]

SILVER_COLS = [
    "ano",
    "id_municipio",
    "nome_municipio",
    "id_uf",
    "sigla_uf",
    "populacao_residente",
    *COLS_ESTRUTURAIS,
]


def normalizar_nome(texto: str) -> str:
    """Casefold sem acento e com espaços colapsados.

    É a regra de comparação dos nomes declarados acima contra os que a API devolve:
    acento, hífen e espaço duplo variam entre publicações do IBGE, e uma diferença
    cosmética não pode virar falha de pipeline nem categoria trocada.
    """
    import unicodedata

    semacento = unicodedata.normalize("NFKD", texto)
    semacento = "".join(c for c in semacento if not unicodedata.combining(c))
    return " ".join(semacento.split()).casefold()

# A Gold guarda só medições independentes. ``porte_municipio`` (faixas de
# população) e ``variacao_populacional_pct`` (delta da população) saíram por
# serem calculáveis a partir de ``populacao_residente``, que continua aqui.
# Reaparecem na Gold analítica, junto com a densidade.
# ``pct_populacao_rural`` e ``pct_esgoto_adequado`` são razões de contagens do Censo.
# As contagens ficam na Silver, não aqui: guardar as duas pontas tornaria a razão
# derivável, e a regra desta camada é uma medição por coluna. A razão é a medição.
GOLD_COLS = [
    "ano",
    "id_municipio",
    "nome_municipio",
    "id_uf",
    "sigla_uf",
    "populacao_residente",
    "area_km2",
    MEDIDA_PCT_RURAL,
    MEDIDA_PCT_ESGOTO,
    MEDIDA_RENDA_MEDIANA,
    MEDIDA_RENDA_MEDIA,
]

# Faixas de porte populacional. Não são coluna desta camada — ficam registradas
# aqui para a Gold analítica. Cardinalidade baixa de propósito: entra no
# OneHotEncoder de src/preprocessing/pipeline.py sem explodir a matriz.
FAIXAS_PORTE = (
    (0, 5_000, "Até 5 mil"),
    (5_000, 10_000, "5 a 10 mil"),
    (10_000, 20_000, "10 a 20 mil"),
    (20_000, 50_000, "20 a 50 mil"),
    (50_000, 100_000, "50 a 100 mil"),
    (100_000, 500_000, "100 a 500 mil"),
    (500_000, None, "Mais de 500 mil"),
)

# Piso de municípios por ano usado nos checks. O Brasil tem 5.570 municípios; a série de
# estimativas já traz 5.571 (Boa Esperança do Norte/MT, criado depois do Censo 2022).
# O piso fica abaixo disso para tolerar criação/extinção sem falso positivo.
MIN_MUNICIPIOS_POR_ANO = 5_500
