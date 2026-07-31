import os, sys, shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, "/private/tmp/claude-501/-Users-mustafa-Desktop-NIDS-IDS-Project/27367645-50b6-4f4c-ad67-446d3fe33e07/scratchpad")
import report_style as sty
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DENSE_DIR = os.path.join(PROJECT_ROOT, "08_dense_v1_comparison")
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "02_pairwise_attack_type")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_DIR)
import evaluate_by_attack_type as single
import evaluate_pairwise_attack_type as pairwise
from dense_backend import DEFAULT_DENSE_BACKEND, MODEL_LABEL as DENSE_LABEL

feature_cols = single.load_feature_cols()
df = single.assemble_labeled_features_df(feature_cols)
PAIRS = pairwise.PAIRS


def run_model(model_name, backend, n_seeds, out_dir, pooled_csv_src, pooled_md_src):
    os.makedirs(out_dir, exist_ok=True)
    all_rows = []
    for pair in PAIRS:
        name = pairwise.pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        all_rows.extend(single.evaluate_group(subset, feature_cols, name, backend=backend))
    per_seed = pd.DataFrame(all_rows)

    # --- pooled recall figure ---
    pooled = per_seed.groupby("attack_type")["attack_recall"].agg(["mean", "std"])
    pooled = pooled.loc[[pairwise.pair_name(p) for p in PAIRS]]
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    bars = ax.bar(pooled.index, pooled["mean"], yerr=pooled["std"], capsize=6,
                   color=sty.COLOR_VAE if model_name == "VAE" else sty.COLOR_DENSE, width=0.55)
    for b, v in zip(bars, pooled["mean"]):
        ax.text(b.get_x() + b.get_width()/2, v + 0.03, f"{v:.3f}", ha="center", fontsize=12)
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
    decomposed = decomposed.loc[[pairwise.pair_name(p) for p in PAIRS]]
    decomposed.to_csv(os.path.join(out_dir, "decomposed_recall.csv"))

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    pairs_names = decomposed.index.tolist()
    x = np.arange(len(pairs_names))
    width = 0.35
    for i, pair_name in enumerate(pairs_names):
        types_in_pair = sorted(set(c.replace("recall__", "").replace("_mean", "")
                                    for c in decomposed.columns if c.endswith("_mean")
                                    and not pd.isna(decomposed.loc[pair_name, c])))
        offsets = np.linspace(-width/2, width/2, len(types_in_pair)) if len(types_in_pair) > 1 else [0]
        for off, t in zip(offsets, types_in_pair):
            v = decomposed.loc[pair_name, f"recall__{t}_mean"]
            e = decomposed.loc[pair_name, f"recall__{t}_std"]
            b = ax.bar(x[i] + off, v, width/max(len(types_in_pair), 1) * 0.9, yerr=e, capsize=4,
                       color=sty.COLOR_TYPE[t], label=t if i == 0 or t not in ax.get_legend_handles_labels()[1] else None)
            ax.text(x[i] + off, v + 0.03, f"{v:.2f}", ha="center", fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(pairs_names, rotation=8)
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("Per-Type Recall @ threshold_95")
    ax.set_xlabel("Attack-type pair (each bar: that type's own flows, within the pair's eval set)")
    ax.set_title(f"Decomposed Per-Type Recall Within Each Pair — {model_name} ({n_seeds} seeds)")
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), frameon=False, loc="upper right", ncol=3)
    fig.tight_layout()
    decomposed_path = os.path.join(out_dir, "decomposed_recall.png")
    fig.savefig(decomposed_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {decomposed_path}")

    shutil.copy(pooled_csv_src, os.path.join(out_dir, "results.csv"))
    shutil.copy(pooled_md_src, os.path.join(out_dir, "results.md"))
    print(f"  copied results.csv/.md into {out_dir}")


print("=== VAE (20 seeds) ===")
run_model("VAE", single.DEFAULT_BACKEND, len(single.SEEDS), os.path.join(OUT_ROOT, "vae"),
          pairwise.RESULTS_CSV, pairwise.RESULTS_MD)

print("=== Dense v1 (5 seeds) ===")
run_model(DENSE_LABEL, DEFAULT_DENSE_BACKEND, len(DEFAULT_DENSE_BACKEND.seeds), os.path.join(OUT_ROOT, "dense_v1"),
          os.path.join(DENSE_DIR, "results_pairwise_attack_type_dense.csv"),
          os.path.join(DENSE_DIR, "results_pairwise_attack_type_dense.md"))
print("done")
