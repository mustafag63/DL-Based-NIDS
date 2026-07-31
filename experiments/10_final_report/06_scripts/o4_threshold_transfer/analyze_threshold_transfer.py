"""Numerical check for audit finding O4 (11_fable_review/independent_audit.md):
threshold_95 is calibrated as the 95th percentile of reconstruction error on a
SMALL val-benign set (window_10 val split), then applied to test benign flows
from other windows -- a distribution-transfer assumption.

No retraining. For each of the 20 canonical clean-only VAE seeds
(deterministic z_mean scoring, the post-O2 convention):

  1. n of the val-benign calibration set (same set for every seed).
  2. threshold_95 on val-benign -> cross-seed mean/std/CV.
  3. Within-seed sampling noise of the 95th-percentile estimator itself:
     bootstrap the 653 val errors (10k resamples) -> per-seed 95% CI width.
     This separates "small-n percentile noise" from "model-to-model variance".
  4. Distribution transfer val -> test benign: two-sample KS test between the
     val-benign and test-benign z_mean error distributions, plus the realized
     test-benign FPR at the val-derived threshold (5.00% == perfect transfer)
     and the threshold that WOULD have given exactly 5% on test benign.

Outputs (this directory): threshold_transfer_per_seed.csv,
threshold_transfer_summary.md. Nothing in the published reports is touched.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
sys.path.insert(0, ATTACK_TYPE_DIR)

import evaluate_by_attack_type as single  # noqa: E402

SEEDS = list(range(20))
N_BOOT = 10_000
RNG = np.random.default_rng(4_2026)

PER_SEED_CSV = os.path.join(HERE, "threshold_transfer_per_seed.csv")
SUMMARY_MD = os.path.join(HERE, "threshold_transfer_summary.md")


def main():
    backend = single.VAEBackend(deterministic=True)
    X_val = backend._val_benign_X_cached()
    n_val = len(X_val)

    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)
    test_benign = df[df["is_attack"] == 0]
    X_test_benign = test_benign[feature_cols].values.astype("float32")
    n_test = len(X_test_benign)
    print(f"val-benign n={n_val} (window_10 val split), "
          f"test-benign n={n_test} (window_02-08 + resampled)")

    rows = []
    for seed in SEEDS:
        model = backend.load(seed)
        val_err = single.reconstruction_error_zmean(model["encoder"], model["decoder"], X_val)
        test_err = single.reconstruction_error_zmean(model["encoder"], model["decoder"], X_test_benign)

        thr95_val = float(np.percentile(val_err, 95))
        thr95_test = float(np.percentile(test_err, 95))

        # bootstrap CI of the val 95th percentile (small-n order-statistic noise)
        idx = RNG.integers(0, n_val, size=(N_BOOT, n_val))
        boot_p95 = np.percentile(val_err[idx], 95, axis=1)
        ci_lo, ci_hi = np.percentile(boot_p95, [2.5, 97.5])

        ks_stat, ks_p = ks_2samp(val_err, test_err)
        fpr_test = float((test_err > thr95_val).mean())

        rows.append({
            "seed": seed,
            "n_val": n_val,
            "threshold_95_val": thr95_val,
            "boot_ci95_lo": float(ci_lo),
            "boot_ci95_hi": float(ci_hi),
            "boot_ci95_rel_width": float((ci_hi - ci_lo) / thr95_val),
            "threshold_95_testbenign": thr95_test,
            "thr_ratio_test_over_val": thr95_test / thr95_val,
            "test_benign_fpr_at_val_thr": fpr_test,
            "ks_stat_val_vs_testbenign": float(ks_stat),
            "ks_pvalue": float(ks_p),
            "val_err_median": float(np.median(val_err)),
            "test_err_median": float(np.median(test_err)),
        })
        print(f"  seed {seed:2d}: thr95_val={thr95_val:.4f} "
              f"[boot CI {ci_lo:.4f}-{ci_hi:.4f}] thr95_test={thr95_test:.4f} "
              f"FPR_test={fpr_test:.4f} KS={ks_stat:.4f} (p={ks_p:.2e})")

    per_seed = pd.DataFrame(rows)
    per_seed.to_csv(PER_SEED_CSV, index=False)

    thr = per_seed["threshold_95_val"]
    fpr = per_seed["test_benign_fpr_at_val_thr"]
    summary = {
        "thr95_mean": thr.mean(), "thr95_std": thr.std(ddof=1),
        "thr95_cv": thr.std(ddof=1) / thr.mean(),
        "thr95_min": thr.min(), "thr95_max": thr.max(),
        "boot_rel_width_mean": per_seed["boot_ci95_rel_width"].mean(),
        "fpr_mean": fpr.mean(), "fpr_std": fpr.std(ddof=1),
        "fpr_min": fpr.min(), "fpr_max": fpr.max(),
        "ks_mean": per_seed["ks_stat_val_vs_testbenign"].mean(),
        "ks_min": per_seed["ks_stat_val_vs_testbenign"].min(),
        "ks_max": per_seed["ks_stat_val_vs_testbenign"].max(),
        "n_ks_p_below_0.01": int((per_seed["ks_pvalue"] < 0.01).sum()),
        "ratio_mean": per_seed["thr_ratio_test_over_val"].mean(),
        "ratio_min": per_seed["thr_ratio_test_over_val"].min(),
        "ratio_max": per_seed["thr_ratio_test_over_val"].max(),
    }

    lines = [
        "# O4 threshold transfer check — val-benign (n=653) -> test benign",
        "",
        f"20 canonical clean-only VAE seeds, deterministic z_mean scoring.",
        f"Calibration set: window_10 val-benign, n={n_val}. Applied to test "
        f"benign, n={n_test} (different windows).",
        "",
        f"- threshold_95 across seeds: mean {summary['thr95_mean']:.4f}, "
        f"std {summary['thr95_std']:.4f} (CV {summary['thr95_cv']:.1%}), "
        f"range [{summary['thr95_min']:.4f}, {summary['thr95_max']:.4f}]",
        f"- within-seed bootstrap 95% CI of the percentile estimate: mean "
        f"relative width {summary['boot_rel_width_mean']:.1%} of the threshold",
        f"- test-benign FPR at the val threshold (nominal 5.00%): mean "
        f"{summary['fpr_mean']:.2%} ± {summary['fpr_std']:.2%}, range "
        f"[{summary['fpr_min']:.2%}, {summary['fpr_max']:.2%}]",
        f"- threshold that would give exactly 5% on test benign / val "
        f"threshold: mean ratio {summary['ratio_mean']:.3f}, range "
        f"[{summary['ratio_min']:.3f}, {summary['ratio_max']:.3f}]",
        f"- KS(val errors, test-benign errors): mean {summary['ks_mean']:.4f}, "
        f"range [{summary['ks_min']:.4f}, {summary['ks_max']:.4f}]; "
        f"{summary['n_ks_p_below_0.01']}/20 seeds with p < 0.01",
        "",
        "Per-seed table: threshold_transfer_per_seed.csv",
        "",
    ]
    with open(SUMMARY_MD, "w") as f:
        f.write("\n".join(lines))

    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
