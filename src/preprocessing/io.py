"""Local Parquet I/O helpers (Hive-style partitions, pandas)."""

from __future__ import annotations

from pathlib import Path
import shutil

import pandas as pd


def apply_schema(df: pd.DataFrame, schema: list[tuple[str, str]]) -> pd.DataFrame:
    """Select contracted columns by name and cast to equivalent pandas dtypes."""
    nomes = [n for n, _ in schema]
    faltando = [n for n in nomes if n not in df.columns]
    if faltando:
        raise AssertionError(f"sem colunas do contrato: {faltando}")

    out = pd.DataFrame(index=df.index)
    for name, spark_type in schema:
        col = df[name]
        if spark_type == "int":
            out[name] = pd.to_numeric(col, errors="coerce").astype("Int64")
        elif spark_type == "double":
            out[name] = pd.to_numeric(col, errors="coerce")
        else:
            text = col.astype("string").str.strip()
            out[name] = text.mask(text.isin(["", "-", "- "]))
    return out


def write_parquet_partitioned(
    df: pd.DataFrame,
    path: Path,
    partition_col: str,
    overwrite_entity: bool = False,
) -> None:
    """Write ``df`` as Hive-style ``col=value/part.parquet`` partitions."""
    path = Path(path)
    if overwrite_entity and path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)

    if df.empty:
        return

    for key, part in df.groupby(partition_col, dropna=False, sort=False):
        if pd.isna(key):
            continue
        try:
            key = int(key)
        except TypeError, ValueError:
            pass
        part_dir = path / f"{partition_col}={key}"
        if part_dir.exists():
            shutil.rmtree(part_dir)
        part_dir.mkdir(parents=True)
        part.to_parquet(part_dir / "part.parquet", index=False)


def read_parquet(path: Path) -> pd.DataFrame:
    """Read a parquet file or a directory of partitioned parquet files."""
    path = Path(path)
    if path.is_file():
        return pd.read_parquet(path)
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Nenhum parquet em {path}")
    frames = [pd.read_parquet(f) for f in files]
    return pd.concat(frames, ignore_index=True)


def list_partition_values(path: Path, partition_col: str) -> set[int]:
    """Return integer partition keys present as ``col=value`` directories."""
    path = Path(path)
    if not path.exists():
        return set()
    values: set[int] = set()
    for child in path.iterdir():
        if child.is_dir() and child.name.startswith(f"{partition_col}="):
            raw = child.name.split("=", 1)[1]
            try:
                values.add(int(raw))
            except ValueError:
                continue
    return values
