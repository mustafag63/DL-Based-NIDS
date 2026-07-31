"""
STAGE 3: pairwise attack-type evaluation for the v2 (19-feature,
+concurrency_src_1s) models, generic over backend so it runs for both
Dense v2 and VAE v2 without duplicating logic (mirrors
06_attack_type_analysis/evaluate_pairwise_attack_type.py's structure, but
generic-backend the way 08_dense_v1_comparison/evaluate_by_attack_type_dense.py
reuses single.evaluate_group() instead of hardcoding one model).

For each pair, evaluation set = benign + both listed attack types (third
type excluded). Decomposed (per-constituent-type) recall comes from
evaluate_group()'s recall__<type> columns -- NOT pooled -- so apache_bench's
own recall within a pair can be read directly, same distinction v1's combined
table makes explicit.
"""
import itertools
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DENSE_V2_DIR = os.path.join(PROJECT_ROOT, "09_dense_v2_comparison")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_V2_DIR)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2  # noqa: E402
from evaluate_by_attack_type_dense_v2 import assemble_labeled_features_df_v2  # noqa: E402

PAIRS = list(itertools.combinations(single.ATTACK_TYPES, 2))


def pair_name(pair):
    return "+".join(pair)


def run_pairwise_v2(backend, model_label, model_dir_desc, out_dir, single_results_csv):
    os.makedirs(out_dir, exist_ok=True)
    feature_cols = load_feature_cols_v2()
    df = assemble_labeled_features_df_v2(feature_cols)

    all_rows = []
    for pair in PAIRS:
        name = pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        all_rows.extend(single.evaluate_group(subset, feature_cols, name, backend=backend))
    per_seed_df = pd.DataFrame(all_rows)
    per_seed_df.to_csv(os.path.join(out_dir, "results_per_seed.csv"), index=False)

    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary = summary.reset_index().rename(columns={"attack_type": "attack_type_pair"})
    order = {pair_name(p): i for i, p in enumerate(PAIRS)}
    summary["_order"] = summary["attack_type_pair"].map(order)
    summary = summary.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    results_csv = os.path.join(out_dir, "results.csv")
    summary.to_csv(results_csv, index=False)
    print(f"Wrote {results_csv}")

    n_seeds = len(list(backend.seeds))
    lines = [
        f"# {model_label}, evaluated per pairwise attack-type combination",
        "",
        f"Model: `{model_dir_desc}` ({n_seeds} seeds, threshold_95 per seed, inference only, no retraining).",
        "",
        "Each row = both listed attack types' flows vs. the full test-split benign set "
        f"(the third attack type is excluded from that run). Mean +/- std across {n_seeds} seeds.",
        "",
        "| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95, pooled) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['attack_type_pair']} | {int(r['n_benign'])} | {int(r['n_attack'])} | "
            f"{r['roc_auc_mean']:.4f} +/- {r['roc_auc_std']:.4f} | "
            f"{r['pr_auc_mean']:.4f} +/- {r['pr_auc_std']:.4f} | "
            f"{r['f1_mean']:.4f} +/- {r['f1_std']:.4f} | "
            f"{r['benign_fpr_mean']:.4f} +/- {r['benign_fpr_std']:.4f} | "
            f"{r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} |"
        )

    subtype_recall_cols = [c for c in per_seed_df.columns if c.startswith("recall__")]
    subtype_summary = per_seed_df.groupby("attack_type")[subtype_recall_cols].agg(["mean", "std"])
    subtype_summary.columns = [f"{c}_{s}" for c, s in subtype_summary.columns]
    subtype_summary = subtype_summary.reset_index().rename(columns={"attack_type": "attack_type_pair"})
    subtype_summary.to_csv(os.path.join(out_dir, "decomposed_recall.csv"), index=False)

    single_df = pd.read_csv(single_results_csv)
    ab_solo = single_df[single_df["attack_type"] == "apache_bench"].iloc[0]
    lines += [
        "",
        "## apache_bench decomposed (own-flows-only) recall: solo vs. paired",
        "",
        "Per-flow decision (errors > thr95) does not depend on which other flows share the "
        "eval set, so apache_bench's own recall is expected to match the solo number up to "
        "seed-sampling noise -- checked explicitly here, not assumed.",
        "",
        "| evaluation set | apache_bench-only recall |",
        "|---|---|",
        f"| apache_bench (solo) | {ab_solo['attack_recall_mean']:.4f} +/- {ab_solo['attack_recall_std']:.4f} |",
    ]
    for pair in PAIRS:
        if "apache_bench" in pair:
            name = pair_name(pair)
            sub_row = subtype_summary[subtype_summary["attack_type_pair"] == name]
            if not sub_row.empty and "recall__apache_bench_mean" in sub_row.columns:
                ab_only = (f"{sub_row.iloc[0]['recall__apache_bench_mean']:.4f} +/- "
                          f"{sub_row.iloc[0]['recall__apache_bench_std']:.4f}")
            else:
                ab_only = "n/a"
            lines.append(f"| {name} (pair) | {ab_only} |")

    results_md = os.path.join(out_dir, "results.md")
    with open(results_md, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {results_md}")
    return summary, subtype_summary


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "10_vae_v2_comparison"))
    from dense_backend_v2 import DEFAULT_DENSE_V2_BACKEND, MODEL_LABEL as DENSE_LABEL, MODEL_DIR_DESC as DENSE_DESC  # noqa: E402
    from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND, MODEL_LABEL as VAE_LABEL, MODEL_DIR_DESC as VAE_DESC  # noqa: E402

    print("=== Dense v2 (5 seeds) ===")
    run_pairwise_v2(
        DEFAULT_DENSE_V2_BACKEND, DENSE_LABEL, DENSE_DESC,
        os.path.join(HERE, "dense_v2"),
        os.path.join(DENSE_V2_DIR, "results_single_attack_type_dense_v2.csv"),
    )
    print("\n=== VAE v2 (5 seeds, deterministic z_mean) ===")
    run_pairwise_v2(
        DEFAULT_VAE_V2_BACKEND, VAE_LABEL, VAE_DESC,
        os.path.join(HERE, "vae"),
        os.path.join(PROJECT_ROOT, "10_vae_v2_comparison", "results_single_attack_type_vae_v2.csv"),
    )
    print("done")
