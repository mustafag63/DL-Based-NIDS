"""
STAGE 3 scope: report figures for pairwise_attack_type v2 (Dense v2 + VAE v2,
both 19-feature / +concurrency_src_1s). Reuses build_02_pairwise.py's figure
layout (pooled_recall.png, decomposed_recall.png) but reads directly from the
already-computed results_per_seed.csv in each v2 output dir instead of
re-running inference -- the numbers already exist, only the plots are new.

Writes into 10_final_report/02_pairwise_attack_type/{dense,vae}/, alongside
the existing results.md/.csv/decomposed_recall.csv.
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "02_pairwise_attack_type")

PAIR_ORDER = ["portscan+apache_bench", "portscan+slowloris", "apache_bench+slowloris"]


def make_figures(model_name, out_dir, color):
    per_seed = pd.read_csv(os.path.join(out_dir, "results_per_seed.csv"))
    n_seeds = per_seed["seed"].nunique()

    # --- pooled recall figure ---
    pooled = per_seed.groupby("attack_type")["attack_recall"].agg(["mean", "std"])
    pooled = pooled.loc[PAIR_ORDER]
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    bars = ax.bar(pooled.index, pooled["mean"], yerr=pooled["std"], capsize=6, color=color, width=0.55)
    for b, v in zip(bars, pooled["mean"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.3f}", ha="center", fontsize=12)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Pooled Attack Recall @ threshold_95")
    ax.set_xlabel("Attack-type pair (evaluation set = benign + both types)")
    ax.set_title(f"Pooled Attack Recall by Pair — {model_name} ({n_seeds} seeds)")
    plt.setp(ax.get_xticklabels(), rotation=8)
    fig.tight_layout()
    pooled_path = os.path.join(out_dir, "pooled_recall.png")
    fig.savefig(pooled_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {pooled_path}")

    # --- decomposed (per-type-within-pair) recall figure ---
    recall_cols = [c for c in per_seed.columns if c.startswith("recall__")]
    decomposed = per_seed.groupby("attack_type")[recall_cols].agg(["mean", "std"])
    decomposed.columns = [f"{c}_{s}" for c, s in decomposed.columns]
    decomposed = decomposed.loc[PAIR_ORDER]

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    x = np.arange(len(PAIR_ORDER))
    width = 0.35
    seen_labels = set()
    for i, pair_name in enumerate(PAIR_ORDER):
        types_in_pair = sorted(
            t for t in ("apache_bench", "portscan", "slowloris")
            if not pd.isna(decomposed.loc[pair_name, f"recall__{t}_mean"])
        )
        offsets = np.linspace(-width / 2, width / 2, len(types_in_pair)) if len(types_in_pair) > 1 else [0]
        for off, t in zip(offsets, types_in_pair):
            v = decomposed.loc[pair_name, f"recall__{t}_mean"]
            e = decomposed.loc[pair_name, f"recall__{t}_std"]
            label = t if t not in seen_labels else None
            seen_labels.add(t)
            ax.bar(x[i] + off, v, width / max(len(types_in_pair), 1) * 0.9, yerr=e, capsize=4,
                   color=sty.COLOR_TYPE[t], label=label)
            ax.text(x[i] + off, v + 0.03, f"{v:.2f}", ha="center", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(PAIR_ORDER, rotation=8)
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("Per-Type Recall @ threshold_95")
    ax.set_xlabel("Attack-type pair (each bar: that type's own flows, within the pair's eval set)")
    ax.set_title(f"Decomposed Per-Type Recall Within Each Pair — {model_name} ({n_seeds} seeds)")
    ax.legend(frameon=False, loc="upper right", ncol=3)
    fig.tight_layout()
    decomposed_path = os.path.join(out_dir, "decomposed_recall.png")
    fig.savefig(decomposed_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {decomposed_path}")


def append_image_refs(out_dir):
    md_path = os.path.join(out_dir, "results.md")
    with open(md_path) as f:
        content = f.read()
    marker = "![Pooled recall]"
    if marker in content:
        return  # already linked
    content = content.rstrip("\n") + (
        "\n\n"
        "![Pooled recall](pooled_recall.png)\n\n"
        "![Decomposed recall](decomposed_recall.png)\n"
    )
    with open(md_path, "w") as f:
        f.write(content)
    print(f"  linked PNGs into {md_path}")


print("=== Dense v2 (5 seeds, pairwise) ===")
make_figures("Dense v2", os.path.join(OUT_ROOT, "dense"), sty.COLOR_DENSE)
append_image_refs(os.path.join(OUT_ROOT, "dense"))

print("=== VAE v2 (5 seeds, pairwise) ===")
make_figures("VAE v2", os.path.join(OUT_ROOT, "vae"), sty.COLOR_VAE)
append_image_refs(os.path.join(OUT_ROOT, "vae"))
print("done (Stage 3: pairwise v2 figures)")
