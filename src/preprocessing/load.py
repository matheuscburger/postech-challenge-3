"""Load CSV or partitioned Parquet datasets from the data lake folders."""

from pathlib import Path

import pandas as pd

from src.preprocessing.io import read_parquet


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a tabular dataset from CSV or Parquet (file or directory)."""
    path = Path(path)
    if path.is_dir():
        return read_parquet(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file format: {suffix or path} ({path})")
