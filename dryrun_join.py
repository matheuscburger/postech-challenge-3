"""Dry-run sintético de src/preprocessing/join.py.

Não toca em data/. Monta tabelas falsas em um diretório temporário com valores
escolhidos para que cada propriedade seja verificável a olho nu:

    gold/municipio.taxa_alfabetizacao == float(ano)
    gold/municipio.meta               == float(ano) + 0.5

Logo, na base_analitica de um aluno do ano N:

    ctx_inep_mun_taxa_alfabetizacao_lag1 == N - 1   (defasado)
    ctx_inep_mun_meta                    == N + 0.5 (corrente)

Se algum dia alguém remover o lag, a primeira asserção quebra com a mensagem
exata do que passou a entrar.

O mesmo desenho cobre as outras fontes:

    gold/atlas.idhm         == marca do município (0.501/0.502/0.503), só 2010
    gold/nse.valor_nse      == float(ano) + 0.7 (município) / + 0.3 (UF)
    gold/nse.ponderador_nse == float(ano) + 0.07 (município) / + 0.03 (UF)

O Atlas existe só no ano-base: se o join passar a casar por ``ano``, todas as
colunas ``ctx_atlas_*`` viram nulo e a conferência acusa. O NSE existe só em
2024-2025: 2023 tem de sair **nulo**, sem proxy — e há um controle negativo que
reintroduz o proxy e exige que o guard pare o pipeline.

Dois municípios modelam ausências que não são falha de join:

    ORFAO     — não existe em contexto nenhum
    POS_2010  — existe em tudo menos no Atlas (como os 6 municípios reais
                criados depois do Censo 2010)
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import CORTE_PROFICIENCIA  # noqa: E402
from src.preprocessing import join as J  # noqa: E402
from src.preprocessing.inep.roles import ALVO_CLASSIFICACAO, ALVO_REGRESSAO  # noqa: E402
from src.preprocessing.io import read_parquet, write_parquet_partitioned  # noqa: E402

ANOS = [2023, 2024, 2025]
ANOS_NSE = [2024, 2025]  # o FUNDEB só publica estas edições
ANO_BASE_ATLAS = 2010

MUNICIPIOS = [("3500001", 35, "SP"), ("3500002", 35, "SP"), ("3100001", 31, "MG")]
POS_2010 = ("4300001", 43, "RS")  # existe em tudo menos no Atlas
ORFAO = ("9999999", 99, "ZZ")  # existe no aluno, não existe em nenhum contexto

# Municípios que aparecem em todas as fontes exceto o Atlas.
COM_CONTEXTO = [*MUNICIPIOS, POS_2010]
DEPS = {2: "Estadual", 3: "Municipal"}

# marca por município: 0.501, 0.502, 0.503 — identifica quem casou com quem
MARCA_ATLAS = {mun: 0.500 + (i + 1) / 1000 for i, (mun, _, _) in enumerate(MUNICIPIOS)}


def montar(raiz: Path) -> None:
    # --- gold/aluno --------------------------------------------------------
    linhas = []
    i = 0
    for ano in ANOS:
        for mun, uf, _ in [*COM_CONTEXTO, ORFAO]:
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
                            # A nota vem antes do rótulo, como em COLS_ALUNO, e
                            # respeita o corte real: 700 < 743 <= 800, então
                            # label_alfabetizado == (label_proficiencia >= corte)
                            # vale por construção e a conferência 10 pode exigi-la.
                            "label_proficiencia": 700.0 + (i % 2) * 100.0,
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
        for mun, uf, sig in COM_CONTEXTO
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
            for uf, sig in {(uf, sig) for _, uf, sig in COM_CONTEXTO}
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
            for mun, uf, sig in COM_CONTEXTO
        ]
    )
    ibge["ano"] = ibge["ano"].astype("Int64")
    ibge["id_uf"] = ibge["id_uf"].astype("Int64")
    ibge["id_municipio"] = ibge["id_municipio"].astype("string")
    ibge["populacao_residente"] = ibge["populacao_residente"].astype("Int64")
    write_parquet_partitioned(
        ibge, raiz / "populacao_municipios", "ano", overwrite_entity=True
    )

    # --- gold/atlas_desenvolvimento_humano --------------------------------
    # Só o ano-base 2010, e POS_2010 de fora: o Atlas acabou em 2010 e não
    # conhece município criado depois. Cada indicador recebe marca + posição,
    # então uma rotação no mapa de renome aparece na conferência.
    atlas_rows = []
    for mun, _, _ in MUNICIPIOS:
        linha = {
            "ano": ANO_BASE_ATLAS,
            "id_municipio": mun,
            "nome_municipio": f"Cidade {mun}",
        }
        for pos, col in enumerate(J.ATLAS_COLS):
            linha[col] = MARCA_ATLAS[mun] + pos
        atlas_rows.append(linha)
    atlas = pd.DataFrame(atlas_rows)
    atlas["ano"] = atlas["ano"].astype("Int64")
    atlas["id_municipio"] = atlas["id_municipio"].astype("string")
    write_parquet_partitioned(
        atlas, raiz / J.ATLAS_ENTIDADE, "ano", overwrite_entity=True
    )

    # --- gold/nse_entes_federados (FUNDEB) --------------------------------
    # Só 2024-2025, as edições que o INEP publica. 2023 tem de sair nulo.
    nse_rows = []
    for ano in ANOS_NSE:
        for mun, _, sig in COM_CONTEXTO:
            nse_rows.append(
                {
                    "ano": ano,
                    "codigo_ente": int(mun),
                    "tipo_ente": "municipio",
                    "nome_ente": f"Cidade {mun}",
                    "sigla_uf": sig,
                    "valor_nse": float(ano) + 0.7,
                    "ponderador_nse": float(ano) + 0.07,
                }
            )
        for uf, sig in {(uf, sig) for _, uf, sig in COM_CONTEXTO}:
            nse_rows.append(
                {
                    "ano": ano,
                    "codigo_ente": uf,
                    "tipo_ente": "uf",
                    "nome_ente": sig,
                    "sigla_uf": sig,
                    "valor_nse": float(ano) + 0.3,
                    "ponderador_nse": float(ano) + 0.03,
                }
            )
    nse = pd.DataFrame(nse_rows)
    nse["ano"] = nse["ano"].astype("Int64")
    nse["codigo_ente"] = nse["codigo_ente"].astype("Int64")
    nse["tipo_ente"] = nse["tipo_ente"].astype("string")
    write_parquet_partitioned(
        nse, raiz / J.FUNDEB_ENTIDADE, "ano", overwrite_entity=True
    )

    # --- gold/atu_municipios (Censo Escolar) ------------------------------
    # Inclui ruído de propósito: linhas fora de localizacao="Total" e da rede
    # Federal. Sem o filtro de join_atu, validate="m:1" quebraria aqui.
    atu_rows = []
    for ano in ANOS:
        for mun, _, sig in COM_CONTEXTO:
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


def conferir(base: pd.DataFrame) -> list[str]:
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

    # 7. Atlas: fixo no ano-base, replicado em todos os anos, casado por município
    com_atlas = conhecido[conhecido["id_municipio"] != POS_2010[0]]
    esperado_atlas = com_atlas["id_municipio"].map(MARCA_ATLAS).astype("float64")
    checar(
        "Atlas: ctx_atlas_idhm bate com a marca do município",
        bool((com_atlas["ctx_atlas_idhm"] == esperado_atlas).all()),
        f"marcas {sorted(MARCA_ATLAS.values())}",
    )
    por_ano = com_atlas.groupby(["id_municipio", "ano"])["ctx_atlas_idhm"].first().unstack()
    checar(
        f"Atlas: mesmo valor de {ANO_BASE_ATLAS} nos {len(ANOS)} anos (replicação)",
        bool(por_ano.nunique(axis=1).eq(1).all()),
        f"{por_ano.shape[0]} municípios x {por_ano.shape[1]} anos",
    )
    ultima = J.ATLAS_COLS[-1]
    checar(
        f"Atlas: ctx_atlas_{ultima} == marca + {len(J.ATLAS_COLS) - 1} (renome não rotacionou)",
        bool(
            (com_atlas[f"ctx_atlas_{ultima}"] == esperado_atlas + (len(J.ATLAS_COLS) - 1)).all()
        ),
    )
    cols_atlas = [f"ctx_atlas_{c}" for c in J.ATLAS_COLS]
    pos = conhecido[conhecido["id_municipio"] == POS_2010[0]]
    checar(
        "Atlas: município pós-2010 fica nulo, mas mantém o resto do contexto",
        bool(
            len(pos) > 0
            and pos[cols_atlas].isna().all().all()
            and pos["ctx_ibge_area_km2"].notna().all()
            and pos[J.COL_NSE_MUNICIPIO].notna().any()
        ),
        f"{len(pos)} linhas, {len(cols_atlas)} colunas ctx_atlas_ nulas",
    )

    # 8. FUNDEB: ano corrente, sem cruzar município com UF, e 2023 SEM PROXY
    com_nse = conhecido[conhecido["ano"].isin(ANOS_NSE)]
    checar(
        f"FUNDEB: {J.COL_NSE_MUNICIPIO} == ano + 0.7 (ano corrente, sem lag)",
        bool((com_nse[J.COL_NSE_MUNICIPIO] == com_nse["ano"].astype("float64") + 0.7).all()),
    )
    checar(
        f"FUNDEB: {J.COL_NSE_UF} == ano + 0.3 (município e UF não se cruzaram)",
        bool((com_nse[J.COL_NSE_UF] == com_nse["ano"].astype("float64") + 0.3).all()),
    )
    checar(
        "FUNDEB: ponderador chegou nas duas colunas certas",
        bool(
            (
                com_nse["ctx_fundeb_ponderador_nse_municipio"]
                == com_nse["ano"].astype("float64") + 0.07
            ).all()
            and (
                com_nse["ctx_fundeb_ponderador_nse_uf"]
                == com_nse["ano"].astype("float64") + 0.03
            ).all()
        ),
    )
    sem_nse = conhecido[~conhecido["ano"].isin(ANOS_NSE)]
    cols_nse = [c for c in base.columns if c.startswith("ctx_fundeb_")]
    checar(
        "FUNDEB: 2023 nulo, sem proxy",
        bool(len(sem_nse) > 0 and sem_nse[cols_nse].isna().all().all()),
        f"{len(sem_nse)} linhas, {len(cols_nse)} colunas ctx_fundeb_",
    )
    checar(
        "FUNDEB: nenhuma coluna de flag de proxy sobrou",
        not [c for c in base.columns if "proxy" in c],
    )

    # 9. left join preservou o município órfão, com contexto nulo
    orfao = base[base["id_municipio"] == ORFAO[0]]
    ctx = [c for c in base.columns if c.startswith("ctx_")]
    checar(
        "município sem contexto sobrevive com ctx_* nulo",
        bool(len(orfao) > 0 and orfao[ctx].isna().all().all()),
        f"{len(orfao)} linhas, {len(ctx)} colunas ctx_*",
    )

    # 10. os DOIS alvos continuam intactos
    #
    # A regressão de 06/09/2026 foi exatamente esta: label_proficiencia entrou na
    # gold/aluno e a base_analitica ficou sem ela, porque nada aqui exigia a
    # coluna. Conferir só o rótulo deixa o segundo alvo cair em silêncio.
    for alvo in (ALVO_CLASSIFICACAO, ALVO_REGRESSAO):
        checar(
            f"{alvo} sobreviveu ao join sem nulos",
            bool(alvo in base.columns and base[alvo].notna().all()),
            "coluna ausente" if alvo not in base.columns else "",
        )

    # ... e continuam sendo a mesma medição em duas escalas: se o join
    # embaralhasse linhas, a identidade quebraria antes do nulo aparecer.
    if ALVO_REGRESSAO in base.columns:
        checar(
            "os dois alvos seguem coerentes (rótulo == nota >= corte)",
            bool(
                (
                    base[ALVO_CLASSIFICACAO].astype("Int64")
                    == (base[ALVO_REGRESSAO] >= CORTE_PROFICIENCIA).astype("Int64")
                ).all()
            ),
        )
    return falhas


def conferir_guard(raiz: Path) -> list[str]:
    """Controle negativo: reintroduzir o proxy tem de parar o pipeline.

    É a regressão da decisão de 06/09/2026 — NSE é medição de período, e
    carregar 2024 para trás inventa um ponto da série.
    """
    falhas: list[str] = []
    print("\n=== Controle negativo ===")

    alunos = read_parquet(raiz / "aluno" / "ano=2023")
    original = J._preparar_nse_municipio

    def com_proxy(nse: pd.DataFrame) -> pd.DataFrame:
        base = original(nse)
        proxy = base.loc[base["ano"] == min(ANOS_NSE)].copy()
        proxy["ano"] = 2023
        return pd.concat([base, proxy], ignore_index=True)

    J._preparar_nse_municipio = com_proxy
    try:
        J.join_fundeb(alunos)
        print("  [FALHA] guard não acusou o proxy 2023 <- 2024")
        falhas.append("guard do proxy do FUNDEB")
    except AssertionError as erro:
        print(f"  [OK  ] guard acusou o proxy 2023 <- 2024 — {erro}")
    finally:
        J._preparar_nse_municipio = original
    return falhas


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        J.PROCESSED_DATA_DIR = raiz
        montar(raiz)
        J.run_join()
        base = read_parquet(raiz / J.ENTIDADE_DESTINO)

        falhas = conferir(base) + conferir_guard(raiz)

        print()
        if falhas:
            raise SystemExit(f"FALHAS: {falhas}")
        ctx = [c for c in base.columns if c.startswith("ctx_")]
        print(
            f"Todas as conferências passaram. base_analitica: "
            f"{len(base):,} linhas x {base.shape[1]} colunas ({len(ctx)} de contexto)"
        )


if __name__ == "__main__":
    main()
