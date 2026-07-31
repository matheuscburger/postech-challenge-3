from pathlib import Path

import pandas as pd


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a tabular dataset from CSV or Parquet."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file format: {suffix} ({path})")
