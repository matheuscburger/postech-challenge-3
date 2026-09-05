"""Dry-run sintético de src/preprocessing/join.py.

Não toca em data/. Monta tabelas falsas em um diretório temporário com valores
escolhidos para que a defasagem seja verificável a olho nu:

    gold/municipio.taxa_alfabetizacao == float(ano)
    gold/municipio.meta               == float(ano) + 0.5

Logo, na base_analitica de um aluno do ano N:

    ctx_inep_mun_taxa_alfabetizacao_lag1 == N - 1   (defasado)
    ctx_inep_mun_meta                    == N + 0.5 (corrente)

Se algum dia alguém remover o lag, a primeira asserção quebra com a mensagem
exata do que passou a entrar.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.preprocessing import join as J  # noqa: E402
from src.preprocessing.io import read_parquet, write_parquet_partitioned  # noqa: E402

ANOS = [2023, 2024, 2025]
MUNICIPIOS = [("3500001", 35, "SP"), ("3500002", 35, "SP"), ("3100001", 31, "MG")]
ORFAO = ("9999999", 99, "ZZ")  # existe no aluno, não existe em nenhum contexto
DEPS = {2: "Estadual", 3: "Municipal"}


def montar(raiz: Path) -> None:
    # --- gold/aluno --------------------------------------------------------
    linhas = []
    i = 0
    for ano in ANOS:
        for mun, uf, _ in [*MUNICIPIOS, ORFAO]:
            for dep in DEPS:
                for _ in range(2):
                    i += 1
                    linhas.append(
                        {
                            "ano": ano,
                            "id_uf": uf,
                            "id_municipio": mun,
                            "id_escola": f"{mun}9",
                            "id_aluno": f"A{i:06d}",
                            "dependencia_administrativa": dep,
                            "label_alfabetizado": i % 2,
                        }
                    )
    aluno = pd.DataFrame(linhas)
    aluno["ano"] = aluno["ano"].astype("Int64")
    aluno["id_uf"] = aluno["id_uf"].astype("Int64")
    aluno["dependencia_administrativa"] = aluno["dependencia_administrativa"].astype("Int64")
    for c in ("id_municipio", "id_escola", "id_aluno"):
        aluno[c] = aluno[c].astype("string")
    write_parquet_partitioned(aluno, raiz / "aluno", "ano", overwrite_entity=True)

    # --- gold/municipio (INEP) --------------------------------------------
    mun_rows = [
        {
            "ano": ano,
            "id_uf": uf,
            "sigla_uf": sig,
            "id_municipio": mun,
            "nome_municipio": f"Cidade {mun}",
            "taxa_alfabetizacao": float(ano),
            "media_portugues": float(ano) + 0.1,
            "meta": float(ano) + 0.5,
            "percentual_participacao": float(ano) + 0.2,
            "nivel_alfabetizacao": float(ano) + 0.3,
        }
        for ano in ANOS
        for mun, uf, sig in MUNICIPIOS
    ]
    municipio = pd.DataFrame(mun_rows)
    municipio["ano"] = municipio["ano"].astype("Int64")
    municipio["id_uf"] = municipio["id_uf"].astype("Int64")
    municipio["id_municipio"] = municipio["id_municipio"].astype("string")
    write_parquet_partitioned(municipio, raiz / "municipio", "ano", overwrite_entity=True)

    # --- gold/ufs (INEP) ---------------------------------------------------
    ufs = pd.DataFrame(
        [
            {
                "ano": ano,
                "id_uf": uf,
                "sigla_uf": sig,
                "taxa_alfabetizacao": float(ano),
                "media_portugues": float(ano) + 0.1,
                "meta": float(ano) + 0.5,
                "percentual_participacao": float(ano) + 0.2,
            }
            for ano in ANOS
            for uf, sig in {(uf, sig) for _, uf, sig in MUNICIPIOS}
        ]
    )
    ufs["ano"] = ufs["ano"].astype("Int64")
    ufs["id_uf"] = ufs["id_uf"].astype("Int64")
    write_parquet_partitioned(ufs, raiz / "ufs", "ano", overwrite_entity=True)

    # --- gold/populacao_municipios (IBGE) ---------------------------------
    ibge = pd.DataFrame(
        [
            {
                "ano": ano,
                "id_municipio": mun,
                "nome_municipio": f"Cidade {mun}",
                "id_uf": uf,
                "sigla_uf": sig,
                # 2023 sem estimativa, como na Gold real
                "populacao_residente": pd.NA if ano == 2023 else ano * 100,
                "area_km2": 10.0,
                "pct_populacao_rural": 12.5,
                "pct_esgoto_adequado": 80.0,
                "renda_domiciliar_per_capita_mediana": 900.0,
                "renda_domiciliar_per_capita_media": 1500.0,
            }
            for ano in ANOS
            for mun, uf, sig in MUNICIPIOS
        ]
    )
    ibge["ano"] = ibge["ano"].astype("Int64")
    ibge["id_uf"] = ibge["id_uf"].astype("Int64")
    ibge["id_municipio"] = ibge["id_municipio"].astype("string")
    ibge["populacao_residente"] = ibge["populacao_residente"].astype("Int64")
    write_parquet_partitioned(
        ibge, raiz / "populacao_municipios", "ano", overwrite_entity=True
    )

    # --- gold/atu_municipios (Censo Escolar) ------------------------------
    # Inclui ruído de propósito: linhas fora de localizacao="Total" e da rede
    # Federal. Sem o filtro de join_atu, validate="m:1" quebraria aqui.
    atu_rows = []
    for ano in ANOS:
        for mun, _, sig in MUNICIPIOS:
            for loc in ("Total", "Urbana", "Rural"):
                for dep in ("Estadual", "Municipal", "Federal", "Privada"):
                    base = {
                        "ano": ano,
                        "regiao": "Sudeste",
                        "sigla_uf": sig,
                        "id_municipio": mun,
                        "nome_municipio": f"Cidade {mun}",
                        "localizacao": loc,
                        "dependencia_administrativa": dep,
                    }
                    # valor identificável: rede muda o número
                    marca = {"Estadual": 1.0, "Municipal": 2.0, "Federal": 3.0, "Privada": 4.0}[dep]
                    for col in J.METRIC_COLS:
                        base[col] = marca if loc == "Total" else -1.0
                    atu_rows.append(base)
    atu = pd.DataFrame(atu_rows)
    atu["ano"] = atu["ano"].astype("Int64")
    atu["id_municipio"] = atu["id_municipio"].astype("string")
    write_parquet_partitioned(atu, raiz / "atu_municipios", "ano", overwrite_entity=True)


def conferir(base: pd.DataFrame) -> None:
    falhas: list[str] = []

    def checar(nome: str, ok: bool, detalhe: str = "") -> None:
        print(f"  [{'OK  ' if ok else 'FALHA'}] {nome}{(' — ' + detalhe) if detalhe else ''}")
        if not ok:
            falhas.append(nome)

    print("\n=== Conferências ===")

    # 1. sem colisão de nomes
    checar(
        "nenhuma coluna _x/_y",
        not [c for c in base.columns if c.endswith(("_x", "_y"))],
    )

    # 2. defasagem do INEP: ano N carrega a medição de N-1
    conhecido = base[base["id_municipio"] != ORFAO[0]]
    for prefixo, rotulo in ((J.PREFIXO_INEP["municipio"], "município"), (J.PREFIXO_INEP["ufs"], "UF")):
        col_lag = f"{prefixo}taxa_alfabetizacao{J.SUFIXO_LAG}"
        com_lag = conhecido[conhecido["ano"] > min(ANOS)]
        esperado = (com_lag["ano"] - 1).astype("float64")
        checar(
            f"{rotulo}: {col_lag} == ano - 1",
            bool((com_lag[col_lag] == esperado).all()),
            f"{com_lag[col_lag].min():.0f}..{com_lag[col_lag].max():.0f}",
        )
        primeiro = conhecido[conhecido["ano"] == min(ANOS)]
        checar(
            f"{rotulo}: sem contexto defasado em {min(ANOS)}",
            bool(primeiro[col_lag].isna().all()),
        )
        # 3. meta é a única que entra no ano corrente
        col_meta = f"{prefixo}meta"
        checar(
            f"{rotulo}: {col_meta} == ano + 0.5 (mesmo ano)",
            bool((conhecido[col_meta] == conhecido["ano"].astype("float64") + 0.5).all()),
        )

    # 4. nenhuma coluna de resultado entrou sem sufixo de lag
    crus = [
        f"{p}{c}"
        for p in J.PREFIXO_INEP.values()
        for c in J.COLUNAS_LAG_OBRIGATORIO
        if f"{p}{c}" in base.columns
    ]
    checar("nenhum resultado do INEP entrou sem lag", not crus, str(crus))

    # 5. ATU casou na rede certa
    marca = {2: 1.0, 3: 2.0}
    col_atu = J.METRIC_RENAME["media_fundamental"]
    esperado_atu = conhecido["dependencia_administrativa"].map(marca).astype("float64")
    checar(
        f"ATU: {col_atu} bate com a rede do aluno",
        bool((conhecido[col_atu] == esperado_atu).all()),
        "Estadual=1.0, Municipal=2.0",
    )

    # 6. IBGE: área sempre, população nula só em 2023
    checar(
        "IBGE: area_km2 preenchida em todos os anos conhecidos",
        bool(conhecido["ctx_ibge_area_km2"].notna().all()),
    )
    pop = "ctx_ibge_populacao_residente"
    checar(
        "IBGE: população nula em 2023 e preenchida depois",
        bool(
            conhecido.loc[conhecido["ano"] == 2023, pop].isna().all()
            and conhecido.loc[conhecido["ano"] > 2023, pop].notna().all()
        ),
    )

    # 7. left join preservou o município órfão, com contexto nulo
    orfao = base[base["id_municipio"] == ORFAO[0]]
    ctx = [c for c in base.columns if c.startswith("ctx_")]
    checar(
        "município sem contexto sobrevive com ctx_* nulo",
        bool(len(orfao) > 0 and orfao[ctx].isna().all().all()),
        f"{len(orfao)} linhas, {len(ctx)} colunas ctx_*",
    )

    # 8. o alvo continua intacto
    checar(
        "label_alfabetizado sem nulos",
        bool(base["label_alfabetizado"].notna().all()),
    )

    print()
    if falhas:
        raise SystemExit(f"FALHAS: {falhas}")
    print(f"Todas as conferências passaram. base_analitica: "
          f"{len(base):,} linhas x {base.shape[1]} colunas")
    print("\nColunas de contexto criadas:")
    for c in ctx:
        print(f"  {c}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        J.PROCESSED_DATA_DIR = raiz
        montar(raiz)
        J.run_join()
        base = read_parquet(raiz / J.ENTIDADE_DESTINO)
        conferir(base)


if __name__ == "__main__":
    main()
