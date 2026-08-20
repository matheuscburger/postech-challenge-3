"""Declarative data-quality checks ported from the Glue Silver/Gold jobs."""

from __future__ import annotations

import re

from loguru import logger
import pandas as pd

from src.config import ANOS, CORTE_PROFICIENCIA

ANOS_ESPERADOS = list(ANOS)


class DataQualityError(RuntimeError):
    """Raised when a critical data-quality check fails."""


def _violations_expr(df: pd.DataFrame, nome: str) -> pd.Series:
    if nome == "rede_uf_invalida":
        return df["rede"].isna() | (df["rede"] != 5)
    if nome == "rede_municipio_invalida":
        return df["rede"].isna() | (df["rede"] != 3)
    if nome == "dependencia_administrativa_invalida":
        return df["dependencia_administrativa"].isna() | ~df["dependencia_administrativa"].isin(
            [2, 3]
        )
    if nome == "meta_ausente_em_ano_alvo":
        return df["ano"].isin([2024, 2025]) & df["meta"].isna()
    if nome == "atingiu_meta_incoerente":
        previsto = (df["taxa_alfabetizacao"] - df["meta"]) >= 0
        return df["meta"].notna() & (previsto != df["atingiu_meta"])
    if nome == "label_incoerente_com_corte":
        return (df["proficiencia"] >= CORTE_PROFICIENCIA) != (df["label_alfabetizado"] == 1)
    raise ValueError(f"Expressão de qualidade desconhecida: {nome}")


def checar_qualidade(entidade: str, df: pd.DataFrame, checks: list[dict], camada: str) -> float:
    logger.info("[DQ:{}] {} | iniciando | checks={}", camada, entidade, len(checks))

    referenciadas: set[str] = set()
    for check in checks:
        col = check.get("coluna")
        if isinstance(col, list):
            referenciadas.update(col)
        elif col:
            referenciadas.add(col)
    ausentes = referenciadas - set(df.columns)
    if ausentes:
        raise ValueError(
            f"[DQ:{camada}] {entidade}: coluna(s) do check ausente(s) no schema -> "
            f"{sorted(ausentes)} | schema: {list(df.columns)}"
        )

    total = len(df)
    passou = falhou = criticos = 0

    for check in checks:
        tipo = check["tipo"]
        coluna = check.get("coluna")
        valor = check.get("valor")
        critico = check.get("critico", True)
        ok = False
        detalhe = ""

        if tipo == "min_count":
            ok = total >= valor
            detalhe = f"contagem={total} | minimo={valor}"
        elif tipo == "not_null":
            nulos = int(df[coluna].isna().sum())
            ok = nulos == 0
            detalhe = f"{nulos} nulos"
        elif tipo == "unique":
            cols = coluna if isinstance(coluna, list) else [coluna]
            dups = int(df.duplicated(cols).sum())
            ok = dups == 0
            detalhe = f"{dups} duplicatas (chave={cols})"
        elif tipo == "range":
            mn, mx = valor
            col = df[coluna]
            naonulos = int(col.notna().sum())
            fora = int(((col < mn) | (col > mx)).fillna(False).sum())
            if total > 0 and naonulos == 0:
                ok = False
                detalhe = f"coluna 100% nula ({total} linhas)"
            else:
                ok = fora == 0
                detalhe = f"{fora} fora de [{mn},{mx}] | nulos={total - naonulos}"
        elif tipo == "anos":
            presentes = set(pd.to_numeric(df[coluna], errors="coerce").dropna().astype(int))
            faltando = set(valor) - presentes
            ok = len(faltando) == 0
            detalhe = f"faltando={sorted(faltando)} | presentes={sorted(presentes)}"
        elif tipo == "regex":
            padrao = re.compile(valor)
            texto = df[coluna].astype("string")
            invalidos = int((texto.notna() & ~texto.str.match(padrao, na=False)).sum())
            ok = invalidos == 0
            detalhe = f"{invalidos} fora do padrão '{valor}'"
        elif tipo == "expr":
            violacoes = int(_violations_expr(df, check["nome"]).fillna(False).sum())
            ok = violacoes == 0
            detalhe = f"{violacoes} violações ({check['nome']})"
        else:
            raise ValueError(f"Tipo de check desconhecido: {tipo}")

        status = "PASS" if ok else ("FAIL" if critico else "WARN")
        logger.info(
            "[DQ:{}] {:4} | {:9} | {} | {}",
            camada,
            status,
            tipo,
            coluna if coluna else "-",
            detalhe,
        )
        if ok:
            passou += 1
        else:
            falhou += 1
            criticos += int(critico)

    score = round(passou / len(checks) * 100, 1) if checks else 100.0
    logger.info(
        "[DQ:{}] {} | Score={}% | PASS={} FAIL={}", camada, entidade, score, passou, falhou
    )
    if criticos > 0:
        raise DataQualityError(
            f"[DQ:{camada}] {entidade}: {criticos} check(s) critico(s) falharam. "
            "Pipeline interrompido."
        )
    return score


