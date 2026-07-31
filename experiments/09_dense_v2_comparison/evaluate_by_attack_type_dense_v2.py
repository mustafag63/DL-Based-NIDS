"""
STAGE 1 scope: single_attack_type evaluation ONLY, Dense v2 ONLY (pairwise
and VAE v2 are later stages, not run here per the phased-rollout plan).

Reuses evaluate_group() from 06_attack_type_analysis/evaluate_by_attack_type.py
verbatim (imported, not reimplemented) -- same test_with_attack_type.csv
labels, same per-seed threshold_95 convention -- but features are looked up
against the v2 (19-feature) table instead of the v1 (18-feature) one, via
dense_backend_v2.load_feature_cols_v2()/build_combined_features_v2().

Writes: results_single_attack_type_dense_v2.csv / .md
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, HERE)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import (  # noqa: E402
    DEFAULT_DENSE_V2_BACKEND, MODEL_LABEL, MODEL_DIR_DESC,
    load_feature_cols_v2, build_combined_features_v2,
)

RESULTS_CSV = os.path.join(HERE, "results_single_attack_type_dense_v2.csv")
RESULTS_MD = os.path.join(HERE, "results_single_attack_type_dense_v2.md")


def assemble_labeled_features_df_v2(feature_cols):
    """Same row_index/window_id/ts/is_attack agreement check as
    single.assemble_labeled_features_df, against the v2 feature table."""
    labeled = pd.read_csv(single.LABELED_TEST_PATH)
    combined = build_combined_features_v2()
    features = combined.loc[labeled["row_index"].values, feature_cols].reset_index(drop=True)
    check_cols = combined.loc[labeled["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check_cols["window_id"].values == labeled["window_id"].values).all()
    assert np.allclose(check_cols["ts"].values, labeled["ts"].values)
    assert (check_cols["is_attack"].values == labeled["is_attack"].values).all()
    df = pd.concat([labeled.reset_index(drop=True), features], axis=1)
    print(f"Assembled v2 eval frame: {len(df)} rows, {len(feature_cols)} feature columns.")
    return df


def summarize(per_seed_df):
    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    return summary.reset_index()


def write_md(path, summary, n_seeds):
    lines = [
        f"# {MODEL_LABEL}, evaluated per attack type",
        "",
        f"Model: `{MODEL_DIR_DESC}` ({n_seeds} seeds, threshold_95 = 95th percentile of val-benign "
        "reconstruction error per seed, inference only, no retraining).",
        "",
        "| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['attack_type']} | {int(r['n_benign'])} | {int(r['n_attack'])} | "
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
    feature_cols = load_feature_cols_v2()
    df = assemble_labeled_features_df_v2(feature_cols)
    backend = DEFAULT_DENSE_V2_BACKEND
    n_seeds = len(backend.seeds)

    rows = []
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        rows.extend(single.evaluate_group(subset, feature_cols, attack_type, backend=backend))
    per_seed = pd.DataFrame(rows)
    per_seed.to_csv(RESULTS_CSV.replace(".csv", "_per_seed.csv"), index=False)
    summary = summarize(per_seed)
    summary.to_csv(RESULTS_CSV, index=False)
    write_md(RESULTS_MD, summary, n_seeds)


if __name__ == "__main__":
    main()
