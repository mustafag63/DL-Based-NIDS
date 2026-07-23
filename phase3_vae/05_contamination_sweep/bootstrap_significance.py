"""
Phase 3 (VAE) - contamination sweep, statistical-significance pass: now that
all 9 contamination points (0/1/2/4/8/12/14.33/19.30/21.29%) have n=20 seeds
each (see train/evaluate_contamination_sweep_original_seedext.py), compare
each point's PR-AUC distribution across seeds against the 0% (clean)
baseline with a bootstrap confidence interval on the difference in means.

Method: for each non-zero contamination level, draw 10,000 bootstrap
resamples (with replacement) of size n_seeds independently from the 0%
group and from the level's group, compute mean(level) - mean(0%) for each
resample pair, and report the 2.5th/97.5th percentile of that distribution
as the 95% CI. If the CI excludes 0, the difference from clean-only is
called statistically significant at the seed level (given the caveat that
this is still only ~20 independent training runs per point, not a
distributional claim about the underlying data-generating process).

Deliberately dependency-light: plain numpy resampling, no scipy.stats.bootstrap,
matching the rest of this sweep's minimal-dependency style.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "05_results"

N_BOOT = 10_000
RNG_SEED = 12345
METRIC = "pr_auc"
PLOT_METRICS = ["pr_auc", "f1", "benign_fpr", "attack_recall"]


def bootstrap_diff_ci(baseline, level, n_boot=N_BOOT, seed=RNG_SEED):
    rng = np.random.default_rng(seed)
    baseline = np.asarray(baseline)
    level = np.asarray(level)
    n_base, n_level = len(baseline), len(level)

    boot_diffs = np.empty(n_boot)
    for i in range(n_boot):
        base_sample = rng.choice(baseline, size=n_base, replace=True)
        level_sample = rng.choice(level, size=n_level, replace=True)
        boot_diffs[i] = level_sample.mean() - base_sample.mean()

    point_diff = level.mean() - baseline.mean()
    ci_lo, ci_hi = np.percentile(boot_diffs, [2.5, 97.5])
    significant = not (ci_lo <= 0 <= ci_hi)
    return point_diff, ci_lo, ci_hi, significant


def bootstrap_point_ci(values, n_boot=N_BOOT, seed=RNG_SEED):
    rng = np.random.default_rng(seed)
    values = np.asarray(values)
    n = len(values)
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        boot_means[i] = rng.choice(values, size=n, replace=True).mean()
    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
    return float(ci_lo), float(ci_hi)


def main() -> None:
    per_seed = pd.read_csv(RESULTS_DIR / "results_per_seed.csv")

    levels = sorted(per_seed["contamination_pct"].unique())
    n_seeds_per_level = per_seed.groupby("contamination_pct")["seed"].nunique()
    print("n_seeds per level:", dict(n_seeds_per_level))
    assert (n_seeds_per_level == 20).all(), (
        f"expected 20 seeds at every level before running significance tests, got:\n{n_seeds_per_level}"
    )

    baseline_vals = per_seed.loc[per_seed["contamination_pct"] == 0, METRIC].values
    assert len(baseline_vals) == 20

    rows = []
    for level_pct in levels:
        level_vals = per_seed.loc[per_seed["contamination_pct"] == level_pct, METRIC].values
        mean = level_vals.mean()
        median = np.median(level_vals)
        std = level_vals.std(ddof=1)

        if level_pct == 0:
            diff, ci_lo, ci_hi, significant = 0.0, 0.0, 0.0, False
        else:
            diff, ci_lo, ci_hi, significant = bootstrap_diff_ci(baseline_vals, level_vals)

        rows.append({
            "contamination_pct": level_pct,
            "n_seeds": len(level_vals),
            "pr_auc_mean": mean,
            "pr_auc_median": median,
            "pr_auc_std": std,
            "diff_from_0pct_mean": diff,
            "ci95_lo": ci_lo,
            "ci95_hi": ci_hi,
            "significant": significant,
        })
        sig_str = "YES" if significant else "no"
        print(f"  {level_pct:>6}%: mean={mean:.4f} median={median:.4f} std={std:.4f} "
              f"diff_vs_0%={diff:+.4f} 95%CI=[{ci_lo:+.4f}, {ci_hi:+.4f}] significant={sig_str}")

    out_df = pd.DataFrame(rows)
    out_path = RESULTS_DIR / "bootstrap_significance.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    # Per-point CI (own mean, not diff-from-baseline) for every metric used in
    # the contamination_curve.png panels - these become the plotted error bars.
    point_rows = []
    for level_pct in levels:
        level_df = per_seed[per_seed["contamination_pct"] == level_pct]
        row = {"contamination_pct": level_pct}
        for metric in PLOT_METRICS:
            vals = level_df[metric].values
            lo, hi = bootstrap_point_ci(vals)
            row[f"{metric}_mean"] = vals.mean()
            row[f"{metric}_ci95_lo"] = lo
            row[f"{metric}_ci95_hi"] = hi
        point_rows.append(row)
    point_ci_df = pd.DataFrame(point_rows)
    point_ci_path = RESULTS_DIR / "bootstrap_point_ci.csv"
    point_ci_df.to_csv(point_ci_path, index=False)
    print(f"Wrote {point_ci_path}")


if __name__ == "__main__":
    main()
