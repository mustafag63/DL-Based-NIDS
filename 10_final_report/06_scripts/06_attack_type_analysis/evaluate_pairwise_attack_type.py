"""
Break down the clean-only (0% train contamination) VAE's test-set detection
performance for the 3 pairwise attack_type combinations (apache_bench +
slowloris, slowloris + portscan, apache_bench + portscan), using the
attack_type labels derived in derive_attack_type_labels.py
(06_attack_type_analysis/test_with_attack_type.csv).

Does not reimplement anything -- imports assemble_labeled_features_df(),
load_feature_cols(), evaluate_group(), ATTACK_TYPES and SEEDS directly from
evaluate_by_attack_type.py, so the model loading / threshold_95 / metric
logic (and therefore the numbers) are identical to the single-attack-type
run. Inference only, no retraining.

For each pair, the evaluation set is: all test-split benign flows + both
attack types' attack flows; the third (excluded) attack type's flows are
dropped from that run entirely, same exclusion rule as the single-type runs.

Writes 06_attack_type_analysis/results_pairwise_attack_type.csv and .md, plus
a combined single-vs-pairwise comparison table at
06_attack_type_analysis/results_combined.md.
"""
import itertools
import os

import pandas as pd

import evaluate_by_attack_type as single  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

RESULTS_CSV = os.path.join(HERE, "results_pairwise_attack_type.csv")
RESULTS_MD = os.path.join(HERE, "results_pairwise_attack_type.md")
COMBINED_MD = os.path.join(HERE, "results_combined.md")

PAIRS = list(itertools.combinations(single.ATTACK_TYPES, 2))  # 3 pairs from the 3 types


def pair_name(pair):
    return "+".join(pair)


def main():
    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)

    all_rows = []
    for pair in PAIRS:
        name = pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        all_rows.extend(single.evaluate_group(subset, feature_cols, name))

    per_seed_df = pd.DataFrame(all_rows)

    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.reset_index().rename(columns={"attack_type": "attack_type_pair"})
    # keep the 3 pairs in a fixed, readable order rather than groupby's alphabetical one
    order = {pair_name(p): i for i, p in enumerate(PAIRS)}
    summary["_order"] = summary["attack_type_pair"].map(order)
    summary = summary.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    summary.to_csv(RESULTS_CSV, index=False)
    print(f"\nWrote {RESULTS_CSV}")

    lines = [
        "# Clean-only (0% contamination) VAE, evaluated per pairwise attack-type combination",
        "",
        f"Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` "
        f"({len(single.SEEDS)} seeds, threshold_95 per seed, inference only, no retraining).",
        "",
        "Each row = both listed attack types' flows vs. the full test-split benign set "
        f"(the third attack type is excluded from that run). Mean +/- std across {len(single.SEEDS)} seeds.",
        "",
        "| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |",
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
    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {RESULTS_MD}")

    subtype_recall_cols = [c for c in per_seed_df.columns if c.startswith("recall__")]
    subtype_summary = per_seed_df.groupby("attack_type")[subtype_recall_cols].agg(["mean", "std"])
    subtype_summary.columns = [f"{col}_{stat}" for col, stat in subtype_summary.columns]
    subtype_summary = subtype_summary.reset_index().rename(columns={"attack_type": "attack_type_pair"})

    write_combined_table(single, summary, subtype_summary)


def write_combined_table(single, pairwise_summary, subtype_summary):
    single_df = pd.read_csv(single.RESULTS_CSV)

    def fmt(row):
        return (
            f"{row['roc_auc_mean']:.4f} +/- {row['roc_auc_std']:.4f}",
            f"{row['pr_auc_mean']:.4f} +/- {row['pr_auc_std']:.4f}",
            f"{row['f1_mean']:.4f} +/- {row['f1_std']:.4f}",
            f"{row['attack_recall_mean']:.4f} +/- {row['attack_recall_std']:.4f}",
        )

    lines = [
        "# Single vs. pairwise attack-type evaluation (clean-only VAE, contam_0pct)",
        "",
        "Combines results_single_attack_type.md and results_pairwise_attack_type.md into "
        "one table, so each attack type's solo performance can be read next to its "
        "performance when a second attack type shares the evaluation set (both compared "
        "against the same fixed benign pool; the non-participating attack type is excluded "
        "from each run, never present as unlabeled noise).",
        "",
        "| evaluation set | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in single_df.iterrows():
        roc, pr, f1, rec = fmt(r)
        lines.append(f"| {r['attack_type']} (solo) | {int(r['n_benign'])} | {int(r['n_attack'])} | {roc} | {pr} | {f1} | {rec} |")
    for _, r in pairwise_summary.iterrows():
        roc, pr, f1, rec = fmt(r)
        lines.append(f"| {r['attack_type_pair']} (pair) | {int(r['n_benign'])} | {int(r['n_attack'])} | {roc} | {pr} | {f1} | {rec} |")

    lines += [
        "",
        "## apache_bench recall: solo vs. paired",
        "",
        "Two different numbers, both included because they answer different questions:",
        "",
        "- **pooled recall (pair)**: fraction of ALL attack flows in that pair's mixed evaluation "
        "set that get flagged. Moves mechanically with the mix (e.g. adding well-detected "
        "portscan flows pulls the pooled number up) even if no individual apache_bench flow's "
        "detection outcome changes -- it is not a measure of apache_bench detectability by itself.",
        "- **apache_bench-only recall (pair)**: recall computed using only the apache_bench flows "
        "inside that pair's evaluation set, at the same model/threshold. Since detection is a "
        "per-flow decision (errors > thr95) that does not depend on which other flows share the "
        "test set, this is expected to match the solo number exactly (up to seed-sampling noise "
        "from the VAE's stochastic reparameterization) -- it is here to make that point explicit, "
        "not because pairing is expected to change it.",
        "",
        "| evaluation set | pooled recall (pair) | apache_bench-only recall (pair) |",
        "|---|---|---|",
    ]
    ab_solo = single_df[single_df["attack_type"] == "apache_bench"].iloc[0]
    lines.append(
        f"| apache_bench (solo) | -- | {ab_solo['attack_recall_mean']:.4f} +/- {ab_solo['attack_recall_std']:.4f} |"
    )
    for _, r in pairwise_summary.iterrows():
        if "apache_bench" in r["attack_type_pair"]:
            sub_row = subtype_summary[subtype_summary["attack_type_pair"] == r["attack_type_pair"]]
            ab_col_mean = "recall__apache_bench_mean"
            ab_col_std = "recall__apache_bench_std"
            ab_only = (
                f"{sub_row.iloc[0][ab_col_mean]:.4f} +/- {sub_row.iloc[0][ab_col_std]:.4f}"
                if not sub_row.empty and ab_col_mean in sub_row.columns else "n/a"
            )
            lines.append(
                f"| {r['attack_type_pair']} (pair) | {r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} | {ab_only} |"
            )

    with open(COMBINED_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {COMBINED_MD}")


if __name__ == "__main__":
    main()
