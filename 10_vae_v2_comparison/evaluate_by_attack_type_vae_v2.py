"""
STAGE 2 scope: single_attack_type evaluation ONLY, VAE v2 ONLY (pairwise and
segmented v2 are Stage 3, not run here).

Reuses evaluate_group() from evaluate_by_attack_type.py verbatim; features
looked up against the v2 (19-feature) combined table via
09_dense_v2_comparison's assemble_labeled_features_df_v2 (same helper Dense
v2's single_attack_type eval used, re-imported not reimplemented).

Writes: results_single_attack_type_vae_v2.csv / .md
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DENSE_V2_DIR = os.path.join(PROJECT_ROOT, "09_dense_v2_comparison")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_V2_DIR)
sys.path.insert(0, HERE)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2  # noqa: E402
from evaluate_by_attack_type_dense_v2 import assemble_labeled_features_df_v2  # noqa: E402
from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND, MODEL_LABEL, MODEL_DIR_DESC  # noqa: E402

RESULTS_CSV = os.path.join(HERE, "results_single_attack_type_vae_v2.csv")
RESULTS_MD = os.path.join(HERE, "results_single_attack_type_vae_v2.md")


def summarize(per_seed_df):
    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    return summary.reset_index()


def write_md(path, summary, n_seeds):
    lines = [
        f"# {MODEL_LABEL}, evaluated per attack type",
        "",
        f"Model: `{MODEL_DIR_DESC}` ({n_seeds} seeds, threshold_95 = 95th percentile of "
        "DETERMINISTIC (z_mean) val-benign reconstruction error per seed, inference only).",
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
    backend = DEFAULT_VAE_V2_BACKEND
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
