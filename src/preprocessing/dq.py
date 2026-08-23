"""Shared declarative data-quality engine for Medallion pipelines."""

from __future__ import annotations

from collections.abc import Callable
import re

from loguru import logger
import pandas as pd


class DataQualityError(RuntimeError):
    """Raised when a critical data-quality check fails."""


ViolationsExpr = Callable[[pd.DataFrame, str], pd.Series]


def checar_qualidade(
    entidade: str,
    df: pd.DataFrame,
    checks: list[dict],
    camada: str,
    *,
    violations_expr: ViolationsExpr | None = None,
) -> float:
    """Run declarative checks; raise ``DataQualityError`` on critical failures."""
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
            if violations_expr is None:
                raise ValueError(
                    f"[DQ:{camada}] {entidade}: check expr '{check.get('nome')}' "
                    "sem violations_expr"
                )
            violacoes = int(violations_expr(df, check["nome"]).fillna(False).sum())
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
