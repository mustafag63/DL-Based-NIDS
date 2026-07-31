"""
Dedup sanity check for audit finding O3 (11_fable_review/independent_audit.md):
faz2's post-hoc leakage fix forces every resampled-window row into the same
split as its byte-identical source-window twin, so the test set contains BOTH
copies of the same real flow -- 2356 of test_with_attack_type.csv's 9931 rows
(1393 benign + 963 attack = 31.0% of attack rows) are resampled duplicates.
That double-counts flows in the metrics: n_benign/n_attack are inflated and
seed-to-seed stds are artificially tight. It is NOT train->test leakage (the
twins sit on the same side of the split); this check quantifies whether the
double-counting moves any reported number.

DEDUP RULE: drop ALL rows whose window_id starts with "window_resampled";
keep the real-window original (its row_index, i.e. the source flow's own
features/label). Verified before dropping, and asserted in code:
  - every resampled row has a ts-matched real-window twin in this same file
    (2356/2356 -- resampled copies keep the source flow's original ts), and
  - twin pairs agree on is_attack and attack_type (0 mismatches),
so dropping the resampled side removes exactly the duplicate copies and
nothing else. The deduplicated table is written next to the results as
dedup_test_with_attack_type.csv.

EVALUATION: identical to the canonical deterministic run
(run_zmean_rescore.py) in every respect except the eval set -- same 20
contam_0pct models, same z_mean deterministic score, same per-seed
threshold_95 recomputed on val_benign.csv, same evaluate_group() metric code.
No retraining. The canonical (non-dedup) results.csv is NOT touched; outputs
go to 01_single_attack_type/vae/dedup_sanity_check/ only, including a
side-by-side dedup-vs-canonical comparison with deltas and a verdict
(threshold: |delta| < 0.02 on ROC-AUC/F1/recall => "duplicates only inflated
n, results unchanged").
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402

OUT_DIR = os.path.join(REPORT_DIR, "01_single_attack_type", "vae", "dedup_sanity_check")
DEDUP_CSV = os.path.join(OUT_DIR, "dedup_test_with_attack_type.csv")
RESULTS_CSV = os.path.join(OUT_DIR, "results_dedup.csv")
RESULTS_MD = os.path.join(OUT_DIR, "results_dedup.md")
CANONICAL_CSV = os.path.join(REPORT_DIR, "01_single_attack_type", "vae", "results.csv")

DELTA_THRESHOLD = 0.02
# Split by what a delta would MEAN. Rank/threshold metrics depend only on
# per-flow scores and decisions -- if duplicates changed model behavior, it
# shows up here. PR-AUC and F1 additionally depend on the benign:attack
# prevalence of the eval set BY DEFINITION, and dedup changes that mix
# (removes 20% of benign rows but 31% of attack rows), so these can move
# mechanically even when every per-flow decision is identical.
BEHAVIOR_METRICS = ["roc_auc", "benign_fpr", "attack_recall"]
PREVALENCE_METRICS = ["pr_auc", "f1"]
COMPARE_METRICS = ["roc_auc", "pr_auc", "f1", "benign_fpr", "attack_recall"]


def build_dedup_table():
    labeled = pd.read_csv(single.LABELED_TEST_PATH)
    is_resampled = labeled["window_id"].str.startswith("window_resampled")
    res, real = labeled[is_resampled], labeled[~is_resampled]

    # Safety: dropping a resampled row must be dropping a *duplicate*, i.e.
    # its ts-twin (resampled copies keep the source flow's original ts) must
    # be present among the real-window rows of this same file, with matching
    # labels. Both held (2356/2356, 0 mismatches) when this was written.
    twin = res.merge(real[["ts", "is_attack", "attack_type"]], on="ts",
                     how="left", suffixes=("", "_twin"))
    assert twin["is_attack_twin"].notna().all(), \
        "resampled row without a real-window ts-twin in test -- dedup rule would lose a unique flow"
    assert (twin["is_attack"] == twin["is_attack_twin"]).all()
    assert (twin["attack_type"] == twin["attack_type_twin"]).all()

    print(f"Dedup: dropping {len(res)} resampled rows "
          f"({int(res['is_attack'].sum())} attack = "
          f"{100 * res['is_attack'].sum() / labeled['is_attack'].sum():.1f}% of attack rows, "
          f"{int((res['is_attack'] == 0).sum())} benign); keeping {len(real)} real-window rows.")
    real = real.reset_index(drop=True)
    real.to_csv(DEDUP_CSV, index=False)
    print(f"Wrote {DEDUP_CSV}")
    return real


def attach_features(labeled, feature_cols):
    # Same row_index feature lookup + agreement checks as
    # single.assemble_labeled_features_df(), applied to the dedup table.
    combined = single.build_combined_features()
    features = combined.loc[labeled["row_index"].values, feature_cols].reset_index(drop=True)
    check = combined.loc[labeled["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check["window_id"].values == labeled["window_id"].values).all()
    assert np.allclose(check["ts"].values, labeled["ts"].values)
    assert (check["is_attack"].values == labeled["is_attack"].values).all()
    return pd.concat([labeled.reset_index(drop=True), features], axis=1)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    feature_cols = single.load_feature_cols()
    df = attach_features(build_dedup_table(), feature_cols)
    backend = single.VAEBackend(deterministic=True)

    all_rows = []
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        all_rows.extend(single.evaluate_group(subset, feature_cols, attack_type, backend=backend))
    per_seed = pd.DataFrame(all_rows)

    summary = per_seed.groupby(["attack_type", "n_benign", "n_attack"])[COMPARE_METRICS].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary = summary.reset_index()
    summary.to_csv(RESULTS_CSV, index=False)
    print(f"\nWrote {RESULTS_CSV}")

    canonical = pd.read_csv(CANONICAL_CSV).set_index("attack_type")
    dedup = summary.set_index("attack_type")

    n_seeds = len(list(backend.seeds))
    lines = [
        "# Dedup sanity check — clean-only VAE (contam_0pct), deterministic z_mean, per attack type",
        "",
        "Audit finding **O3**: the test set contains both the source-window copy and the "
        "resampled-window copy of the same real flow (2356/9931 rows; 963 = 31.0% of attack "
        "rows), double-counting those flows in the metrics. **Dedup rule:** drop every "
        "`window_resampled_*` row, keep the real-window original (asserted: every dropped row "
        "has a ts-matched, label-identical real-window twin in this same test set, so nothing "
        "unique is lost). Dedup table: `dedup_test_with_attack_type.csv` (this folder).",
        "",
        f"Everything else is identical to the canonical deterministic run (`../results.csv`): "
        f"same {n_seeds} seeds, z_mean scoring, per-seed threshold_95 recomputed on val-benign, "
        "no retraining. This is a sanity check only — the canonical results are unchanged.",
        "",
        "## Dedup results",
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

    lines += [
        "",
        "## Comparison vs. canonical (non-dedup) deterministic results",
        "",
        "| attack_type | metric | canonical (dup) | dedup | delta |",
        "|---|---|---|---|---|",
    ]
    max_behavior_delta = 0.0
    max_prevalence_delta = 0.0
    for attack_type in single.ATTACK_TYPES:
        c, d = canonical.loc[attack_type], dedup.loc[attack_type]
        lines.append(f"| {attack_type} | n_benign / n_attack | {int(c['n_benign'])} / {int(c['n_attack'])} "
                     f"| {int(d['n_benign'])} / {int(d['n_attack'])} | "
                     f"-{int(c['n_benign']) - int(d['n_benign'])} / -{int(c['n_attack']) - int(d['n_attack'])} |")
        for m in COMPARE_METRICS:
            delta = float(d[f"{m}_mean"] - c[f"{m}_mean"])
            if m in BEHAVIOR_METRICS:
                max_behavior_delta = max(max_behavior_delta, abs(delta))
            else:
                max_prevalence_delta = max(max_prevalence_delta, abs(delta))
            tag = " (prevalence-sensitive)" if m in PREVALENCE_METRICS else ""
            lines.append(f"| {attack_type} | {m}{tag} | {c[f'{m}_mean']:.4f} +/- {c[f'{m}_std']:.4f} "
                         f"| {d[f'{m}_mean']:.4f} +/- {d[f'{m}_std']:.4f} | {delta:+.4f} |")

    lines += ["", "## Verdict", ""]
    lines.append(
        f"Max |delta|, behavior metrics (ROC-AUC / recall / FPR — depend only on per-flow "
        f"scores and decisions): **{max_behavior_delta:.4f}**. "
        f"Max |delta|, prevalence-sensitive metrics (PR-AUC / F1 — depend on the eval set's "
        f"benign:attack mix by definition): **{max_prevalence_delta:.4f}**. "
        f"Threshold: {DELTA_THRESHOLD}.")
    lines.append("")
    if max_behavior_delta < DELTA_THRESHOLD:
        lines.append(
            "Behavior metrics are practically identical with and without the duplicates: "
            "**the resampled copies were not changing the model's per-flow results — they only "
            "inflated n_benign/n_attack** (and made seed stds look tighter than the number of "
            "independent flows justifies)."
        )
        if max_prevalence_delta >= DELTA_THRESHOLD:
            lines.append(
                "\nPR-AUC/F1 do move past the threshold, but this is the *mechanical* effect of "
                "dedup changing the benign:attack prevalence these metrics are defined on "
                "(dedup removes ~20% of benign rows vs. ~31% of attack rows), not a change in "
                "model behavior — the recall/FPR rows above show the per-flow decisions are the "
                "same. If dedup numbers are adopted for reporting, PR-AUC/F1 should be quoted "
                "from the dedup set (its prevalence reflects distinct real flows); if the "
                "canonical numbers stand, the dedup n values give the true distinct-flow counts."
            )
    else:
        lines.append(
            f"Behavior metrics differ by >= {DELTA_THRESHOLD}: dedup materially changes "
            "per-flow results — see the rows above with the largest deltas. Which version to "
            "treat as canonical is a reporting decision (left to the project owner); the dedup "
            "set is the statistically cleaner basis since each real flow is counted once."
        )
    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {RESULTS_MD}")
    print(f"\nMax |delta|: behavior={max_behavior_delta:.4f}, "
          f"prevalence-sensitive={max_prevalence_delta:.4f} (threshold {DELTA_THRESHOLD})")


if __name__ == "__main__":
    main()
