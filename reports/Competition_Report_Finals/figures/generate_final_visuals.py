#!/usr/bin/env python3
"""Generate deterministic, publication-grade figures for the finals report."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "generated"
RESULTS = ROOT.parents[1] / "docs/macos_test_notes/2026-08-12/finals-results.json"

BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
PURPLE = "#CC79A7"
SKY = "#56B4E9"
GRAY = "#6B7280"


def setup() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial Unicode MS", "Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.7,
            "grid.color": "#D1D5DB",
            "grid.linewidth": 0.45,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf", dpi=300, pad_inches=0.03)
    fig.savefig(OUT / f"{name}.png", dpi=300, pad_inches=0.03)
    plt.close(fig)


def annotated_heatmap(ax: plt.Axes, values: np.ndarray, rows: list[str], cols: list[str], annotations: np.ndarray, title: str) -> None:
    norm = TwoSlopeNorm(vmin=min(-0.85, float(values.min())), vcenter=0.0, vmax=max(2.2, float(values.max())))
    image = ax.imshow(values, cmap="RdYlGn", norm=norm, aspect="auto")
    ax.set_xticks(range(len(cols)), cols, fontweight="bold")
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title(title, loc="left", fontweight="bold", pad=9)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            color = "white" if abs(values[i, j]) > 1.1 else "#111827"
            ax.text(j, i, annotations[i, j], ha="center", va="center", color=color, fontweight="bold", fontsize=8)
    ax.set_xticks(np.arange(-0.5, len(cols), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.figure.colorbar(image, ax=ax, fraction=0.035, pad=0.025, label="relative effect")


def rk_main() -> None:
    rows = ["3 GiB baseline", "3 GiB SLIM-ARC", "2.5 GiB SLIM-ARC"]
    absolute = np.array([[3.85, 0.70], [4.40, 2.21], [4.19, 2.12]])
    relative = np.array([[0.0, 0.0], [4.40 / 3.85 - 1, 2.21 / 0.70 - 1], [4.19 / 3.85 - 1, 2.12 / 0.70 - 1]])
    annotations = np.array([[f"{absolute[i, j]:.2f}\n{relative[i, j]:+.0%}" for j in range(2)] for i in range(3)])
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.5), gridspec_kw={"width_ratios": [1.15, 1]})
    annotated_heatmap(axes[0], relative, rows, ["Prefill", "Decode"], annotations, "(a) Throughput under the 3 GiB contract")
    x = np.arange(2)
    axes[1].plot(x, absolute[0], "o--", color=GRAY, lw=1.8, ms=7, label="baseline")
    axes[1].plot(x, absolute[1], "o-", color=GREEN, lw=2.6, ms=8, label="SLIM-ARC")
    for k, label in enumerate(["1.14×", "3.16×"]):
        axes[1].annotate(label, (x[k], absolute[1, k]), xytext=(0, 10), textcoords="offset points", ha="center", color=GREEN, fontweight="bold")
    axes[1].set_xticks(x, ["Prefill", "Decode"])
    axes[1].set_ylabel("token/s (log scale)")
    axes[1].set_yscale("log")
    axes[1].set_ylim(0.5, 6.0)
    axes[1].grid(axis="y")
    axes[1].legend(frameon=False, loc="upper right")
    axes[1].set_title("(b) Paired baseline-to-system response", loc="left", fontweight="bold", pad=9)
    fig.tight_layout(w_pad=2.0)
    save(fig, "rk3588_3g_main")


def rk_dynamic() -> None:
    strategies = ["Static RANDOM", "Disabled ref.", "Prefill SEQ", "Decode SEQ", "Decode NORMAL", "Dynamic all-SEQ"]
    values = np.array([[0.44, 0.26], [2.74, 1.41], [2.82, 0.25], [2.81, 1.35], [2.57, 1.41], [2.84, 1.40]])
    normalized = values / values[1] - 1
    ann = np.array([[f"{values[i,j]:.2f}\n{values[i,j]/values[1,j]:.2f}×" for j in range(2)] for i in range(6)])
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.25), gridspec_kw={"width_ratios": [1.15, 1]})
    annotated_heatmap(axes[0], normalized, strategies, ["Prefill", "Decode"], ann, "(a) Strategy-response matrix")
    axes[1].axhspan(0.95, 1.05, color=GREEN, alpha=0.12, label="within ±5% of reference")
    idx = np.arange(len(strategies))
    axes[1].plot(idx, values[:, 0] / values[1, 0], "o-", color=BLUE, lw=2, label="Prefill / ref.")
    axes[1].plot(idx, values[:, 1] / values[1, 1], "s-", color=ORANGE, lw=2, label="Decode / ref.")
    axes[1].set_xticks(idx, ["RND", "off", "P-SEQ", "D-SEQ", "D-NORM", "all-SEQ"], rotation=25, ha="right")
    axes[1].set_ylabel("normalized throughput")
    axes[1].set_ylim(0, 1.15)
    axes[1].grid(axis="y")
    axes[1].legend(frameon=False, loc="lower right")
    axes[1].set_title("(b) Recovery trajectory by phase", loc="left", fontweight="bold", pad=9)
    fig.tight_layout(w_pad=2.0)
    save(fig, "rk3588_dynamic_policy")


def cross_device() -> None:
    rows = ["WSL 8 GiB", "RK 3 GiB", "RK 2.5 GiB", "Mac reclaim cold", "Pi A28 vs A24", "HiDev A24 vs baseline"]
    data = np.array([[13.6, 437.5, np.nan, np.nan], [14.3, 215.7, np.nan, np.nan], [7.3, 15.7, np.nan, np.nan], [np.nan, 6.3, 4.4, 0], [1.5, 14.2, 6.6, np.nan], [-0.1, -6.1, -3.7, np.nan]])
    masked = np.ma.masked_invalid(data)
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.1), gridspec_kw={"width_ratios": [1.25, 1]})
    norm = mpl.colors.SymLogNorm(linthresh=10, linscale=0.8, vmin=-20, vmax=450)
    cmap = mpl.colormaps["RdYlGn"].copy()
    cmap.set_bad("#F3F4F6")
    image = axes[0].imshow(masked, cmap=cmap, norm=norm, aspect="auto")
    axes[0].set_xticks(range(4), ["Prefill ↑", "Decode ↑", "Wall ↓", "RSS ↓"], fontweight="bold")
    axes[0].set_yticks(range(len(rows)), rows)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            axes[0].text(j, i, "—" if np.isnan(data[i,j]) else f"{data[i,j]:+.1f}%", ha="center", va="center", fontsize=8, fontweight="bold")
    axes[0].set_title("(a) Same-contract effect matrix", loc="left", fontweight="bold")
    fig.colorbar(image, ax=axes[0], fraction=0.035, pad=0.025, label="beneficial relative change (%)")
    effect = data[:, 1]
    y = np.arange(len(rows))
    colors = [GREEN if v >= 0 else RED for v in effect]
    axes[1].axvline(0, color="#111827", lw=0.8)
    axes[1].hlines(y, 0, effect, color=colors, lw=2)
    axes[1].scatter(effect, y, c=colors, s=np.clip(np.abs(effect), 20, 140), edgecolor="white", linewidth=0.7, zorder=3)
    axes[1].set_yticks(y, rows)
    axes[1].invert_yaxis()
    axes[1].set_xscale("symlog", linthresh=10)
    axes[1].set_xlim(-20, 650)
    for value, position in zip(effect, y):
        axes[1].annotate(f"{value:+.1f}%", (value, position), xytext=(5 if value >= 0 else -5, -8), textcoords="offset points", ha="left" if value >= 0 else "right", fontsize=7)
    axes[1].set_xlabel("Decode effect (%) — symlog")
    axes[1].grid(axis="x")
    axes[1].set_title("(b) Decode-effect forest", loc="left", fontweight="bold")
    fig.tight_layout(w_pad=2.2)
    save(fig, "cross_device_effects")


def ablation_dashboard() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.25))
    names = ["temporal", "spatial", "confidence", "conf.+budget", "popular-16"]
    hit = [34.9, 4.5, 55.35, 54.0, 19.31]
    y0 = np.arange(len(names))
    colors = [BLUE, GRAY, GREEN, SKY, RED]
    axes[0].hlines(y0, 0, hit, color=colors, lw=3, alpha=0.65)
    axes[0].scatter(hit, y0, s=[70, 55, 120, 130, 150], c=colors, edgecolor="white", lw=0.8, zorder=3)
    axes[0].set_yticks(y0, names)
    axes[0].invert_yaxis()
    axes[0].annotate("12.1 GB issued", (55.35, 2), xytext=(-4, 10), textcoords="offset points", ha="right", fontsize=7, color=GREEN)
    axes[0].annotate("72.6 GB issued", (19.31, 4), xytext=(4, -13), textcoords="offset points", fontsize=7, color=RED)
    axes[0].set_xlabel("expert hit rate (%)")
    axes[0].set_title("(a) Prediction hit rate and I/O", loc="left", fontweight="bold")
    axes[0].grid(axis="x")
    labels = ["FA auto", "FA off", "KV q4_0"]
    decode = [6.90, 3.49, 5.05]
    y = np.arange(3)
    axes[1].hlines(y, 0, decode, color=[GREEN, RED, ORANGE], lw=4, alpha=0.65)
    axes[1].scatter(decode, y, c=[GREEN, RED, ORANGE], s=80, zorder=3)
    axes[1].set_yticks(y, labels)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Decode token/s")
    axes[1].set_title("(b) Attention / KV path", loc="left", fontweight="bold")
    axes[1].grid(axis="x")
    reject = ["Self-draft", "expert RANDOM", "Pi LFRU", "NTFS3 mmap"]
    effects = [-53.2, -67.3, -1.5, -65.7]
    yy = np.arange(4)
    axes[2].axvline(0, color="#111827", lw=0.8)
    axes[2].hlines(yy, effects, 0, color=RED, lw=3, alpha=0.75)
    axes[2].scatter(effects, yy, color=RED, s=70)
    axes[2].set_yticks(yy, reject)
    axes[2].invert_yaxis()
    axes[2].set_xlabel("end-to-end regression (%)")
    axes[2].set_title("(c) Rejected optimizations", loc="left", fontweight="bold")
    axes[2].grid(axis="x")
    fig.tight_layout(w_pad=2.0)
    save(fig, "ablation_dashboard")


def implementation_map() -> None:
    fig, ax = plt.subplots(figsize=(10.6, 4.6))
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 6.1)
    ax.axis("off")
    boxes = [
        (0.25, 4.7, 2.1, 0.9, "llama-model.cpp\nmodel-owned runtime", BLUE),
        (2.8, 4.7, 2.1, 0.9, "slim-arc-runtime\nlease + lifetime", PURPLE),
        (5.35, 4.7, 2.1, 0.9, "unified-scheduler\nphase + pressure", ORANGE),
        (7.9, 4.7, 2.35, 0.9, "slim-arc-prefetch\nqueue + token ledger", GREEN),
        (0.55, 2.5, 2.15, 1.1, "page-range\ninterior aligned pages", SKY),
        (3.15, 2.5, 2.15, 1.1, "expert-reclaim\nplan DONTNEED", RED),
        (5.75, 2.5, 2.15, 1.1, "expert-residency\npressure policy", PURPLE),
        (8.35, 2.5, 1.85, 1.1, "KV eviction\nwindow + sink", ORANGE),
        (2.25, 0.45, 2.4, 0.95, "apply-slim-arc.py\nidempotent patch seam", GRAY),
        (6.0, 0.45, 2.4, 0.95, "macOS harness\ncgroup + provenance", GRAY),
    ]
    for x, y, w, h, label, color in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08", facecolor=mpl.colors.to_rgba(color, 0.10), edgecolor=color, lw=1.5))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontweight="bold", fontsize=9)
    arrows = [((2.35, 5.15), (2.8, 5.15)), ((4.9, 5.15), (5.35, 5.15)), ((7.45, 5.15), (7.9, 5.15)), ((9.05, 4.7), (1.65, 3.6)), ((9.05, 4.7), (4.2, 3.6)), ((9.05, 4.7), (6.8, 3.6)), ((9.05, 4.7), (9.25, 3.6)), ((3.45, 1.4), (1.65, 2.5)), ((3.45, 1.4), (4.2, 2.5)), ((3.45, 1.4), (6.8, 2.5)), ((7.2, 1.4), (6.4, 4.7))]
    for start, end in arrows:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=10, lw=1.0, color="#4B5563", connectionstyle="arc3,rad=0.05"))
    ax.text(0.25, 5.9, "Concrete source ownership and integration flow", fontsize=12, fontweight="bold")
    ax.text(0.25, 0.05, "Solid arrows: ownership/call path    Upward arrows: patching and experiment control", color=GRAY, fontsize=8)
    save(fig, "implementation_module_map")


def main() -> None:
    setup()
    with RESULTS.open(encoding="utf-8") as stream:
        json.load(stream)
    rk_main()
    rk_dynamic()
    cross_device()
    ablation_dashboard()
    implementation_map()


if __name__ == "__main__":
    main()
