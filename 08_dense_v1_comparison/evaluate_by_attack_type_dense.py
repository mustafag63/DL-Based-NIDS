"""
Repeat 06_attack_type_analysis's single-attack-type and pairwise attack-type
evaluations on the Dense autoencoder v1 (full_features, 5 seeds) instead of
the clean-only VAE -- inference only, no retraining.

Does not reimplement any evaluation logic: imports assemble_labeled_features_df(),
load_feature_cols(), evaluate_group() from
06_attack_type_analysis/evaluate_by_attack_type.py verbatim, and passes
dense_backend.DEFAULT_DENSE_BACKEND (this folder's model loading/threshold
logic, itself carried over from analysis/attack_type_breakdown_evaluation.py)
as the `backend` argument -- the same functions that already do this for the
VAE just run against a different model.

Uses the SAME test_with_attack_type.csv (06_attack_type_analysis) and the
same feature reconstruction (row_index -> features_all_windows.csv +
resampled-window features), since Dense v1 consumes the same "_scaled"
feature columns with no separate scaler (see dense_backend.py's docstring).

Writes:
  results_single_attack_type_dense.csv / .md
  results_pairwise_attack_type_dense.csv / .md
"""
import itertools
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_TYPE_DIR = os.path.join(os.path.dirname(HERE), "06_attack_type_analysis")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, HERE)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend import DEFAULT_DENSE_BACKEND, MODEL_LABEL, MODEL_DIR_DESC  # noqa: E402

SINGLE_RESULTS_CSV = os.path.join(HERE, "results_single_attack_type_dense.csv")
SINGLE_RESULTS_MD = os.path.join(HERE, "results_single_attack_type_dense.md")
PAIRWISE_RESULTS_CSV = os.path.join(HERE, "results_pairwise_attack_type_dense.csv")
PAIRWISE_RESULTS_MD = os.path.join(HERE, "results_pairwise_attack_type_dense.md")

PAIRS = list(itertools.combinations(single.ATTACK_TYPES, 2))


def pair_name(pair):
    return "+".join(pair)


def summarize(per_seed_df, group_col_name):
    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary = summary.reset_index().rename(columns={"attack_type": group_col_name})
    return summary


def write_md(path, title, col_header, summary, n_seeds):
    lines = [
        f"# {title}",
        "",
        f"Model: `{MODEL_DIR_DESC}` ({n_seeds} seeds, threshold_95 = 95th percentile of val-benign "
        "reconstruction error per seed, inference only, no retraining).",
        "",
        f"| {col_header} | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    key_col = summary.columns[0]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r[key_col]} | {int(r['n_benign'])} | {int(r['n_attack'])} | "
            f"{r['roc_auc_mean']:.4f} +/- {r['roc_auc_std']:.4f} | "
            f"{r['pr_auc_mean']:.4f} +/- {r['pr_auc_std']:.4f} | "
            f"{r['f1_mean']:.4f} +/- {r['f1_std']:.4f} | "
            f"{r['benign_fpr_mean']:.4f} +/- {r['benign_fpr_std']:.4f} | "
            f"{r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} |"
        )
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {path}")


def main():
    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)
    backend = DEFAULT_DENSE_BACKEND
    n_seeds = len(backend.seeds)

    # --- single attack type ---
    single_rows = []
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        single_rows.extend(single.evaluate_group(subset, feature_cols, attack_type, backend=backend))
    single_per_seed = pd.DataFrame(single_rows)
    single_summary = summarize(single_per_seed, "attack_type")
    single_summary.to_csv(SINGLE_RESULTS_CSV, index=False)
    print(f"Wrote {SINGLE_RESULTS_CSV}")
    write_md(
        SINGLE_RESULTS_MD, f"{MODEL_LABEL}, evaluated per attack type", "attack_type",
        single_summary, n_seeds,
    )

    # --- pairwise attack type combinations ---
    pairwise_rows = []
    for pair in PAIRS:
        name = pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        pairwise_rows.extend(single.evaluate_group(subset, feature_cols, name, backend=backend))
    pairwise_per_seed = pd.DataFrame(pairwise_rows)
    pairwise_summary = summarize(pairwise_per_seed, "attack_type_pair")
    order = {pair_name(p): i for i, p in enumerate(PAIRS)}
    pairwise_summary["_order"] = pairwise_summary["attack_type_pair"].map(order)
    pairwise_summary = pairwise_summary.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    pairwise_summary.to_csv(PAIRWISE_RESULTS_CSV, index=False)
    print(f"Wrote {PAIRWISE_RESULTS_CSV}")
    write_md(
        PAIRWISE_RESULTS_MD, f"{MODEL_LABEL}, evaluated per pairwise attack-type combination",
        "attack_type_pair", pairwise_summary, n_seeds,
    )


if __name__ == "__main__":
    main()
