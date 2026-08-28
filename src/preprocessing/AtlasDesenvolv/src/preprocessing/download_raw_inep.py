"""
Download — Camada Raw: Microdados e Metas de Alfabetização (INEP)
=====================================================================

Este script baixa os arquivos OFICIAIS e ORIGINAIS usados no pipeline da
Fase 2 (repositório https://github.com/diego-nasc/postech-challenge-2),
replicando localmente o que o job `glue_elt_raw.py` faz no S3.

⚠️ IMPORTANTE — RODE ESTE SCRIPT NA SUA MÁQUINA LOCAL, NÃO NO AMBIENTE
DO CLAUDE. O ambiente de execução do Claude tem a rede restrita a poucos
domínios (GitHub, PyPI, npm etc.) e não consegue alcançar
download.inep.gov.br. Rodando localmente na sua máquina, isso não deve
ser um problema.

O que este script faz:
  1. Baixa os ZIPs de microdados (2023, 2024, 2025) e extrai apenas os
     3 arquivos usados no projeto: TS_ALUNO.csv, TS_ESTADO.csv,
     TS_MUNICIPIO.csv
  2. Baixa as planilhas de metas (municípios e UFs) para os 3 anos
  3. Salva tudo em data/raw/inep/, espelhando a camada "Raw" do pipeline
     oficial (dado exatamente como veio da fonte, sem transformação)

Tamanho aproximado dos downloads: os ZIPs de microdados podem ter
centenas de MB a alguns GB cada (são microdados de milhões de alunos).
Terá que ter espaço em disco e paciência/banda de internet.

Uso:
    python download_raw_inep.py            # baixa tudo (2023-2025)
    python download_raw_inep.py --ano 2024  # baixa só um ano
"""

import argparse
import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "inep"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# URLs oficiais — extraídas de src/aws/glue_elt_raw.py do repositório da Fase 2
MICRODADOS_INEP = {
    2023: ["https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2023.zip"],
    2024: ["https://download.inep.gov.br/dados_abertos/microdados_avaliacao_da_alfabetizacao_2024.zip"],
    2025: ["https://download.inep.gov.br/dados_abertos/microdados_AEEB_2025.zip"],
}

METAS_INEP = {
    2023: [
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_municipios.xlsx",
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados_e_metas_ufs.xlsx",
    ],
    2024: [
        "https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_municipios_2024.xlsx",
        "https://download.inep.gov.br/alfabetiza_brasil/resultados_e_metas_ufs_2024_2.xlsx",
    ],
    2025: [
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_municipios_2025_v2.xlsx",
        "https://download.inep.gov.br/avaliacao_da_alfabetizacao/resultados/resultados_e_metas_ufs_2025_v1.xlsx",
    ],
}

# Dentro do ZIP de microdados, só estes 3 arquivos são usados pelo pipeline
ARQUIVOS_ALVO = ["DADOS/TS_ALUNO.csv", "DADOS/TS_ESTADO.csv", "DADOS/TS_MUNICIPIO.csv"]


def baixar_arquivo(url: str, destino: Path, timeout: int = 120):
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        print(f"  já existe, pulando: {destino.name}")
        return
    print(f"  baixando: {url}")
    with requests.get(url, headers=HEADERS, stream=True, timeout=timeout, verify=False) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    print(f"  ok: {destino}")


def extrair_arquivos_alvo(zip_path: Path, destino_dir: Path):
    destino_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        nomes_no_zip = z.namelist()
        for alvo in ARQUIVOS_ALVO:
            # Alguns anos podem ter variação de maiúsculas/minúsculas ou path
            candidatos = [n for n in nomes_no_zip if n.upper().endswith(alvo.upper().split("/")[-1])]
            if not candidatos:
                print(f"  aviso: {alvo} não encontrado no zip {zip_path.name}")
                continue
            nome_real = candidatos[0]
            with z.open(nome_real) as fsrc:
                out_path = destino_dir / Path(alvo).name
                with open(out_path, "wb") as fdst:
                    fdst.write(fsrc.read())
            print(f"  extraído: {out_path}")


def main(anos):
    for ano in anos:
        print(f"\n=== Ano {ano} — microdados ===")
        for url in MICRODADOS_INEP.get(ano, []):
            nome_zip = url.split("/")[-1]
            zip_path = RAW_DIR / "microdados" / str(ano) / nome_zip
            baixar_arquivo(url, zip_path)
            extrair_arquivos_alvo(zip_path, RAW_DIR / "microdados" / str(ano) / "DADOS")

        print(f"\n=== Ano {ano} — metas ===")
        for url in METAS_INEP.get(ano, []):
            nome_arquivo = url.split("/")[-1]
            destino = RAW_DIR / "metas" / str(ano) / nome_arquivo
            baixar_arquivo(url, destino)

    print("\nConcluído. Arquivos salvos em:", RAW_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, choices=[2023, 2024, 2025], default=None)
    args = parser.parse_args()

    anos = [args.ano] if args.ano else [2023, 2024, 2025]
    main(anos)
