"""
Full deconfounded sweep, step 3: bootstrap significance + curve.

Replicates bootstrap_significance.py's method exactly (10,000 resamples,
rng seed 12345, PR-AUC diff-of-means vs the 0% baseline, 95% CI; plus
per-point bootstrap CIs on the mean for the four plotted metrics) on BOTH
arms:
  - v2      : results_all_points.csv        (deconfounded pipeline, primary)
  - v1_det  : v1_deterministic_results_per_seed.csv (original pipeline,
              deterministically rescored -- reference, so the v1-vs-v2
              comparison is not muddied by the scoring-mode difference)

Outputs (this directory):
  bootstrap_significance_deconfounded.csv  -- diff-vs-0% table, `arm` column
  bootstrap_point_ci_deconfounded.csv      -- per-point metric CIs, `arm` column
  contamination_curve_deconfounded.png     -- v2 curve, same format as
      plot_contamination_curve_with_ci.py (95% CI error bars; hollow/faded
      points = PR-AUC not significantly different from 0% baseline)
  comparison_by_level.csv                  -- v1_det vs v2 mean metrics per
      target level, for the findings doc
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))
from bootstrap_significance import bootstrap_diff_ci, bootstrap_point_ci  # noqa: E402

PLOT_METRICS = [
    ("pr_auc", "PR-AUC"),
    ("f1", "F1 (threshold_95)"),
    ("benign_fpr", "Benign FPR (threshold_95)"),
    ("attack_recall", "Attack Recall (threshold_95)"),
]

# v1 curve x convention (results_per_seed.csv): nominal for injection,
# actual for resampled.
V1_CURVE_PCT = {0: 0, 1: 1, 2: 2, 4: 4, 8: 8, 12: 12, 15: 14.33, 20: 19.30, 22: 21.29}


def significance_tables(per_seed, arm, level_col):
    levels = sorted(per_seed[level_col].unique())
    n_seeds = per_seed.groupby(level_col)["seed"].nunique()
    assert (n_seeds == 20).all(), f"{arm}: expected 20 seeds everywhere, got {dict(n_seeds)}"
    baseline = per_seed.loc[per_seed[level_col] == 0, "pr_auc"].values

    diff_rows, ci_rows = [], []
    for lvl in levels:
        sub = per_seed[per_seed[level_col] == lvl]
        vals = sub["pr_auc"].values
        if lvl == 0:
            diff, lo, hi, sig = 0.0, 0.0, 0.0, False
        else:
            diff, lo, hi, sig = bootstrap_diff_ci(baseline, vals)
        diff_rows.append({"arm": arm, "contamination_pct": lvl, "n_seeds": len(vals),
                          "pr_auc_mean": vals.mean(), "pr_auc_median": np.median(vals),
                          "pr_auc_std": vals.std(ddof=1),
                          "diff_from_0pct_mean": diff, "ci95_lo": lo, "ci95_hi": hi,
                          "significant": sig})
        row = {"arm": arm, "contamination_pct": lvl}
        for m, _ in PLOT_METRICS:
            v = sub[m].values
            lo_m, hi_m = bootstrap_point_ci(v)
            row[f"{m}_mean"], row[f"{m}_ci95_lo"], row[f"{m}_ci95_hi"] = v.mean(), lo_m, hi_m
        ci_rows.append(row)
        print(f"  [{arm}] {lvl:>6}%: PR-AUC={vals.mean():.4f} diff_vs_0%={diff:+.4f} "
              f"CI=[{lo:+.4f},{hi:+.4f}] significant={'YES' if sig else 'no'}")
    return pd.DataFrame(diff_rows), pd.DataFrame(ci_rows)


def plot_curve(point_ci, sig, out_path):
    x = point_ci["contamination_pct"].values
    significant = sig.set_index("contamination_pct").loc[x, "significant"].values.astype(bool)

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for (metric, title), ax in zip(PLOT_METRICS, axes.flat):
        mean = point_ci[f"{metric}_mean"].values
        lo = point_ci[f"{metric}_ci95_lo"].values
        hi = point_ci[f"{metric}_ci95_hi"].values
        ax.plot(x, mean, color="#3b6fa0", linewidth=1.0, zorder=1, alpha=0.6)
        for xi, mi, loi, hii, is_sig in zip(x, mean, lo, hi, significant):
            alpha = 1.0 if is_sig or xi == 0 else 0.35
            facecolor = "#3b6fa0" if (is_sig or xi == 0) else "none"
            ax.errorbar(xi, mi, yerr=[[mi - loi], [hii - mi]], fmt="o",
                        color="#3b6fa0", ecolor="#3b6fa0", elinewidth=1.3, capsize=3,
                        markersize=7, markerfacecolor=facecolor, alpha=alpha, zorder=3)
        ax.axvline(12, color="#999999", linestyle="--", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("Train contamination (%)")
        ax.set_ylabel(title)
        ax.grid(alpha=0.3)

    handles = [
        plt.Line2D([0], [0], marker="o", color="#3b6fa0", linestyle="", markersize=7,
                   label="significant vs 0% baseline"),
        plt.Line2D([0], [0], marker="o", color="#3b6fa0", linestyle="", markersize=7,
                   markerfacecolor="none", alpha=0.5,
                   label="not significant vs 0% (95% CI crosses 0)"),
    ]
    axes[0, 0].legend(handles=handles, fontsize=7, loc="best")
    fig.suptitle("VAE contamination sweep — DECONFOUNDED pipeline (K1 mixed-benign test, "
                 "K2 signature-grouped split, O2 deterministic z_mean)\n"
                 "latent=10, beta=0.25, n=20 seeds/point; error bars = 95% bootstrap CI on the "
                 "mean; hollow/faded = not significantly different from 0% (PR-AUC bootstrap test)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


def main():
    v2 = pd.read_csv(HERE / "results_all_points.csv")
    v1 = pd.read_csv(HERE / "v1_deterministic_results_per_seed.csv")
    v1["contamination_pct"] = v1["target_pct"].map(V1_CURVE_PCT)

    print("=== v2 (deconfounded) ===")
    v2_diff, v2_ci = significance_tables(v2, "v2", "contamination_pct")
    print("=== v1_det (original pipeline, deterministic rescore) ===")
    v1_diff, v1_ci = significance_tables(v1, "v1_det", "contamination_pct")

    pd.concat([v2_diff, v1_diff], ignore_index=True).to_csv(
        HERE / "bootstrap_significance_deconfounded.csv", index=False)
    pd.concat([v2_ci, v1_ci], ignore_index=True).to_csv(
        HERE / "bootstrap_point_ci_deconfounded.csv", index=False)
    print(f"Wrote {HERE / 'bootstrap_significance_deconfounded.csv'} and bootstrap_point_ci_deconfounded.csv")

    plot_curve(v2_ci.sort_values("contamination_pct"),
               v2_diff.sort_values("contamination_pct"),
               HERE / "contamination_curve_deconfounded.png")

    # side-by-side per-level comparison for the findings doc
    def level_means(df, arm):
        g = df.groupby("target_pct")[["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]]
        out = g.mean().add_prefix(f"{arm}_")
        out[f"{arm}_pr_auc_std"] = g.std()["pr_auc"]
        return out

    comp = level_means(v2, "v2").join(level_means(v1, "v1det"))
    comp["pr_auc_delta_v2_minus_v1det"] = comp["v2_pr_auc"] - comp["v1det_pr_auc"]
    comp.to_csv(HERE / "comparison_by_level.csv")
    print(f"Wrote {HERE / 'comparison_by_level.csv'}")
    print(comp[["v1det_pr_auc", "v2_pr_auc", "pr_auc_delta_v2_minus_v1det"]].round(4).to_string())


if __name__ == "__main__":
    main()
