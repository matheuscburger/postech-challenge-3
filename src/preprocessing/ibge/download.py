"""Download IBGE aggregate series from the API into data/raw/{ano}.

Diferente das outras fontes, o IBGE não publica ZIP anual: publica API. O contrato de
download aqui é gravar a resposta *crua* em disco, para que a Bronze possa ser
reconstruída sem depender da API estar de pé e para que `--skip-download` funcione
igual ao resto do projeto.

O layout segue o das demais fontes, uma pasta por ano — é feito um pedido por ano, de
modo que cada arquivo em data/raw/{ano} seja a resposta íntegra daquele ano:

    data/external/{ano}/agregado_{id}_metadados.json   metadados da API (auxiliar)
    data/raw/{ano}/{entidade}_{ano}.json               a série, que a Bronze lê
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from loguru import logger
import requests
from requests.exceptions import RequestException

from src.config import EXTERNAL_DATA_DIR, MAX_DOWNLOAD_ATTEMPTS, RAW_DATA_DIR
from src.preprocessing.ibge.schemas import API_JOBS, NIVEL_MUNICIPIO, ApiJob, normalizar_nome

API_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# A API é pública e sem chave de acesso. A pausa é cortesia, não exigência.
PAUSA_ENTRE_CHAMADAS = 1.0


def _destino(base: Path, ano: int, nome_arquivo: str) -> Path:
    pasta = base / str(ano)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / nome_arquivo


def caminho_metadados(agregado: int, ano: int) -> Path:
    return _destino(EXTERNAL_DATA_DIR, ano, f"agregado_{agregado}_metadados.json")


def caminho_serie(entidade: str, ano: int) -> Path:
    return _destino(RAW_DATA_DIR, ano, f"{entidade}_{ano}.json")


def url_metadados(agregado: int) -> str:
    return f"{API_BASE}/{agregado}/metadados"


def url_periodos(agregado: int) -> str:
    return f"{API_BASE}/{agregado}/periodos"


def url_serie(
    agregado: int,
    ano: int,
    variavel: str,
    nivel: str,
    classificacoes: list[tuple[str, list[str]]] | None = None,
) -> str:
    """Monta a rota de série: um pedido só cobre todos os municípios via N6[all].

    ``classificacoes`` são pares (id, [ids de categoria]) já resolvidos por
    ``classificacoes_do_agregado``. Várias entram no mesmo pedido separadas por ``|``,
    que é como a API cruza dimensões: ``&classificacao=2[6794]|86[95251]``.
    """
    url = f"{API_BASE}/{agregado}/periodos/{ano}/variaveis/{variavel}?localidades={nivel}[all]"
    partes = [f"{cls}[{','.join(cats)}]" for cls, cats in (classificacoes or []) if cats]
    if partes:
        url += "&classificacao=" + "|".join(partes)
    return url


def localizar_por_nome(
    itens: list[tuple[str, str]], desejado: str
) -> tuple[str, str, str] | None:
    """Acha o item cujo nome casa com ``desejado``.

    Devolve ``(id, nome_publicado, tipo)`` com tipo em {"exato", "prefixo"}, ou None.
    Separar os dois tipos importa: casamento por prefixo é conveniência, mas também é
    como uma categoria mais específica pode ser escolhida por engano.
    """
    alvo = normalizar_nome(desejado)
    for i, nome in itens:
        if normalizar_nome(nome) == alvo:
            return i, nome, "exato"
    for i, nome in itens:
        if normalizar_nome(nome).startswith(alvo):
            return i, nome, "prefixo"
    return None


def _casar_por_nome(itens: list[tuple[str, str]], desejado: str, contexto: str) -> str:
    """Escolhe o id cujo nome casa com ``desejado``: exato, depois prefixo."""
    achado = localizar_por_nome(itens, desejado)
    if achado is None:
        disponiveis = ", ".join(f"{i}={nome!r}" for i, nome in itens)
        raise ValueError(f"{contexto}: nada casa com {desejado!r}. Disponíveis: {disponiveis}")
    id_item, nome_publicado, tipo = achado
    if tipo == "prefixo":
        logger.warning(
            "{}: {!r} casou por PREFIXO com {!r} (id {}). Confirme com --conferir; se não "
            "for a categoria pretendida, ajuste a constante no schemas.py.",
            contexto,
            desejado,
            nome_publicado,
            id_item,
        )
    return id_item


def classificacoes_do_agregado(
    metadados: dict,
    agregado: int,
    declaradas: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[tuple[str, list[str]]]:
    """Resolve todas as classificações do job: NOMES -> ids.

    Erra alto e cedo listando o que existe: pegar a categoria errada é o tipo de bug
    que não aparece no schema nem no total, só no resultado.

    Atenção a um detalhe do SIDRA: "Total" tem id DIFERENTE em cada classificação
    (6794 em Sexo, 95251 em Cor ou raça, 95253 em Grupo de idade). Por isso cada
    categoria é resolvida dentro da sua própria classificação.
    """
    if not declaradas:
        return []

    publicadas = metadados.get("classificacoes") or []
    if not publicadas:
        pedidas = [nome for nome, _ in declaradas]
        raise ValueError(
            f"Agregado {agregado}: metadados sem classificações, mas o job pede "
            f"{pedidas}. Chaves recebidas: {sorted(metadados)}"
        )

    pares = [(str(c.get("id")), str(c.get("nome", ""))) for c in publicadas]
    resolvidas: list[tuple[str, list[str]]] = []

    for nome_classificacao, nomes_categorias in declaradas:
        cls_id = _casar_por_nome(pares, nome_classificacao, f"Agregado {agregado}: classificação")
        escolhida = next(c for c in publicadas if str(c.get("id")) == cls_id)
        categorias = [
            (str(cat.get("id")), str(cat.get("nome", "")))
            for cat in escolhida.get("categorias") or []
        ]
        ids = [
            _casar_por_nome(categorias, nome, f"Agregado {agregado}: categoria de {cls_id}")
            for nome in nomes_categorias
        ]
        logger.info(
            "Agregado {}: classificação {} ({}) | categorias {}",
            agregado,
            cls_id,
            escolhida.get("nome"),
            dict(zip(ids, nomes_categorias, strict=True)),
        )
        resolvidas.append((cls_id, ids))

    return resolvidas


def baixar_json(url: str, destino: Path | None, espera: int = 5) -> Any:
    """Baixa ``url`` como JSON e, se ``destino`` for dado, grava a resposta crua."""
    logger.info(f"Consultando {url}")
    for tentativa in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            resposta = requests.get(url, headers=HEADERS, timeout=(30, 180))
            resposta.raise_for_status()
            payload = resposta.json()
            if destino is not None:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.info(f"Resposta gravada: {destino}")
            return payload
        except (RequestException, ValueError) as erro:
            if tentativa == MAX_DOWNLOAD_ATTEMPTS:
                logger.error(f"Falha após {MAX_DOWNLOAD_ATTEMPTS} tentativas: {url}")
                raise
            logger.warning(
                f"Tentativa {tentativa}/{MAX_DOWNLOAD_ATTEMPTS} falhou ({erro}). "
                f"Retry em {espera}s..."
            )
            time.sleep(espera)
    raise RuntimeError(f"Download falhou: {url}")


def carregar_metadados(agregado: int, ano: int, *, usar_cache: bool = False) -> dict:
    """Lê os metadados do agregado (do cache do ano ou da API)."""
    destino = caminho_metadados(agregado, ano)
    if usar_cache:
        if not destino.exists():
            raise FileNotFoundError(f"Metadados não encontrados em cache: {destino}")
        return json.loads(destino.read_text(encoding="utf-8"))
    return baixar_json(url_metadados(agregado), destino)


def variavel_do_agregado(metadados: dict, agregado: int, nome_desejado: str) -> str:
    """Resolve o id da variável pelo NOME declarado no job.

    Erra alto e cedo listando os nomes disponíveis: num agregado com várias variáveis,
    escolher por posição é roleta.
    """
    variaveis = metadados.get("variaveis") or []
    if not variaveis:
        raise ValueError(
            f"Agregado {agregado}: metadados sem lista de variáveis. "
            f"Chaves recebidas: {sorted(metadados)}"
        )

    alvo = nome_desejado.strip().casefold()
    nomes = [(str(v.get("id")), str(v.get("nome", ""))) for v in variaveis]
    exatas = [vid for vid, nome in nomes if nome.strip().casefold() == alvo]
    prefixo = [vid for vid, nome in nomes if nome.strip().casefold().startswith(alvo)]

    escolhida = (exatas or prefixo or [None])[0]
    if escolhida is None:
        disponiveis = ", ".join(f"{vid}={nome!r}" for vid, nome in nomes)
        raise ValueError(
            f"Agregado {agregado}: nenhuma variável casa com {nome_desejado!r}. "
            f"Disponíveis: {disponiveis}"
        )
    logger.info("Agregado {}: variável {} ({}).", agregado, escolhida, dict(nomes)[escolhida])
    return escolhida


def periodos_publicados(agregado: int) -> set[int] | None:
    """Enumera os períodos do agregado. Devolve None se o endpoint não responder.

    A janela `periodicidade.inicio/fim` dos metadados é um INTERVALO, não uma lista:
    o agregado 6579 declara [2001, 2026] e mesmo assim não tem 2022 nem 2023 para
    município. Só a enumeração diz a verdade.
    """
    try:
        payload = baixar_json(url_periodos(agregado), None)
    except (RequestException, RuntimeError, ValueError) as erro:
        logger.warning("Agregado {}: não foi possível enumerar períodos ({}).", agregado, erro)
        return None
    if not isinstance(payload, list):
        return None
    publicados: set[int] = set()
    for item in payload:
        bruto = item.get("id") if isinstance(item, dict) else item
        try:
            publicados.add(int(str(bruto)[:4]))
        except (TypeError, ValueError):
            continue
    return publicados or None


def _conferir_periodos(job: ApiJob) -> None:
    """Compara os períodos pedidos com os publicados, antes das chamadas de série."""
    publicados = periodos_publicados(job.agregado)
    if publicados is None:
        return
    faltando = sorted(set(job.periodos) - publicados)
    if faltando:
        raise ValueError(
            f"{job.entidade}: o agregado {job.agregado} não publica os períodos {faltando}. "
            f"Publicados: {sorted(publicados)}. Ajuste ANOS_ESTIMATIVA em schemas.py ou "
            f"escolha outro agregado."
        )
    logger.info("Agregado {}: períodos {} confirmados na publicação.", job.agregado, job.periodos)


def _periodos_na_resposta(payload: Any) -> set[str]:
    presentes: set[str] = set()
    if not isinstance(payload, list):
        return presentes
    for bloco in payload:
        for resultado in bloco.get("resultados") or []:
            for serie in resultado.get("series") or []:
                presentes.update((serie.get("serie") or {}).keys())
    return presentes


def _conferir_resposta(job: ApiJob, ano: int, payload: Any) -> None:
    """Confere o que de fato voltou para o ano. Esta é a verificação autoritativa."""
    presentes = _periodos_na_resposta(payload)
    if str(ano) not in presentes:
        raise ValueError(
            f"{job.entidade}: a API não devolveu o período {ano} para o nível {job.nivel}. "
            f"Devolveu: {sorted(presentes)}. Rode "
            f"`python -m src.preprocessing.ibge.download --inspecionar` para ver o que "
            f"o agregado {job.agregado} publica."
        )


def baixar_dados_ibge() -> None:
    """Baixa metadados e séries dos agregados contratados, uma pasta por ano."""
    logger.info("Iniciando extração dos dados do IBGE...")
    EXTERNAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("EXTERNAL_DATA_DIR : {}", EXTERNAL_DATA_DIR)
    logger.info("RAW_DATA_DIR      : {}", RAW_DATA_DIR)

    for job in API_JOBS:
        logger.info(
            "{}: agregado {} | períodos {} | nível {} | variável {!r} | {} classificação(ões)",
            job.entidade,
            job.agregado,
            job.periodos,
            job.nivel,
            job.variavel,
            len(job.classificacoes),
        )
        _conferir_periodos(job)
        time.sleep(PAUSA_ENTRE_CHAMADAS)

        for ano in job.periodos:
            logger.info(f"Ano {ano}:")
            metadados = carregar_metadados(job.agregado, ano)
            variavel = variavel_do_agregado(metadados, job.agregado, job.variavel)
            classificacoes = classificacoes_do_agregado(
                metadados, job.agregado, job.classificacoes
            )
            time.sleep(PAUSA_ENTRE_CHAMADAS)

            payload = baixar_json(
                url_serie(job.agregado, ano, variavel, job.nivel, classificacoes),
                caminho_serie(job.entidade, ano),
            )
            _conferir_resposta(job, ano, payload)
            time.sleep(PAUSA_ENTRE_CHAMADAS)

    logger.success("Extração dos dados do IBGE concluída.")


def inspecionar(agregado: int | None = None) -> None:
    """Imprime o que o agregado oferece. Rode isto ANTES do pipeline completo.

        python -m src.preprocessing.ibge.download --inspecionar

    Serve para confirmar variáveis, períodos publicados e níveis territoriais antes de
    fixar qualquer coisa no schemas.py.
    """
    jobs = {job.agregado: job for job in API_JOBS}
    alvos = [agregado] if agregado else list(jobs)
    for alvo in alvos:
        ano = jobs[alvo].periodos[0] if alvo in jobs else max(job.periodos[-1] for job in API_JOBS)
        meta = carregar_metadados(alvo, ano)
        periodicidade = meta.get("periodicidade") or {}
        logger.info("=" * 72)
        logger.info("Agregado {} | {}", meta.get("id", alvo), meta.get("nome", "?"))
        logger.info("Pesquisa      : {}", meta.get("pesquisa", "?"))
        logger.info(
            "Janela        : {} a {} ({}) — intervalo, não lista",
            periodicidade.get("inicio", "?"),
            periodicidade.get("fim", "?"),
            periodicidade.get("frequencia", "?"),
        )
        publicados = periodos_publicados(alvo)
        logger.info("Publicados    : {}", sorted(publicados) if publicados else "não enumerados")
        niveis = (meta.get("nivelTerritorial") or {}).get("Administrativo", [])
        logger.info("Níveis        : {}", niveis)
        for var in meta.get("variaveis") or []:
            logger.info(
                "  variável {:>6} | {} | {}", var.get("id"), var.get("nome"), var.get("unidade")
            )
        for cls in meta.get("classificacoes") or []:
            categorias = cls.get("categorias") or []
            logger.info(
                "  classif. {:>6} | {} | {} categoria(s)",
                cls.get("id"),
                cls.get("nome"),
                len(categorias),
            )
            # Os NOMES são o que o schemas.py declara — imprimi-los é o que permite
            # conferir (e corrigir) as constantes CAT_* sem adivinhar.
            for cat in categorias:
                logger.info("      cat {:>8} | {}", cat.get("id"), cat.get("nome"))
        time.sleep(PAUSA_ENTRE_CHAMADAS)
    logger.success("Inspeção concluída.")


def url_catalogo() -> str:
    return API_BASE


def procurar(termo: str, nivel: str | None = NIVEL_MUNICIPIO) -> None:
    """Procura agregados do IBGE pelo NOME, no catálogo inteiro da API.

        python -m src.preprocessing.ibge.download --procurar "rendimento domiciliar"

    Existe porque escolher um agregado é a única etapa em que ainda se depende de
    saber o número da tabela por fora. O catálogo é a fonte: procurar nele evita
    tanto o chute quanto a busca no navegador, que devolve tabela de outro Censo.

    ``nivel`` filtra pelos agregados que publicam naquele nível territorial (N6 =
    município, o único que interessa a este projeto). Passe ``None`` para não filtrar.
    """
    payload = baixar_json(url_catalogo(), None)
    if not isinstance(payload, list):
        raise ValueError(f"Catálogo em formato inesperado: {type(payload).__name__}")

    alvo = normalizar_nome(termo)
    achados: list[tuple[str, str, str]] = []
    for pesquisa in payload:
        nome_pesquisa = str(pesquisa.get("nome", "?"))
        for agregado in pesquisa.get("agregados") or []:
            nome = str(agregado.get("nome", ""))
            if alvo in normalizar_nome(nome):
                achados.append((str(agregado.get("id")), nome, nome_pesquisa))

    if not achados:
        logger.warning("Nenhum agregado com {!r} no nome.", termo)
        return

    logger.info("{} agregado(s) com {!r} no nome:", len(achados), termo)
    for id_agregado, nome, pesquisa in achados:
        logger.info("  {:>6} | {} | {}", id_agregado, pesquisa, nome)

    if nivel:
        logger.info("")
        logger.info(
            "Para ver variáveis, períodos e categorias — e confirmar se publica em {}:",
            nivel,
        )
        logger.info(
            "  python -m src.preprocessing.ibge.download --inspecionar <id>",
        )


def _conferir_um(
    rotulo: str, declarado: str, publicados: list[tuple[str, str]], entidade: str
) -> tuple[str | None, str | None]:
    """Confere um nome declarado contra os publicados. Devolve (id_resolvido, problema)."""
    achado = localizar_por_nome(publicados, declarado)
    if achado is None:
        candidatos = ", ".join(repr(nome) for _, nome in publicados) or "(nenhum)"
        logger.error("  FALHA   {:<14} {!r}", rotulo, declarado)
        logger.error("          publicados: {}", candidatos)
        return None, f"{entidade}: {rotulo} {declarado!r} não existe no agregado"

    id_item, nome_publicado, tipo = achado
    if tipo == "exato":
        logger.info("  OK      {:<14} {!r} -> id {}", rotulo, declarado, id_item)
        return id_item, None

    logger.warning("  PREFIXO {:<14} {!r}", rotulo, declarado)
    logger.warning("          publicado: {!r} (id {})", nome_publicado, id_item)
    return id_item, (
        f"{entidade}: {rotulo} {declarado!r} casou por prefixo com {nome_publicado!r} "
        "— confirme se é a categoria pretendida"
    )


def conferir() -> None:
    """Confere, contra a API, todos os NOMES declarados no schemas.py.

        python -m src.preprocessing.ibge.download --conferir

    Existe porque variável, classificação e categoria são declaradas por NOME, não por
    id: é isso que evita o acoplamento silencioso a um id que o IBGE republica. O preço
    é que um nome errado só apareceria no download — este comando antecipa a descoberta
    e diz exatamente qual constante do schemas.py corrigir.
    """
    problemas: list[str] = []

    for job in API_JOBS:
        ano = job.periodos[0]
        logger.info("=" * 72)
        logger.info("{} | agregado {} | período {}", job.entidade, job.agregado, ano)
        try:
            meta = carregar_metadados(job.agregado, ano)
        except (RequestException, RuntimeError, ValueError, OSError) as erro:
            logger.error("  FALHA   metadados inacessíveis ({})", erro)
            problemas.append(f"{job.entidade}: metadados do agregado {job.agregado} ({erro})")
            continue

        variaveis = [
            (str(v.get("id")), str(v.get("nome", ""))) for v in meta.get("variaveis") or []
        ]
        _, problema = _conferir_um("variável", job.variavel, variaveis, job.entidade)
        if problema:
            problemas.append(problema)

        publicadas = meta.get("classificacoes") or []
        pares = [(str(c.get("id")), str(c.get("nome", ""))) for c in publicadas]
        for nome_classificacao, nomes_categorias in job.classificacoes:
            cls_id, problema = _conferir_um(
                "classificação", nome_classificacao, pares, job.entidade
            )
            if problema:
                problemas.append(problema)
            if cls_id is None:
                continue
            escolhida = next(c for c in publicadas if str(c.get("id")) == cls_id)
            categorias = [
                (str(c.get("id")), str(c.get("nome", "")))
                for c in escolhida.get("categorias") or []
            ]
            for nome in nomes_categorias:
                _, problema = _conferir_um("categoria", nome, categorias, job.entidade)
                if problema:
                    problemas.append(problema)

        time.sleep(PAUSA_ENTRE_CHAMADAS)

    logger.info("=" * 72)
    if not problemas:
        logger.success("Todos os nomes declarados no schemas.py conferem com a API.")
        return

    logger.error("{} nome(s) a revisar em src/preprocessing/ibge/schemas.py:", len(problemas))
    for p in problemas:
        logger.error("  - {}", p)
    raise SystemExit(1)


def _argumento_depois(argv: list[str], flag: str) -> str | None:
    """Valor logo após ``flag``, se houver."""
    if flag in argv:
        i = argv.index(flag) + 1
        if i < len(argv) and not argv[i].startswith("--"):
            return argv[i]
    return None


if __name__ == "__main__":
    import sys

    if "--procurar" in sys.argv:
        termo = _argumento_depois(sys.argv, "--procurar")
        if not termo:
            raise SystemExit(
                'Uso: python -m src.preprocessing.ibge.download --procurar "rendimento domiciliar"'
            )
        procurar(termo)
    elif "--inspecionar" in sys.argv:
        alvo = _argumento_depois(sys.argv, "--inspecionar")
        inspecionar(int(alvo) if alvo else None)
    elif "--conferir" in sys.argv:
        conferir()
    else:
        baixar_dados_ibge()
