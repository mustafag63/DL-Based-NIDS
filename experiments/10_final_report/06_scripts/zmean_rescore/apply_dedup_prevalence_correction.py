"""
Apply the dedup prevalence correction to the canonical VAE result files
(decision following the O3 dedup sanity check, see run_dedup_sanity_check.py):

  - recall / ROC-AUC / benign-FPR stay from the CANONICAL (non-dedup) test set:
    they are behavior metrics (per-flow scores/decisions only) and the sanity
    check verified dedup moves them by < 0.02 -- negligible.
  - PR-AUC / F1 are REPLACED with values computed on the DEDUP test set
    (dedup_sanity_check/dedup_test_with_attack_type.csv): both depend on the
    eval set's benign:attack prevalence by definition, and the resampled
    duplicates distort that prevalence (they are 20% of benign rows but 31%
    of attack rows); the dedup set's prevalence reflects distinct real flows.

Files rewritten (hybrid values + an explicit footnote naming which metric
comes from which set):
  01_single_attack_type/vae/results.csv + results.md
  02_pairwise_attack_type/vae/results.csv + results.md + results_combined.md
      (pairwise PR-AUC/F1 on the dedup set are computed here -- the dedup
      sanity check only ran the single-type evaluation)
  03_segmented_injection/vae/block_recall_f1.md -- NOT patched, only a note
      appended: that report has no PR-AUC, and its per-block F1 is computed
      inside all-attack segments (no benign rows in the block), where
      precision == 1 and F1 == 2r/(1+r) -- a pure function of recall, i.e. a
      behavior metric, not prevalence-sensitive. Duplicates there only
      inflate per-segment n.

The patched CSVs keep their original columns (pr_auc_*/f1_* now dedup-based)
plus two added columns, n_benign_dedup / n_attack_dedup, recording the
distinct-flow counts the PR-AUC/F1 values are based on. The pre-correction
deterministic values remain available in dedup_sanity_check/ (canonical side
of the comparison table) and in git history.
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, HERE)
import evaluate_by_attack_type as single  # noqa: E402
import evaluate_pairwise_attack_type as pairwise  # noqa: E402
from run_dedup_sanity_check import attach_features, DEDUP_CSV  # noqa: E402

SINGLE_DIR = os.path.join(REPORT_DIR, "01_single_attack_type", "vae")
PAIRWISE_DIR = os.path.join(REPORT_DIR, "02_pairwise_attack_type", "vae")
SEGMENTED_MD = os.path.join(REPORT_DIR, "03_segmented_injection", "vae", "block_recall_f1.md")
DEDUP_SINGLE_CSV = os.path.join(SINGLE_DIR, "dedup_sanity_check", "results_dedup.csv")

PREV_COLS = ["pr_auc_mean", "pr_auc_std", "f1_mean", "f1_std"]

SCORE_NOTE = (
    "**Scoring: deterministic z_mean** (reparameterization skipped at inference, "
    "z = z_mean -- no eps sample, no eval seed; audit finding O2). threshold_95 "
    "recomputed per seed as the 95th percentile of the deterministic error on the "
    "same held-out val-benign set (`05_contamination_sweep/01_data/val_benign.csv`), "
    "because the stored `threshold.json` values were calibrated on stochastic val "
    "errors and do not transfer. The original stochastic-scoring results live in "
    "`_stochastic_legacy/` next to this file; model weights identical, no retraining."
)


def footnote(n_line):
    return (
        "**Dipnot (PR-AUC / F1):** PR-AUC ve F1, tekrarlanan (resampled) flow "
        f"kopyalarının prevalans'ı çarpıtmasını önlemek için dedup edilmiş test setinden "
        f"({n_line}) hesaplanmıştır; recall/ROC-AUC/FPR davranış metrikleri olduğu için "
        "kanonik (dedup'suz) sette hesaplanmıştır — iki set arasında davranışsal fark "
        "<0.02 olduğu doğrulanmıştır (bkz. `dedup_sanity_check/` / "
        "`../01_single_attack_type/vae/dedup_sanity_check/`)."
    )


def metric_row(prefix, r):
    return (
        f"| {prefix} | "
        f"{r['roc_auc_mean']:.4f} +/- {r['roc_auc_std']:.4f} | "
        f"{r['pr_auc_mean']:.4f} +/- {r['pr_auc_std']:.4f} | "
        f"{r['f1_mean']:.4f} +/- {r['f1_std']:.4f} | "
        f"{r['benign_fpr_mean']:.4f} +/- {r['benign_fpr_std']:.4f} | "
        f"{r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} |"
    )


def patch_single():
    canonical = pd.read_csv(os.path.join(SINGLE_DIR, "results.csv"))
    dedup = pd.read_csv(DEDUP_SINGLE_CSV).set_index("attack_type")

    canonical = canonical.set_index("attack_type")
    for at in canonical.index:
        for c in PREV_COLS:
            canonical.loc[at, c] = dedup.loc[at, c]
        canonical.loc[at, "n_benign_dedup"] = int(dedup.loc[at, "n_benign"])
        canonical.loc[at, "n_attack_dedup"] = int(dedup.loc[at, "n_attack"])
    canonical = canonical.reset_index()
    canonical[["n_benign_dedup", "n_attack_dedup"]] = canonical[["n_benign_dedup", "n_attack_dedup"]].astype(int)
    canonical.to_csv(os.path.join(SINGLE_DIR, "results.csv"), index=False)
    print(f"Patched {os.path.join(SINGLE_DIR, 'results.csv')}")

    n_line = ", ".join(
        f"{r['attack_type']} n={int(r['n_attack_dedup'])}" for _, r in canonical.iterrows()
    ) + f", benign n={int(canonical['n_benign_dedup'].iloc[0])}"

    lines = [
        "# Clean-only (0% contamination) VAE, evaluated per attack type",
        "",
        "Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` "
        "(20 seeds, threshold_95 per seed, inference only, no retraining).",
        "",
        "Each row = that attack type's flows vs. the full test-split benign set "
        "only (other attack types excluded from that run). Mean +/- std across "
        "20 seeds.",
        "",
        SCORE_NOTE,
        "",
        footnote(n_line),
        "",
        "| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | benign FPR (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in canonical.iterrows():
        lines.append(metric_row(f"{r['attack_type']} | {int(r['n_benign'])} | {int(r['n_attack'])}", r))
    with open(os.path.join(SINGLE_DIR, "results.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Rewrote {os.path.join(SINGLE_DIR, 'results.md')}")
    return canonical


def compute_pairwise_dedup():
    """Pairwise PR-AUC/F1 on the dedup set (the sanity check only ran the
    single-type evaluation). Same backend/metric code as everything else."""
    feature_cols = single.load_feature_cols()
    labeled = pd.read_csv(DEDUP_CSV)
    df = attach_features(labeled, feature_cols)
    backend = single.VAEBackend(deterministic=True)

    rows = []
    for pair in pairwise.PAIRS:
        name = pairwise.pair_name(pair)
        subset = df[(df["is_attack"] == 0) | (df["attack_type"].isin(pair))].copy()
        rows.extend(single.evaluate_group(subset, feature_cols, name, backend=backend))
    per_seed = pd.DataFrame(rows)
    summary = per_seed.groupby(["attack_type", "n_benign", "n_attack"])[["pr_auc", "f1"]].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    return summary.reset_index().rename(columns={"attack_type": "attack_type_pair"}).set_index("attack_type_pair")


def patch_pairwise():
    dedup = compute_pairwise_dedup()
    canonical = pd.read_csv(os.path.join(PAIRWISE_DIR, "results.csv")).set_index("attack_type_pair")
    for p in canonical.index:
        for c in PREV_COLS:
            canonical.loc[p, c] = dedup.loc[p, c]
        canonical.loc[p, "n_benign_dedup"] = int(dedup.loc[p, "n_benign"])
        canonical.loc[p, "n_attack_dedup"] = int(dedup.loc[p, "n_attack"])
    canonical = canonical.reset_index()
    canonical[["n_benign_dedup", "n_attack_dedup"]] = canonical[["n_benign_dedup", "n_attack_dedup"]].astype(int)
    canonical.to_csv(os.path.join(PAIRWISE_DIR, "results.csv"), index=False)
    print(f"Patched {os.path.join(PAIRWISE_DIR, 'results.csv')}")

    n_line = ", ".join(
        f"{r['attack_type_pair']} n={int(r['n_attack_dedup'])}" for _, r in canonical.iterrows()
    ) + f", benign n={int(canonical['n_benign_dedup'].iloc[0])}"

    lines = [
        "# Clean-only (0% contamination) VAE, evaluated per pairwise attack-type combination",
        "",
        "Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` "
        "(20 seeds, threshold_95 per seed, inference only, no retraining).",
        "",
        "Each row = both listed attack types' flows vs. the full test-split benign set "
        "(the third attack type is excluded from that run). Mean +/- std across 20 seeds.",
        "",
        SCORE_NOTE,
        "",
        footnote(n_line),
        "",
        "| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | benign FPR (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in canonical.iterrows():
        lines.append(metric_row(f"{r['attack_type_pair']} | {int(r['n_benign'])} | {int(r['n_attack'])}", r))
    with open(os.path.join(PAIRWISE_DIR, "results.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Rewrote {os.path.join(PAIRWISE_DIR, 'results.md')}")
    return canonical


def rewrite_combined(single_df, pairwise_df):
    """results_combined.md from the two PATCHED CSVs, same structure as
    evaluate_pairwise_attack_type.write_combined_table(). The apache_bench
    solo-vs-paired recall section uses recall values only (behavior metrics,
    canonical set) -- read from decomposed_recall.csv, which is unchanged."""
    decomposed = pd.read_csv(os.path.join(PAIRWISE_DIR, "decomposed_recall.csv"), index_col=0)

    def fmt(row):
        return (
            f"{row['roc_auc_mean']:.4f} +/- {row['roc_auc_std']:.4f}",
            f"{row['pr_auc_mean']:.4f} +/- {row['pr_auc_std']:.4f}",
            f"{row['f1_mean']:.4f} +/- {row['f1_std']:.4f}",
            f"{row['attack_recall_mean']:.4f} +/- {row['attack_recall_std']:.4f}",
        )

    n_line_all = "tekli: " + ", ".join(
        f"{r['attack_type']} n={int(r['n_attack_dedup'])}" for _, r in single_df.iterrows()
    ) + "; ikili: " + ", ".join(
        f"{r['attack_type_pair']} n={int(r['n_attack_dedup'])}" for _, r in pairwise_df.iterrows()
    ) + f"; benign n={int(single_df['n_benign_dedup'].iloc[0])}"

    lines = [
        "# Single vs. pairwise attack-type evaluation (clean-only VAE, contam_0pct)",
        "",
        "Combines results.md (single) and results.md (pairwise) into one table, so each "
        "attack type's solo performance can be read next to its performance when a second "
        "attack type shares the evaluation set (both compared against the same fixed benign "
        "pool; the non-participating attack type is excluded from each run, never present "
        "as unlabeled noise). Deterministic z_mean scoring throughout.",
        "",
        footnote(n_line_all),
        "",
        "| evaluation set | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in single_df.iterrows():
        roc, pr, f1, rec = fmt(r)
        lines.append(f"| {r['attack_type']} (solo) | {int(r['n_benign'])} | {int(r['n_attack'])} | {roc} | {pr} | {f1} | {rec} |")
    for _, r in pairwise_df.iterrows():
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
        "test set, this matches the solo number exactly (deterministic scoring: the equality is "
        "now literal, not up-to-noise) -- it is here to make that point explicit, not because "
        "pairing is expected to change it.",
        "",
        "| evaluation set | pooled recall (pair) | apache_bench-only recall (pair) |",
        "|---|---|---|",
    ]
    ab_solo = single_df[single_df["attack_type"] == "apache_bench"].iloc[0]
    lines.append(
        f"| apache_bench (solo) | -- | {ab_solo['attack_recall_mean']:.4f} +/- {ab_solo['attack_recall_std']:.4f} |"
    )
    for _, r in pairwise_df.iterrows():
        if "apache_bench" in r["attack_type_pair"]:
            ab_mean = decomposed.loc[r["attack_type_pair"], "recall__apache_bench_mean"]
            ab_std = decomposed.loc[r["attack_type_pair"], "recall__apache_bench_std"]
            lines.append(
                f"| {r['attack_type_pair']} (pair) | {r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} "
                f"| {ab_mean:.4f} +/- {ab_std:.4f} |"
            )
    with open(os.path.join(PAIRWISE_DIR, "results_combined.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Rewrote {os.path.join(PAIRWISE_DIR, 'results_combined.md')}")


SEGMENTED_NOTE = (
    "\n## Dedup prevalans düzeltmesi bu rapora neden uygulanmadı\n\n"
    "01/02'deki kanonik tablolarda PR-AUC ve F1, resampled kopyaların prevalans'ı "
    "çarpıtmaması için dedup edilmiş test setinden alınmıştır. Bu raporda ise "
    "prevalans-duyarlı metrik yok: PR-AUC hiç raporlanmıyor ve blok F1'i, her attack "
    "bloğu %100 attack flow'dan oluştuğu için (blokta benign yok) precision=1 ile "
    "F1 = 2·recall/(1+recall) — yani recall'un birebir fonksiyonu, bir davranış "
    "metriği. Dedup sağlamlık kontrolü (`../../01_single_attack_type/vae/"
    "dedup_sanity_check/`) davranış metriklerinin dedup'la <0.02 değiştiğini "
    "doğruladı; resampled kopyalar burada yalnızca segment başına n'i şişirir "
    "(attack satırlarının %31'i kopya), hiçbir orandaki sonucu değiştirmez.\n"
)


def annotate_segmented():
    with open(SEGMENTED_MD) as f:
        content = f.read()
    if "Dedup prevalans düzeltmesi" in content:
        print(f"{SEGMENTED_MD} already annotated, skipping.")
        return
    with open(SEGMENTED_MD, "a") as f:
        f.write(SEGMENTED_NOTE)
    print(f"Appended dedup note to {SEGMENTED_MD}")


if __name__ == "__main__":
    single_df = patch_single()
    pairwise_df = patch_pairwise()
    rewrite_combined(single_df, pairwise_df)
    annotate_segmented()
    print("done")
