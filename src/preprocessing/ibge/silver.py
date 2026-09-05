"""Silver layer: pivot from long to wide, semantic rename and quality checks for IBGE."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
import pandas as pd

from src.config import BRONZE_DATA_DIR, SILVER_DATA_DIR
from src.preprocessing.ibge.quality import CHECKS_SILVER, checar_qualidade
from src.preprocessing.ibge.schemas import (
    ANO_REFERENCIA_AREA,
    ANOS_IBGE,
    ANOS_SEM_ESTIMATIVA,
    CAT_ESGOTO_ADEQUADO,
    CAT_ESGOTO_FOSSA_LIGADA,
    CAT_ESGOTO_REDE,
    CAT_ESGOTO_SEM_BANHEIRO,
    CAT_ESGOTO_TOTAL,
    CAT_SITUACAO_RURAL,
    CAT_SITUACAO_TOTAL,
    CAT_SITUACAO_URBANA,
    COLS_ESTRUTURAIS,
    COLUMN_MAP_BASE,
    ENTIDADE_AREA,
    ENTIDADE_ESGOTO,
    ENTIDADE_POPULACAO,
    ENTIDADE_RENDA_MEDIA,
    ENTIDADE_RENDA_MEDIANA,
    ENTIDADE_SITUACAO,
    JOBS_POR_ENTIDADE,
    MEDIDA_AREA,
    MEDIDA_PCT_ESGOTO,
    MEDIDA_PCT_RURAL,
    MEDIDA_POPULACAO,
    MEDIDA_RENDA_MEDIA,
    MEDIDA_RENDA_MEDIANA,
    NIVEL_MUNICIPIO,
    SILVER_COLS,
    ApiJob,
    normalizar_nome,
)
from src.preprocessing.io import read_parquet, write_parquet_partitioned

ENTITY = ENTIDADE_POPULACAO

# Rótulos do município que a área carrega para montar as linhas dos anos sem
# estimativa — a série de população não cobre esses anos.
COLS_MUNICIPIO = ["id_municipio", "nome_municipio", "id_uf", "sigla_uf"]


def add_metadata(df: pd.DataFrame, ts) -> pd.DataFrame:
    df = df.copy()
    df["_silver_processed_at"] = ts
    return df


def _separar_nome_uf(nome_localidade: pd.Series) -> tuple[pd.Series, pd.Series]:
    """A API devolve o município como 'Alta Floresta D'Oeste - RO'.

    Devolve (nome_municipio, sigla_uf). A sigla aqui é conferência: a fonte de verdade
    da UF são os dois primeiros dígitos do código IBGE, como já é feito no inep/gold.py.
    """
    texto = nome_localidade.astype("string").str.strip()
    partes = texto.str.rsplit(" - ", n=1, expand=True)
    if partes.shape[1] < 2:
        return texto, pd.Series(pd.NA, index=texto.index, dtype="string")
    nome = partes[0].astype("string").str.strip()
    sigla = partes[1].astype("string").str.strip().str.upper()
    valida = sigla.str.match(r"^[A-Z]{2}$", na=False)
    return nome.mask(~valida, texto), sigla.mask(~valida)


def _preparar(bronze: pd.DataFrame, job: ApiJob) -> pd.DataFrame:
    """Filtra o nível municipal, renomeia e tipa. Não desduplica."""
    mapa = {**COLUMN_MAP_BASE, "VL_MEDIDA": job.medida}
    faltando = [c for c in mapa if c not in bronze.columns]
    if faltando:
        raise AssertionError(f"{job.entidade}: colunas ausentes na Bronze: {faltando}")

    df = bronze.loc[bronze["CO_NIVEL"].astype("string") == NIVEL_MUNICIPIO].copy()
    if df.empty:
        niveis = sorted(bronze["CO_NIVEL"].dropna().unique().tolist())
        raise AssertionError(
            f"{job.entidade}: nenhuma linha no nível {NIVEL_MUNICIPIO}. Níveis presentes: {niveis}"
        )

    df = df.rename(columns=mapa)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip().str.zfill(7)
    df[job.medida] = pd.to_numeric(df[job.medida], errors="coerce")

    nome, sigla = _separar_nome_uf(df["nome_localidade"])
    df["nome_municipio"] = nome
    df["sigla_uf"] = sigla
    df["id_uf"] = pd.to_numeric(df["id_municipio"].str.slice(0, 2), errors="coerce").astype(
        "Int64"
    )

    return df.loc[df["ano"].isin(job.periodos) & df["id_municipio"].notna()].copy()


def pivotar(bronze: pd.DataFrame, job: ApiJob) -> pd.DataFrame:
    """Longo -> largo: uma linha por (ano, município), uma coluna por medida.

    O nome da coluna de valor vem de ``job.medida``, então cada indicador novo do IBGE
    entra como uma coluna aqui sem tocar no resto do pipeline.
    """
    df = _preparar(bronze, job)

    duplicadas = int(df.duplicated(["ano", "id_municipio"]).sum())
    if duplicadas:
        logger.warning(
            "{}: {:,} par(es) (ano, id_municipio) duplicado(s) na Bronze; "
            "mantendo o primeiro registro de cada.",
            job.entidade,
            duplicadas,
        )
        df = df.drop_duplicates(["ano", "id_municipio"], keep="first")

    return df


def pivotar_categorias(bronze: pd.DataFrame, job: ApiJob) -> pd.DataFrame:
    """Longo -> largo por CATEGORIA: uma linha por município, uma coluna por categoria.

    As colunas saem nomeadas pelos nomes declarados no job, não pelos que a API
    devolveu — casados por ``normalizar_nome``. Assim o resto da Silver referencia as
    constantes do schemas, e uma variação de acento ou espaço no texto do IBGE não
    vira KeyError lá na frente.

    Só faz sentido para job de UMA classificação com várias categorias. Cruzamento de
    dimensões chega aqui com rótulo composto e não casaria por nome — esses jobs são
    ``celula_unica`` e vão por ``pivotar``.
    """
    if len(job.classificacoes) != 1:
        raise AssertionError(
            f"{job.entidade}: pivotar_categorias espera exatamente uma classificação, "
            f"o job declara {len(job.classificacoes)}."
        )
    nomes_categorias = job.classificacoes[0][1]

    df = _preparar(bronze, job)
    if "NO_CATEGORIA" not in df.columns:
        raise AssertionError(
            f"{job.entidade}: Bronze sem NO_CATEGORIA. Reprocesse a Bronze — o contrato "
            "de série longa passou a carregar a classificação."
        )

    recebidas = {normalizar_nome(str(c)): str(c) for c in df["NO_CATEGORIA"].dropna().unique()}
    faltando = [c for c in nomes_categorias if normalizar_nome(c) not in recebidas]
    if faltando:
        raise AssertionError(
            f"{job.entidade}: categorias ausentes na resposta: {faltando}. "
            f"Recebidas: {sorted(recebidas.values())}"
        )

    largo = pd.DataFrame({"id_municipio": df["id_municipio"].drop_duplicates()}).set_index(
        "id_municipio"
    )
    for categoria in nomes_categorias:
        fatia = df.loc[df["NO_CATEGORIA"].astype("string") == recebidas[normalizar_nome(categoria)]]
        fatia = fatia.drop_duplicates("id_municipio", keep="first").set_index("id_municipio")
        largo[categoria] = fatia[job.medida]
    return largo.reset_index()


def area_estrutural(bronze_area: pd.DataFrame) -> pd.DataFrame:
    """Reduz a área a um atributo do município, sem ano.

    A área só muda com alteração de limites territoriais, então o valor do Censo
    de {ANO_REFERENCIA_AREA} vale para toda a janela. Devolve uma linha por
    município, com os rótulos (nome, UF) e ``area_km2``.
    """
    job = JOBS_POR_ENTIDADE[ENTIDADE_AREA]
    area = pivotar(bronze_area, job)[[*COLS_MUNICIPIO, MEDIDA_AREA]]
    area = area.drop_duplicates("id_municipio", keep="first")
    logger.info(
        "{}: {:,} municípios com área (referência {}).",
        ENTIDADE_AREA,
        int(area[MEDIDA_AREA].notna().sum()),
        ANO_REFERENCIA_AREA,
    )
    return area


def medida_estrutural(bronze: pd.DataFrame, entidade: str) -> pd.DataFrame:
    """Reduz um job de célula única a ``(id_municipio, medida)``.

    Serve aos dois jobs de renda do agregado 10295, que cruza sexo × cor ou raça ×
    grupo de idade mas pede ``Total`` nas três: a resposta tem uma célula por
    município, então entra por ``pivotar`` como a área, não por
    ``pivotar_categorias``.

    A renda vem em REAIS NOMINAIS de 2022, replicada na janela como os demais
    atributos do Censo: serve para posição relativa entre municípios, não para
    comparação temporal com renda de outro ano.
    """
    job = JOBS_POR_ENTIDADE[entidade]
    if not job.celula_unica:
        raise AssertionError(
            f"{entidade}: o job pede mais de uma categoria por classificação; "
            "a resposta não tem uma célula por município."
        )
    out = pivotar(bronze, job)[["id_municipio", job.medida]]
    out = out.drop_duplicates("id_municipio", keep="first")
    logger.info(
        "{}: {:,} municípios com {} (referência {}).",
        entidade,
        int(out[job.medida].notna().sum()),
        job.medida,
        ANO_REFERENCIA_AREA,
    )
    return out


def _conferir_assimetria_renda(estrutural: pd.DataFrame) -> None:
    """Renda é assimétrica à direita, então média >= mediana quase sempre.

    Não é identidade matemática — é propriedade da distribuição de renda. O valor
    do check é outro: "médio" e "mediano" diferem em duas letras, e se a resolução
    por nome tivesse trocado as duas variáveis, média < mediana apareceria em quase
    todos os municípios. Um punhado de exceções é plausível; a maioria não.
    """
    media = pd.to_numeric(estrutural[MEDIDA_RENDA_MEDIA], errors="coerce")
    mediana = pd.to_numeric(estrutural[MEDIDA_RENDA_MEDIANA], errors="coerce")
    comparavel = media.notna() & mediana.notna()
    n = int(comparavel.sum())
    if not n:
        logger.warning("renda: nada comparável entre média e mediana.")
        return

    invertidos = int((comparavel & (media < mediana)).sum())
    if invertidos / n > 0.10:
        logger.error(
            "renda: média < mediana em {:,} de {:,} municípios ({:.1%}). Renda é "
            "assimétrica à direita — proporção alta sugere média e mediana trocadas "
            "na resolução por nome. Rode --conferir.",
            invertidos,
            n,
            invertidos / n,
        )
    else:
        logger.info(
            "renda: média >= mediana em {:,} de {:,} municípios ({:,} exceções).",
            n - invertidos,
            n,
            invertidos,
        )


def _razao(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """Divisão que devolve nulo — nunca inf — onde o denominador é zero ou ausente."""
    num = pd.to_numeric(numerador, errors="coerce")
    den = pd.to_numeric(denominador, errors="coerce")
    return (num / den.where(den > 0)).round(6)


def indicadores_censo(bronze_situacao: pd.DataFrame, bronze_esgoto: pd.DataFrame) -> pd.DataFrame:
    """Contagens do Censo 2022 e as duas razões que elas alimentam.

        pct_populacao_rural = rural / (urbana + rural)
        pct_esgoto_adequado = domicilios_com_esgoto_adequado / domicilios_com_banheiro

    Uma linha por município, sem ano: é atributo estrutural, replicado na janela.

    Duas notas sobre o esgoto:

    * o numerador é a categoria PRONTA do IBGE ("Rede geral, rede pluvial ou fossa
      ligada à rede") — a definição da própria fonte, sem risco de dupla contagem.
      As parcelas "Rede geral ou pluvial" e "Fossa séptica ... ligada à rede" são
      pedidas só para conferir que a soma delas bate com a categoria-pai;
    * o SIDRA não publica "domicílios com banheiro" como categoria, então o
      denominador sai de ``Total - "Não tinham banheiro nem sanitário"``.
    """
    # As duas classificações têm uma categoria "Total". Juntar os quadros num merge
    # produziria Total_x/Total_y; alinhar por índice mantém cada categoria no seu
    # contexto e sem ambiguidade de nome.
    situacao = pivotar_categorias(
        bronze_situacao, JOBS_POR_ENTIDADE[ENTIDADE_SITUACAO]
    ).set_index("id_municipio")
    esgoto = pivotar_categorias(bronze_esgoto, JOBS_POR_ENTIDADE[ENTIDADE_ESGOTO]).set_index(
        "id_municipio"
    )
    municipios = situacao.index.union(esgoto.index)
    situacao = situacao.reindex(municipios)
    esgoto = esgoto.reindex(municipios)

    urbana = situacao[CAT_SITUACAO_URBANA]
    rural = situacao[CAT_SITUACAO_RURAL]
    total_situacao = situacao[CAT_SITUACAO_TOTAL]
    total_esgoto = esgoto[CAT_ESGOTO_TOTAL]
    adequado = esgoto[CAT_ESGOTO_ADEQUADO]
    rede = esgoto[CAT_ESGOTO_REDE]
    fossa = esgoto[CAT_ESGOTO_FOSSA_LIGADA]
    sem_banheiro = esgoto[CAT_ESGOTO_SEM_BANHEIRO]
    com_banheiro = total_esgoto - sem_banheiro

    # Conferência 1: o Censo publica urbana + rural = total. Se não fechar, a leitura
    # das categorias está errada — não adianta a razão estar "bonita".
    _conferir_identidade(
        "situação do domicílio", urbana + rural, total_situacao, "urbana+rural", "total"
    )
    # Conferência 2: a categoria-pai usada como numerador tem de ser a soma das duas
    # parcelas. Se não for, o nome resolveu para outra categoria — e o número sairia
    # plausível mesmo assim.
    _conferir_identidade(
        "esgotamento sanitário",
        rede + fossa,
        adequado,
        "rede+fossa_ligada",
        f"categoria {CAT_ESGOTO_ADEQUADO!r}",
    )

    resultado = pd.DataFrame(
        {
            "pop_urbana_censo": urbana,
            "pop_rural_censo": rural,
            "dom_total_censo": total_esgoto,
            "dom_esgoto_adequado_censo": adequado,
            "dom_rede_geral_censo": rede,
            "dom_fossa_ligada_censo": fossa,
            "dom_sem_banheiro_censo": sem_banheiro,
            MEDIDA_PCT_RURAL: _razao(rural, urbana + rural),
            MEDIDA_PCT_ESGOTO: _razao(adequado, com_banheiro),
        },
        index=municipios,
    ).reset_index()
    logger.info(
        "censo 2022: {:,} municípios | pct_populacao_rural nulo em {:,} | "
        "pct_esgoto_adequado nulo em {:,}",
        len(resultado),
        int(resultado[MEDIDA_PCT_RURAL].isna().sum()),
        int(resultado[MEDIDA_PCT_ESGOTO].isna().sum()),
    )
    return resultado


def _conferir_identidade(
    contexto: str, calculado: pd.Series, publicado: pd.Series, nome_calc: str, nome_pub: str
) -> None:
    """Compara uma soma nossa com o agregado que o próprio IBGE publica.

    Não interrompe: divergência pequena é arredondamento ou controle de divulgação. O
    que não pode é passar despercebida — divergência sistemática significa categoria
    errada, e o número sairia plausível mesmo assim.
    """
    a = pd.to_numeric(calculado, errors="coerce")
    b = pd.to_numeric(publicado, errors="coerce")
    comparavel = a.notna() & b.notna()
    if not int(comparavel.sum()):
        logger.warning("{}: nada comparável entre {} e {}.", contexto, nome_calc, nome_pub)
        return
    divergentes = comparavel & ((a - b).abs() > 0)
    n = int(divergentes.sum())
    if n:
        maior = float((a - b).abs().max())
        logger.warning(
            "{}: {} de {} municípios com {} != {} (maior diferença: {:,.0f}).",
            contexto,
            n,
            int(comparavel.sum()),
            nome_calc,
            nome_pub,
            maior,
        )
    else:
        nao_comparaveis = len(a) - int(comparavel.sum())
        logger.info(
            "{}: {} == {} nos {:,} municípios comparáveis ({:,} sem comparação).",
            contexto,
            nome_calc,
            nome_pub,
            int(comparavel.sum()),
            nao_comparaveis,
        )


def _registrar_fora_do_censo(combinada: pd.DataFrame) -> None:
    """Nomeia os municípios sem atributos do Censo, em vez de só contar linhas.

    São municípios criados depois do Censo {ANO_REFERENCIA_AREA}: existem na série de
    estimativas, mas não no universo censitário, então ficam sem área e sem os
    indicadores derivados dele. É condição esperada e transitória — some no próximo
    Censo. Os checks de qualidade não cobram cada caso, cobram a PROPORÇÃO
    (``area_ausente_excessiva`` e ``censo_ausente_excessivo``, ambos críticos).

    Listar por nome é o que mantém a exceção documentada sem fixá-la no código: se
    outro município for criado, ele aparece aqui sozinho.
    """
    sem_censo = combinada[MEDIDA_AREA].isna()
    if not int(sem_censo.sum()):
        return
    fora = combinada.loc[sem_censo, ["id_municipio", "nome_municipio", "sigla_uf"]]
    fora = fora.drop_duplicates("id_municipio")
    nomes = ", ".join(
        f"{r.nome_municipio} - {r.sigla_uf} ({r.id_municipio})" for r in fora.itertuples()
    )
    logger.warning(
        "{}: {} município(s) fora do universo do Censo {} — {:,} linha(s) sem área nem "
        "indicadores do Censo: {}",
        ENTITY,
        len(fora),
        ANO_REFERENCIA_AREA,
        int(sem_censo.sum()),
        nomes,
    )


def anos_sem_estimativa(estrutural: pd.DataFrame) -> pd.DataFrame:
    """Linhas dos anos em que o IBGE não publicou estimativa de população.

    A população fica NULA. Repetir a contagem do Censo como se fosse outro ano
    seria inventar um ponto de uma série anual que o IBGE deliberadamente não
    publicou, e o modelo leria o número como medição. Os atributos estruturais
    (área e os indicadores do Censo) vão preenchidos: não são série, e o valor do
    Censo é o valor correto para o ano.

    O universo de municípios vem do Censo, então um município criado depois dele
    não terá linha nesses anos — o que é fiel: ele não existia na referência.
    """
    if not ANOS_SEM_ESTIMATIVA:
        return pd.DataFrame(columns=[*COLS_MUNICIPIO, *COLS_ESTRUTURAIS, "ano", MEDIDA_POPULACAO])

    blocos = []
    for ano in ANOS_SEM_ESTIMATIVA:
        bloco = estrutural.copy()
        bloco["ano"] = pd.Series(ano, index=bloco.index, dtype="Int64")
        bloco[MEDIDA_POPULACAO] = pd.Series(pd.NA, index=bloco.index, dtype="Float64")
        blocos.append(bloco)
        logger.info(
            "{}: {:,} municípios em {} sem estimativa (população nula por decisão).",
            ENTITY,
            len(bloco),
            ano,
        )
    return pd.concat(blocos, ignore_index=True)


def run_silver() -> None:
    silver_ts = datetime.now(UTC)
    SILVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando camada Silver IBGE...")
    logger.info("BRONZE_DATA_DIR : {}", BRONZE_DATA_DIR)
    logger.info("SILVER_DATA_DIR : {}", SILVER_DATA_DIR)

    populacao = pivotar(
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_POPULACAO), JOBS_POR_ENTIDADE[ENTIDADE_POPULACAO]
    )
    area = area_estrutural(read_parquet(BRONZE_DATA_DIR / ENTIDADE_AREA))
    censo = indicadores_censo(
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_SITUACAO),
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_ESGOTO),
    )
    renda_mediana = medida_estrutural(
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_RENDA_MEDIANA), ENTIDADE_RENDA_MEDIANA
    )
    renda_media = medida_estrutural(
        read_parquet(BRONZE_DATA_DIR / ENTIDADE_RENDA_MEDIA), ENTIDADE_RENDA_MEDIA
    )

    # Tudo que é atributo do município, num quadro só: rótulos + área + Censo 2022.
    estrutural = (
        area.merge(censo, on="id_municipio", how="left")
        .merge(renda_mediana, on="id_municipio", how="left")
        .merge(renda_media, on="id_municipio", how="left")
    )
    _conferir_assimetria_renda(estrutural)

    combinada = populacao.merge(
        estrutural[["id_municipio", *COLS_ESTRUTURAIS]], on="id_municipio", how="left"
    )
    _registrar_fora_do_censo(combinada)

    combinada = pd.concat([combinada, anos_sem_estimativa(estrutural)], ignore_index=True)
    combinada = combinada.loc[combinada["ano"].isin(ANOS_IBGE)].sort_values(
        ["ano", "id_municipio"], ignore_index=True
    )
    silver = add_metadata(combinada[SILVER_COLS], silver_ts)
    write_parquet_partitioned(silver, SILVER_DATA_DIR / ENTITY, "ano", overwrite_entity=True)
    logger.info("{} gravada. Total: {:,}", ENTITY, len(silver))

    for ano, grupo in silver.groupby("ano", dropna=True):
        com_pop = int(grupo[MEDIDA_POPULACAO].notna().sum())
        populacao = (
            f"{grupo[MEDIDA_POPULACAO].sum():,.0f}" if com_pop else "sem estimativa publicada"
        )
        logger.info(
            "  {}: {:,} municípios | população {} | área somada {:,.0f} km²",
            ano,
            grupo["id_municipio"].nunique(),
            populacao,
            grupo[MEDIDA_AREA].sum(),
        )

    for tabela, checks in CHECKS_SILVER.items():
        df = read_parquet(SILVER_DATA_DIR / tabela)
        checar_qualidade(tabela, df, checks, "SILVER")
        del df

    logger.success("Camada Silver IBGE validada com sucesso.")


if __name__ == "__main__":
    run_silver()