CHECKS_SILVER = {
    "meta_alfabetizacao_brasil": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "meta_alfabetizacao_uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "sigla_uf", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "meta_alfabetizacao_municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
    ],
    "uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_uf", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_uf", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "media_portugues", "valor": (0, 1000), "critico": False},
        {"tipo": "expr", "nome": "rede_uf_invalida", "critico": True},
    ],
    "municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "not_null", "coluna": "rede", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio", "rede"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "media_portugues", "valor": (0, 1000), "critico": False},
        {"tipo": "expr", "nome": "rede_municipio_invalida", "critico": True},
    ],
    "alunos": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_aluno", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "regex", "coluna": "id_municipio", "valor": r"^[0-9]{7}$", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_aluno"], "critico": True},
        {"tipo": "range", "coluna": "proficiencia", "valor": (0, 1500), "critico": False},
        {"tipo": "expr", "nome": "dependencia_administrativa_invalida", "critico": True},
    ],
}

CHECKS_GOLD = {
    "indicadores_municipio": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "id_municipio", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_municipio"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "meta", "valor": (0, 100), "critico": False},
        {"tipo": "expr", "nome": "meta_ausente_em_ano_alvo", "critico": False},
        {
            "tipo": "range",
            "coluna": "percentual_participacao",
            "valor": (0, 100),
            "critico": False,
        },
        {"tipo": "expr", "nome": "atingiu_meta_incoerente", "critico": True},
    ],
    "indicadores_uf": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "sigla_uf", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "sigla_uf"], "critico": True},
        {"tipo": "range", "coluna": "taxa_alfabetizacao", "valor": (0, 100), "critico": False},
        {"tipo": "range", "coluna": "meta", "valor": (0, 100), "critico": False},
        {"tipo": "expr", "nome": "meta_ausente_em_ano_alvo", "critico": False},
        {
            "tipo": "range",
            "coluna": "percentual_participacao",
            "valor": (0, 100),
            "critico": False,
        },
        {"tipo": "expr", "nome": "atingiu_meta_incoerente", "critico": True},
    ],
    "aluno_contexto": [
        {"tipo": "min_count", "valor": 1, "critico": True},
        {"tipo": "anos", "coluna": "ano", "valor": ANOS_ESPERADOS, "critico": True},
        {"tipo": "not_null", "coluna": "id_aluno", "critico": True},
        {"tipo": "not_null", "coluna": "ano", "critico": True},
        {"tipo": "not_null", "coluna": "proficiencia", "critico": True},
        {"tipo": "not_null", "coluna": "label_alfabetizado", "critico": True},
        {"tipo": "unique", "coluna": ["ano", "id_aluno"], "critico": True},
        {"tipo": "range", "coluna": "proficiencia", "valor": (0, 1500), "critico": False},
        {"tipo": "expr", "nome": "label_incoerente_com_corte", "critico": True},
    ],
}
