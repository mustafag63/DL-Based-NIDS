"""
Regenerate the VAE figures in 10_final_report/01_single_attack_type/vae/ and
02_pairwise_attack_type/vae/ with the DETERMINISTIC z_mean score (audit finding
O2; see run_zmean_rescore.py in this directory for the scoring/threshold
details). Figure logic mirrors report_generation/build_01_single.py and
build_02_pairwise.py, with two deliberate differences:

  - backend = VAEBackend(deterministic=True) instead of the stochastic default
  - report_style is imported from its committed location
    (06_scripts/report_generation/), not the long-gone scratchpad path the
    original build scripts hardcoded

Outputs use the SAME canonical filenames as before (roc_pr_<type>.png,
pooled_recall.png, decomposed_recall.png, decomposed_recall.csv); the old
stochastic versions live untouched in each vae/_stochastic_legacy/. Dense v1
figures are not touched (Dense scoring was always deterministic).

HYBRID PANELS (dedup prevalence correction, matching the hybrid tables from
apply_dedup_prevalence_correction.py): in each roc_pr_<type>.png the ROC
panel is computed on the CANONICAL (non-dedup) set -- ROC is a behavior
metric, dedup moves it < 0.02 -- while the PR panel (curve AND the AP value)
is computed on the DEDUP set (dedup_sanity_check/dedup_test_with_attack_type.csv),
because PR/AP depend on the eval set's benign:attack prevalence and the
resampled duplicates distort it. The figure suptitle states which n each
panel comes from. Pairwise figures are recall-based (behavior metric) and
stay canonical-set only.

03_segmented_injection/vae/error_plot.png is not produced here -- it comes
from run_zmean_rescore.py's run_segmented_evaluation() call.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve, auc, precision_recall_curve, average_precision_score

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

sys.path.insert(0, os.path.join(REPORT_DIR, "06_scripts", "report_generation"))
sys.path.insert(0, ATTACK_TYPE_DIR)
import report_style as sty  # noqa: E402
sty.apply()
import evaluate_by_attack_type as single  # noqa: E402
import evaluate_pairwise_attack_type as pairwise  # noqa: E402

SINGLE_OUT = os.path.join(REPORT_DIR, "01_single_attack_type", "vae")
PAIRWISE_OUT = os.path.join(REPORT_DIR, "02_pairwise_attack_type", "vae")

MODEL_NAME = "VAE"
SCORE_TAG = "deterministic z_mean"

feature_cols = single.load_feature_cols()
df = single.assemble_labeled_features_df(feature_cols)
backend = single.VAEBackend(deterministic=True)
n_seeds = len(list(backend.seeds))


def make_roc_pr_figure(attack_type, y_roc, err_roc, y_pr, err_pr, out_path):
    """ROC panel from the canonical set (y_roc/err_roc), PR panel from the
    dedup set (y_pr/err_pr) -- see module docstring."""
    fpr, tpr, _ = roc_curve(y_roc, err_roc)
    roc_auc = auc(fpr, tpr)
    prec, rec, _ = precision_recall_curve(y_pr, err_pr)
    pr_auc = average_precision_score(y_pr, err_pr)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    ax = axes[0]
    ax.plot(fpr, tpr, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AUC = {roc_auc:.3f}")
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.2, label="chance level")
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — {MODEL_NAME} — {attack_type}")
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    ax = axes[1]
    ax.plot(rec, prec, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AP = {pr_auc:.3f} (dedup)")
    baseline = float(y_pr.mean())
    ax.axhline(baseline, color="#999999", linestyle="--", linewidth=1.2,
               label=f"baseline (dedup prevalence = {baseline:.3f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title(f"Precision-Recall Curve — {MODEL_NAME} — {attack_type}")
    ax.legend(loc="upper right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    fig.suptitle(
        f"{MODEL_NAME} ({SCORE_TAG}) vs. benign — {attack_type}\n"
        f"ROC: kanonik set (n_attack={int(y_roc.sum())}, n_benign={int((y_roc == 0).sum())}), "
        f"PR: dedup set (n_attack={int(y_pr.sum())}, n_benign={int((y_pr == 0).sum())})"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}  (ROC-AUC={roc_auc:.4f} canonical, PR-AUC={pr_auc:.4f} dedup)")


def mean_errors_for(subset):
    X = subset[feature_cols].values.astype("float32")
    error_matrix, _ = single.compute_error_matrix(X, backend=backend)
    return subset["is_attack"].values, error_matrix.mean(axis=0)


def build_single_figures():
    print(f"=== 01_single_attack_type/vae ({SCORE_TAG}, {n_seeds} seeds, hybrid ROC/PR panels) ===")
    from run_dedup_sanity_check import attach_features, DEDUP_CSV
    dedup_df = attach_features(pd.read_csv(DEDUP_CSV), feature_cols)
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        subset_dedup = dedup_df[(dedup_df["is_attack"] == 0) | (dedup_df["attack_type"] == attack_type)].copy()
        y_roc, err_roc = mean_errors_for(subset)
        y_pr, err_pr = mean_errors_for(subset_dedup)
        make_roc_pr_figure(attack_type, y_roc, err_roc, y_pr, err_pr,
                           os.path.join(SINGLE_OUT, f"roc_pr_{attack_type}.png"))


def build_pairwise_figures():
    print(f"=== 02_pairwise_attack_type/vae ({SCORE_TAG}, {n_seeds} seeds) ===")
    all_rows = []
    for pair in pairwise.PAIRS:
        name = pairwise.pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        all_rows.extend(single.evaluate_group(subset, feature_cols, name, backend=backend))
    per_seed = pd.DataFrame(all_rows)
    pair_names = [pairwise.pair_name(p) for p in pairwise.PAIRS]

    # --- pooled recall figure ---
    pooled = per_seed.groupby("attack_type")["attack_recall"].agg(["mean", "std"]).loc[pair_names]
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    bars = ax.bar(pooled.index, pooled["mean"], yerr=pooled["std"], capsize=6,
                  color=sty.COLOR_VAE, width=0.55)
    for b, v in zip(bars, pooled["mean"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.3f}", ha="center", fontsize=12)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Pooled Attack Recall @ threshold_95")
    ax.set_xlabel("Attack-type pair (evaluation set = benign + both types)")
    ax.set_title(f"Pooled Attack Recall by Pair — {MODEL_NAME} ({n_seeds} seeds, {SCORE_TAG})")
    plt.setp(ax.get_xticklabels(), rotation=8)
    fig.tight_layout()
    pooled_path = os.path.join(PAIRWISE_OUT, "pooled_recall.png")
    fig.savefig(pooled_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {pooled_path}")

    # --- decomposed (per-type-within-pair) recall figure + csv ---
    recall_cols = [c for c in per_seed.columns if c.startswith("recall__")]
    decomposed = per_seed.groupby("attack_type")[recall_cols].agg(["mean", "std"])
    decomposed.columns = [f"{c}_{s}" for c, s in decomposed.columns]
    decomposed = decomposed.loc[pair_names]
    decomposed.to_csv(os.path.join(PAIRWISE_OUT, "decomposed_recall.csv"))
    print(f"  wrote {os.path.join(PAIRWISE_OUT, 'decomposed_recall.csv')}")

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    x = np.arange(len(pair_names))
    width = 0.35
    for i, name in enumerate(pair_names):
        types_in_pair = sorted(set(c.replace("recall__", "").replace("_mean", "")
                                   for c in decomposed.columns if c.endswith("_mean")
                                   and not pd.isna(decomposed.loc[name, c])))
        offsets = np.linspace(-width / 2, width / 2, len(types_in_pair)) if len(types_in_pair) > 1 else [0]
        for off, t in zip(offsets, types_in_pair):
            v = decomposed.loc[name, f"recall__{t}_mean"]
            e = decomposed.loc[name, f"recall__{t}_std"]
            ax.bar(x[i] + off, v, width / max(len(types_in_pair), 1) * 0.9, yerr=e, capsize=4,
                   color=sty.COLOR_TYPE[t],
                   label=t if t not in ax.get_legend_handles_labels()[1] else None)
            ax.text(x[i] + off, v + 0.03, f"{v:.2f}", ha="center", fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(pair_names, rotation=8)
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("Per-Type Recall @ threshold_95")
    ax.set_xlabel("Attack-type pair (each bar: that type's own flows, within the pair's eval set)")
    ax.set_title(f"Decomposed Per-Type Recall Within Each Pair — {MODEL_NAME} ({n_seeds} seeds, {SCORE_TAG})")
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), frameon=False, loc="upper right", ncol=3)
    fig.tight_layout()
    decomposed_path = os.path.join(PAIRWISE_OUT, "decomposed_recall.png")
    fig.savefig(decomposed_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {decomposed_path}")


if __name__ == "__main__":
    build_single_figures()
    build_pairwise_figures()
    print("done")
