"""Gera o gráfico Top 10 da Q2 a partir dos escores já publicados no notebook.

Não retreina o modelo — só plota valores congelados do ranking 2025.
Paleta alinhada aos slides (fundo transparente).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.config import PROJ_ROOT

# Cores dos slides (01 / 02)
COR_TEXTO = "#e2e8f0"
COR_MUTED = "#94a3b8"
COR_BARRA = "#38bdf8"
COR_LABEL = "#fbbf24"
COR_EIXO = "#475569"

# Ranking nominal Q2 (teste temporal 2025) — saída do notebook de classificação.
TOP10_Q2 = [
    ("Jardim de Angicos (RN)", 0.995),
    ("Curralinho (PA)", 0.995),
    ("Melgaço (PA)", 0.995),
    ("Lagoa d'Anta (RN)", 0.992),
    ("Paraú (RN)", 0.992),
    ("Triunfo Potiguar (RN)", 0.991),
    ("Eirunepé (AM)", 0.989),
    ("Envira (AM)", 0.989),
    ("Japi (RN)", 0.989),
    ("Ruy Barbosa (RN)", 0.989),
]

DEFAULT_OUTPUT = PROJ_ROOT / "images" / "q2_top10.png"


def plot_q2_top10(output_path: Path = DEFAULT_OUTPUT) -> Path:
    nomes, scores = zip(*reversed(TOP10_Q2))

    fig, ax = plt.subplots(figsize=(8, 5), facecolor="none")
    ax.set_facecolor("none")

    bars = ax.barh(nomes, scores, color=COR_BARRA, height=0.65, zorder=2)
    ax.set_xlim(0.97, 1.0)
    ax.set_xlabel("Probabilidade de risco", color=COR_MUTED, fontsize=11)
    ax.set_title(
        "Q2 — Top 10 municípios (2025)",
        color=COR_TEXTO,
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    ax.bar_label(bars, fmt="%.3f", padding=4, fontsize=9, color=COR_LABEL)

    ax.tick_params(axis="x", colors=COR_MUTED)
    ax.tick_params(axis="y", colors=COR_TEXTO)
    for spine in ax.spines.values():
        spine.set_color(COR_EIXO)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, color=COR_EIXO, linestyle="--", linewidth=0.6, alpha=0.7, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        dpi=150,
        bbox_inches="tight",
        facecolor="none",
        edgecolor="none",
        transparent=True,
    )
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    path = plot_q2_top10()
    print(f"Gráfico salvo em: {path}")
