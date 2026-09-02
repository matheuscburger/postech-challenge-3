"""
Integração — Camada Gold: Base Enriquecida (Atlas) x FUNDEB (NSE)
=====================================================================

Segunda etapa da integração da camada gold: parte do resultado de
`gerar_gold_atlas.py` (aluno_contexto já enriquecido com o Atlas do
Desenvolvimento Humano) e adiciona o Nível Socioeconômico (NSE) do
FUNDEB, tanto no nível de município quanto de UF.

Fonte do FUNDEB: tabela gold `nse_entes_federados`
(src/preprocessing/fundeb/gold.py, no repositório principal), com colunas
ano, codigo_ente, tipo_ente ("municipio" | "uf"), nome_ente, sigla_uf,
valor_nse, ponderador_nse.

Design (decisões já validadas com o usuário):
  - Ano de 2023 do INEP não tem NSE do FUNDEB (que só cobre 2024/2025) ->
    usamos o valor de 2024 como proxy, marcando a origem com uma flag.
  - O NSE da UF entra como coluna separada (ctx_nse_uf), além do NSE do
    município (ctx_nse_municipio) — não é usado como fallback.

Chaves de join:
  - NSE de município: codigo_ente (int, 7 dígitos) -> id_municipio (string, zfill 7)
  - NSE de UF:          codigo_ente (int, 2 dígitos) -> id_uf (string, zfill 2)

Novas colunas adicionadas:
  ctx_nse_municipio, ctx_ponderador_nse_municipio, ctx_nse_municipio_proxy_2023,
  ctx_nse_uf, ctx_ponderador_nse_uf, ctx_nse_uf_proxy_2023
"""

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
GOLD_DIR = BASE_DIR / "data" / "gold"


def preparar_nse_municipio(nse: pd.DataFrame) -> pd.DataFrame:
    """Filtra tipo_ente == 'municipio', normaliza id_municipio, aplica proxy 2023<-2024."""
    nse_mun = nse.loc[nse["tipo_ente"] == "municipio"].copy()
    nse_mun["id_municipio"] = nse_mun["codigo_ente"].astype("Int64").astype(str).str.zfill(7)

    base = nse_mun[["ano", "id_municipio", "valor_nse", "ponderador_nse"]].copy()
    base["nse_proxy"] = False

    proxy_2023 = base.loc[base["ano"] == 2024].copy()
    proxy_2023["ano"] = 2023
    proxy_2023["nse_proxy"] = True

    return pd.concat([base, proxy_2023], ignore_index=True)


def preparar_nse_uf(nse: pd.DataFrame) -> pd.DataFrame:
    """Filtra tipo_ente == 'uf', normaliza id_uf, aplica proxy 2023<-2024."""
    nse_uf = nse.loc[nse["tipo_ente"] == "uf"].copy()
    nse_uf["id_uf"] = nse_uf["codigo_ente"].astype("Int64").astype(str).str.zfill(2)

    base = nse_uf[["ano", "id_uf", "valor_nse", "ponderador_nse"]].copy()
    base["nse_proxy"] = False

    proxy_2023 = base.loc[base["ano"] == 2024].copy()
    proxy_2023["ano"] = 2023
    proxy_2023["nse_proxy"] = True

    return pd.concat([base, proxy_2023], ignore_index=True)


def integrar_fundeb(base: pd.DataFrame, nse: pd.DataFrame) -> pd.DataFrame:
    """Junta ctx_nse_municipio e ctx_nse_uf à base já enriquecida com o Atlas."""
    n_antes = len(base)

    nse_mun = preparar_nse_municipio(nse).rename(
        columns={
            "valor_nse": "ctx_nse_municipio",
            "ponderador_nse": "ctx_ponderador_nse_municipio",
            "nse_proxy": "ctx_nse_municipio_proxy_2023",
        }
    )
    nse_uf = preparar_nse_uf(nse).rename(
        columns={
            "valor_nse": "ctx_nse_uf",
            "ponderador_nse": "ctx_ponderador_nse_uf",
            "nse_proxy": "ctx_nse_uf_proxy_2023",
        }
    )

    resultado = base.merge(nse_mun, on=["ano", "id_municipio"], how="left")
    resultado = resultado.merge(nse_uf, on=["ano", "id_uf"], how="left")

    n_depois = len(resultado)
    if n_depois != n_antes:
        raise AssertionError(
            f"Join alterou o número de linhas: {n_antes} -> {n_depois}. "
            f"Verifique duplicatas em (ano, id_municipio) ou (ano, id_uf) no FUNDEB gold."
        )

    cobertura_mun = resultado["ctx_nse_municipio"].notna().mean() * 100
    cobertura_uf = resultado["ctx_nse_uf"].notna().mean() * 100
    n_proxy = int(resultado["ctx_nse_municipio_proxy_2023"].sum())
    print(f"Cobertura NSE município: {cobertura_mun:.1f}%")
    print(f"Cobertura NSE UF:        {cobertura_uf:.1f}%")
    print(f"Linhas usando proxy 2023 (valor de 2024): {n_proxy}")

    if cobertura_mun < 90:
        print(
            "⚠️ Aviso: cobertura de NSE município abaixo de 90% — verifique formato de "
            "id_municipio (string, 7 dígitos) nas duas bases."
        )

    return resultado


def run(base_path: Path, nse_path: Path) -> pd.DataFrame:
    print(f"Carregando base enriquecida (Atlas) de: {base_path}")
    base = pd.read_csv(base_path, dtype={"id_municipio": str, "id_uf": str})
    print(f"Base: {len(base)} linhas, {len(base.columns)} colunas")

    print(f"Carregando FUNDEB gold (nse_entes_federados) de: {nse_path}")
    if nse_path.suffix == ".parquet":
        nse = pd.read_parquet(nse_path)
    else:
        nse = pd.read_csv(nse_path)
    print(f"FUNDEB: {len(nse)} linhas")

    resultado = integrar_fundeb(base, nse)

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    destino = GOLD_DIR / "aluno_contexto_enriquecido_atlas_fundeb.csv"
    resultado.to_csv(destino, index=False)
    print(f"Salvo em: {destino}")
    print(f"Resultado final: {len(resultado)} linhas, {len(resultado.columns)} colunas")

    return resultado


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        base_path = Path(sys.argv[1])
        nse_path = Path(sys.argv[2])
    else:
        print("Uso real: python gerar_gold_fundeb.py caminho/aluno_contexto_enriquecido_atlas.csv caminho/nse_entes_federados.parquet")
        print("Nenhum caminho informado — usando dados de teste locais, se existirem.")
        base_path = GOLD_DIR / "aluno_contexto_enriquecido_atlas.csv"
        nse_path = GOLD_DIR / "nse_entes_federados_TESTE.csv"

    resultado = run(base_path, nse_path)
    print("\nColunas novas de contexto:")
    novas = [c for c in resultado.columns if c.startswith("ctx_nse")]
    print(resultado[["id_aluno", "ano", "id_municipio", *novas]].head(10).to_string())
