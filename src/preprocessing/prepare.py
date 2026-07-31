from pathlib import Path

from loguru import logger
from tqdm import tqdm
import typer

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.preprocessing.load import load_dataset

app = typer.Typer()


@app.command()
def main(
    input_path: Path = RAW_DATA_DIR / "dataset.csv",
    output_path: Path = PROCESSED_DATA_DIR / "dataset.csv",
):
    """Load raw data and persist a processed dataset for modeling/EDA.

    Feature transforms (imputation, encoding, scaling) belong in
    ``build_preprocessor`` and should run inside the sklearn Pipeline at
    train time — not as a separate offline features.csv step.
    """
    logger.info(f"Loading dataset from {input_path}...")
    if input_path.exists():
        df = load_dataset(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.success(f"Wrote processed dataset to {output_path} ({len(df)} rows).")
    else:
        logger.warning(f"Input not found: {input_path}. Running stub prepare...")
        for i in tqdm(range(10), total=10):
            if i == 5:
                logger.info("Something happened for iteration 5.")
        logger.success("Processing dataset complete (stub).")


if __name__ == "__main__":
    app()
