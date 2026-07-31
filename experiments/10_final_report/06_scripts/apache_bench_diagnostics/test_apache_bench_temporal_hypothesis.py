"""
Quick, no-retrain check of the temporal hypothesis raised in
diagnose_apache_bench_findings.md section 5: that apache_bench flows are
individually unremarkable but unusually frequent/regular in time, a property
invisible to the current single-flow feature set.

Computes one simple flow-window feature directly from ts (no retraining, no
new modeling features added anywhere): inter-arrival time (IAT) between
consecutive flows of the same label, i.e. sort a window_id's flows by ts and
diff consecutive apache_bench-labeled ts values (and separately, consecutive
benign-labeled ts values as the reference group). Diffs are taken within each
window_id only, never across window boundaries -- window_ids don't share a
timeline (including window_resampled_15pct/20pct, whose flows carry their
original ts under a relabeled window_id, per 06_attack_type_analysis/
derive_attack_type_labels.py).

Note this is IAT among *test-split* flows of a given label (the test split is
a subsample of each window, not every flow that occurred), so it is a proxy
for true request inter-arrival, not an exact reconstruction of it -- adequate
for the quick single-feature check this script is for.

Outputs (this directory):
  - temporal_iat_summary.csv: mean/std/percentiles + KS test, benign vs.
    apache_bench inter-arrival time.
  - iat_apache_bench_vs_benign_hist.png: log-x histogram of both.
  - appends a "Temporal hypothesis test" section to the end of
    diagnose_apache_bench_findings.md (run diagnose_apache_bench.py first;
    that script regenerates the whole file and would remove this section if
    run again afterwards).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
LABELED_TEST_PATH = os.path.join(PROJECT_ROOT, "06_attack_type_analysis", "test_with_attack_type.csv")

IAT_SUMMARY_CSV = os.path.join(HERE, "temporal_iat_summary.csv")
IAT_HIST_PNG = os.path.join(HERE, "iat_apache_bench_vs_benign_hist.png")
FINDINGS_MD = os.path.join(HERE, "diagnose_apache_bench_findings.md")

COLOR_BENIGN = "#0072B2"       # blue, matches diagnose_apache_bench.py
COLOR_APACHE_BENCH = "#D55E00"  # vermillion, matches diagnose_apache_bench.py

PERCENTILES = [5, 25, 50, 75, 95, 99]


def consecutive_iat(df, label_mask):
    """Inter-arrival time between consecutive ts values of the rows selected
    by label_mask, computed per window_id (never diffed across window
    boundaries) then pooled across windows."""
    subset = df[label_mask]
    diffs = []
    for _window_id, g in subset.groupby("window_id"):
        ts_sorted = np.sort(g["ts"].values)
        if len(ts_sorted) > 1:
            diffs.append(np.diff(ts_sorted))
    return np.concatenate(diffs) if diffs else np.array([])


def main():
    df = pd.read_csv(LABELED_TEST_PATH)
    benign_iat = consecutive_iat(df, df["is_attack"] == 0)
    apache_iat = consecutive_iat(df, df["attack_type"] == "apache_bench")
    print(f"benign IAT: n={len(benign_iat)}, apache_bench IAT: n={len(apache_iat)}")

    ks_stat, ks_pvalue = ks_2samp(benign_iat, apache_iat)
    print(f"KS statistic={ks_stat:.4f}, p-value={ks_pvalue:.3e}")

    summary_rows = []
    for name, arr in [("benign", benign_iat), ("apache_bench", apache_iat)]:
        row = {"group": name, "n": len(arr), "mean": np.mean(arr), "std": np.std(arr)}
        for p in PERCENTILES:
            row[f"p{p}"] = np.percentile(arr, p)
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    summary_df["ks_statistic"] = ks_stat
    summary_df["ks_pvalue"] = ks_pvalue
    summary_df.to_csv(IAT_SUMMARY_CSV, index=False)
    print(f"Wrote {IAT_SUMMARY_CSV}")

    plot_iat_histogram(benign_iat, apache_iat, IAT_HIST_PNG)
    print(f"Wrote {IAT_HIST_PNG}")

    append_findings_section(summary_df, ks_stat, ks_pvalue, benign_iat, apache_iat)
    print(f"Appended temporal hypothesis test section to {FINDINGS_MD}")


def plot_iat_histogram(benign_iat, apache_iat, path):
    eps = 1e-4  # smallest meaningful IAT here is sub-millisecond, not 0
    all_iat = np.concatenate([benign_iat, apache_iat])
    bins = np.logspace(np.log10(max(all_iat.min(), eps)), np.log10(all_iat.max()), 60)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for name, arr, color in [("benign", benign_iat, COLOR_BENIGN),
                              ("apache_bench", apache_iat, COLOR_APACHE_BENCH)]:
        ax.hist(arr, bins=bins, density=True, histtype="stepfilled",
                alpha=0.35, color=color, label=f"{name} (n={len(arr)})")
        ax.hist(arr, bins=bins, density=True, histtype="step", linewidth=2, color=color)
    ax.set_xscale("log")
    ax.set_xlabel("inter-arrival time between consecutive same-label flows, seconds (log scale)")
    ax.set_ylabel("density")
    ax.set_title("Inter-arrival time: benign vs. apache_bench (within-window_id, consecutive same-label flows)")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def append_findings_section(summary_df, ks_stat, ks_pvalue, benign_iat, apache_iat):
    b = summary_df[summary_df["group"] == "benign"].iloc[0]
    a = summary_df[summary_df["group"] == "apache_bench"].iloc[0]

    lines = []
    lines.append("## 6. Temporal hypothesis test: inter-arrival time\n")
    lines.append(
        "Quick, no-retrain check of the section 5 hypothesis: compute one "
        "flow-window feature directly from the existing `ts` column -- "
        "inter-arrival time (IAT) between consecutive same-label flows, "
        "diffed within each `window_id` only (see "
        "`test_apache_bench_temporal_hypothesis.py`). This is not a modeling "
        "feature added to the VAE; it is a standalone statistical check of "
        "whether such a feature *could* separate apache_bench from benign.\n"
    )
    lines.append("| group | n | mean IAT (s) | std IAT (s) | p5 | p25 | median | p75 | p95 | p99 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in (b, a):
        lines.append(
            f"| {r['group']} | {int(r['n'])} | {r['mean']:.4g} | {r['std']:.4g} | "
            f"{r['p5']:.4g} | {r['p25']:.4g} | {r['p50']:.4g} | {r['p75']:.4g} | "
            f"{r['p95']:.4g} | {r['p99']:.4g} |"
        )
    lines.append("")
    lines.append(f"KS statistic = {ks_stat:.4f}, p-value = {ks_pvalue:.3e} (n_benign={len(benign_iat)}, n_apache_bench={len(apache_iat)}).\n")

    ratio = b["p50"] / a["p50"] if a["p50"] > 0 else float("inf")
    lines.append(
        f"apache_bench's median inter-arrival time ({a['p50']:.4g}s) is about "
        f"{ratio:.0f}x shorter than benign's ({b['p50']:.4g}s). The KS statistic "
        f"({ks_stat:.3f}) is in the same range as section 1's strongest "
        "single-flow features (0.62-0.76), not higher -- so IAT alone is not "
        "obviously a *better* discriminator by KS. What is different is the "
        "**effect size**: section 1 found apache_bench's strongest features had "
        "means only ~0.4-0.7 benign-std away from benign's mean (inside "
        "benign's normal range); here the two groups' medians differ by ~3 "
        "orders of magnitude, with apache_bench's IAT overwhelmingly under 2ms "
        "(consecutive apache_bench requests arriving almost back-to-back) "
        "against benign's multi-second median. See "
        "`iat_apache_bench_vs_benign_hist.png`. (apache_bench's mean, "
        f"{a['mean']:.4g}s, and p99, {a['p99']:.4g}s, are much larger than its "
        "median because the IAT distribution is bimodal: sub-2ms within a "
        "burst of apache_bench requests, and occasional much longer gaps "
        "between separate bursts in the same window -- both consistent with a "
        "benchmarking tool that fires rapid request bursts rather than one "
        "steady stream.)\n"
    )
    lines.append(
        "This partially supports the section 5 hypothesis: IAT does not beat "
        "the best single-flow features on KS statistic alone, but it separates "
        "apache_bench from benign via a completely different, much larger-"
        "magnitude signal (multi-order-of-magnitude rate difference vs. a "
        "sub-1-sigma mean shift) that the current 18 features have no way to "
        "represent, since none of them look across flows. That is still "
        "grounds to expect a rate/concurrency feature to help, though "
        "which of KS statistic or effect size actually predicts VAE "
        "reconstruction-error separation is untested here. This is a "
        "statistical check of the feature's separability alone, not a "
        "validation that adding it to the VAE and retraining would actually "
        "raise apache_bench's reconstruction error above threshold -- that "
        "would need to be confirmed with a real retrain-and-evaluate pass, "
        "which is out of scope here.\n"
    )

    with open(FINDINGS_MD, "a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
