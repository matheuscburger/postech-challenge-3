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
from src.preprocessing.ibge.schemas import API_JOBS, ApiJob

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


def url_serie(agregado: int, ano: int, variavel: str, nivel: str) -> str:
    """Monta a rota de série: um pedido só cobre todos os municípios via N6[all]."""
    return f"{API_BASE}/{agregado}/periodos/{ano}/variaveis/{variavel}?localidades={nivel}[all]"


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
            "{}: agregado {} | períodos {} | nível {} | variável {!r}",
            job.entidade,
            job.agregado,
            job.periodos,
            job.nivel,
            job.variavel,
        )
        _conferir_periodos(job)
        time.sleep(PAUSA_ENTRE_CHAMADAS)

        for ano in job.periodos:
            logger.info(f"Ano {ano}:")
            metadados = carregar_metadados(job.agregado, ano)
            variavel = variavel_do_agregado(metadados, job.agregado, job.variavel)
            time.sleep(PAUSA_ENTRE_CHAMADAS)

            payload = baixar_json(
                url_serie(job.agregado, ano, variavel, job.nivel),
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
            logger.info(
                "  classif. {:>6} | {} | {} categoria(s)",
                cls.get("id"),
                cls.get("nome"),
                len(cls.get("categorias") or []),
            )
        time.sleep(PAUSA_ENTRE_CHAMADAS)
    logger.success("Inspeção concluída.")


if __name__ == "__main__":
    import sys

    if "--inspecionar" in sys.argv:
        inspecionar()
    else:
        baixar_dados_ibge()
