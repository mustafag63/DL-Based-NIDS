"""
Phase 3 (VAE) - contamination sweep, final curve: redraws
05_results/contamination_curve.png from the now-20-seeds-everywhere data
(0/1/2/4/8/12/14.33/19.30/21.29%), replacing the mean+/-std shaded band with
95% bootstrap CI error bars per point (from bootstrap_point_ci.csv, see
bootstrap_significance.py) and visually de-emphasizing (lower alpha, no
fill) points whose PR-AUC is not statistically significantly different
from the 0% baseline (bootstrap_significance.csv's `significant` column).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "05_results"

# All 9 points are now evaluated identically (20 seeds, same fixed test set,
# same threshold protocol) - no controlled-injection/resampled-window marker
# distinction anymore, only significance-vs-0% is visually encoded.
PANELS = [
    ("pr_auc", "PR-AUC"),
    ("f1", "F1 (threshold_95)"),
    ("benign_fpr", "Benign FPR (threshold_95)"),
    ("attack_recall", "Attack Recall (threshold_95)"),
]


def main() -> None:
    point_ci = pd.read_csv(RESULTS_DIR / "bootstrap_point_ci.csv").sort_values("contamination_pct")
    sig = pd.read_csv(RESULTS_DIR / "bootstrap_significance.csv").sort_values("contamination_pct")
    x = point_ci["contamination_pct"].values
    significant = sig.set_index("contamination_pct").loc[x, "significant"].values.astype(bool)

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for (metric, title), ax in zip(PANELS, axes.flat):
        mean = point_ci[f"{metric}_mean"].values
        ci_lo = point_ci[f"{metric}_ci95_lo"].values
        ci_hi = point_ci[f"{metric}_ci95_hi"].values

        ax.plot(x, mean, color="#3b6fa0", linewidth=1.0, zorder=1, alpha=0.6)

        for xi, mi, loi, hii, is_sig in zip(x, mean, ci_lo, ci_hi, significant):
            # non-significant-vs-0% points rendered lighter/hollow so the
            # eye doesn't read them as confidently different from baseline
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

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="#3b6fa0", linestyle="", markersize=7,
                   label="significant vs 0% baseline"),
        plt.Line2D([0], [0], marker="o", color="#3b6fa0", linestyle="", markersize=7,
                   markerfacecolor="none", alpha=0.5, label="not significant vs 0% (95% CI crosses 0)"),
    ]
    axes[0, 0].legend(handles=legend_handles, fontsize=7, loc="best")
    fig.suptitle("VAE contamination sweep (latent=10, beta=0.25) - fixed test set, n=20 seeds/point\n"
                 "error bars = 95% bootstrap CI on the mean; hollow/faded = not significantly "
                 "different from 0% baseline (PR-AUC bootstrap test)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "contamination_curve.png", dpi=150)
    print(f"Wrote {RESULTS_DIR / 'contamination_curve.png'}")


if __name__ == "__main__":
    main()
