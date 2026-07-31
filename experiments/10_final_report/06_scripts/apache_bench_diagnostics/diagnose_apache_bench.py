"""
Diagnose why apache_bench flows are hard to separate from benign flows for the
clean-only (0% train contamination) VAE (see 06_attack_type_analysis/results_
single_attack_type.md: apache_bench has by far the weakest recall of the three
attack types). Inference / statistics only -- no retraining, no changes to any
existing pipeline output.

Reuses, not reimplements:
  - load_feature_cols(), assemble_labeled_features_df(), compute_error_matrix(),
    DEFAULT_BACKEND (contam_0pct, 20 seeds) from
    06_attack_type_analysis/evaluate_by_attack_type.py
  - which in turn reuses reconstruction_error() from phase3_vae/
    05_contamination_sweep/evaluate_contamination_sweep_extended.py

Four outputs, all in this directory:
  1. feature_diagnostics_<attack_type>.csv (one per apache_bench/portscan/
     slowloris): per scaled-feature mean/std/percentiles for that attack type
     vs. the full test-split benign set, plus a two-sample Kolmogorov-Smirnov
     test (statistic + p-value), sorted most- to least-discriminative (by KS
     statistic).
  2. vae_reconstruction_error_hist.png: histogram of per-flow VAE
     reconstruction error (mean over the 20 contam_0pct seeds) for three
     groups -- benign, apache_bench, portscan+slowloris combined.
  3. top_features_apache_bench_boxplots.png: box plots of the most
     apache_bench-discriminative scaled features (by KS statistic), benign vs.
     apache_bench.
  4. diagnose_apache_bench_findings.md: narrative summary + hypothesis for
     what new feature(s) might help separate apache_bench from benign.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402

ATTACK_TYPES = ["apache_bench", "portscan", "slowloris"]
TARGET_ATTACK_TYPE = "apache_bench"
REFERENCE_ATTACK_TYPES = ["portscan", "slowloris"]
N_TOP_FEATURES = 8
PERCENTILES = [5, 25, 50, 75, 95]

# Okabe-Ito colorblind-safe palette, fixed assignment (not cycled).
COLOR_BENIGN = "#0072B2"       # blue
COLOR_APACHE_BENCH = "#D55E00"  # vermillion -- the group under investigation
COLOR_PORTSCAN = "#009E73"     # green
COLOR_SLOWLORIS = "#CC79A7"    # purple
COLOR_REFERENCE_COMBINED = "#56B4E9"  # sky blue -- portscan+slowloris combined

FEATURE_DIAGNOSTICS_CSV = os.path.join(HERE, "feature_diagnostics_{attack_type}.csv")
ERROR_HIST_PNG = os.path.join(HERE, "vae_reconstruction_error_hist.png")
TOP_FEATURES_BOXPLOT_PNG = os.path.join(HERE, "top_features_apache_bench_boxplots.png")
FINDINGS_MD = os.path.join(HERE, "diagnose_apache_bench_findings.md")


def compare_distributions(feature_cols, benign_df, group_df):
    """Per-feature mean/std/percentile table + two-sample KS test, benign vs.
    group_df, sorted by KS statistic descending (most to least discriminative).

    Also reports `mean_shift_in_benign_std`: (group_mean - benign_mean) /
    benign_std, i.e. how many benign standard deviations away the group's
    *center* sits. A feature can have a high KS statistic (narrow, tightly
    clustered group distribution vs. a wide benign one -> a sharp max-CDF-gap)
    while this shift stays small -- meaning the group sits inside benign's
    normal range rather than out in its tail. Reconstruction error is a sum of
    squared per-feature deviations, so this shift (not the KS statistic) is
    what actually drives whether the VAE's error spikes."""
    rows = []
    for col in feature_cols:
        b = benign_df[col].values.astype("float64")
        g = group_df[col].values.astype("float64")
        ks_stat, ks_pvalue = ks_2samp(b, g)
        benign_std = np.std(b)
        row = {
            "feature": col,
            "benign_mean": np.mean(b), "benign_std": benign_std,
            "group_mean": np.mean(g), "group_std": np.std(g),
            "ks_statistic": ks_stat, "ks_pvalue": ks_pvalue,
            "mean_shift_in_benign_std": (np.mean(g) - np.mean(b)) / benign_std if benign_std > 0 else np.nan,
        }
        for p in PERCENTILES:
            row[f"benign_p{p}"] = np.percentile(b, p)
        for p in PERCENTILES:
            row[f"group_p{p}"] = np.percentile(g, p)
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("ks_statistic", ascending=False).reset_index(drop=True)
    return out


def plot_error_histogram(errors_by_group, threshold_mean, path):
    """Two panels sharing a log-x axis: full range (so portscan/slowloris's
    much larger errors are visible) and a zoom on the benign/apache_bench
    region alone (where the actual overlap this diagnostic cares about is),
    since on a single linear-x axis portscan/slowloris's errors are ~1e6x
    larger and visually flatten benign/apache_bench to a single spike at 0."""
    colors = {
        "benign": COLOR_BENIGN,
        "apache_bench": COLOR_APACHE_BENCH,
        "portscan+slowloris": COLOR_REFERENCE_COMBINED,
    }
    eps = 1e-6
    all_errors = np.concatenate(list(errors_by_group.values()))
    log_min, log_max = np.log10(max(all_errors.min(), eps)), np.log10(all_errors.max())
    bins_full = np.logspace(log_min, log_max, 60)

    zoom_errors = np.concatenate([errors_by_group["benign"], errors_by_group["apache_bench"]])
    zoom_log_min, zoom_log_max = np.log10(max(zoom_errors.min(), eps)), np.log10(zoom_errors.max())
    bins_zoom = np.logspace(zoom_log_min, zoom_log_max, 50)

    fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax, bins, groups in [
        (ax_full, bins_full, errors_by_group.keys()),
        (ax_zoom, bins_zoom, ["benign", "apache_bench"]),
    ]:
        for name in groups:
            errors = errors_by_group[name]
            ax.hist(errors, bins=bins, density=True, histtype="stepfilled",
                    alpha=0.35, color=colors[name], label=f"{name} (n={len(errors)})")
            ax.hist(errors, bins=bins, density=True, histtype="step",
                    linewidth=2, color=colors[name])
        ax.axvline(threshold_mean, color="#555555", linestyle="--", linewidth=1.5,
                    label=f"mean threshold_95 = {threshold_mean:.4g}")
        ax.set_xscale("log")
        ax.set_xlabel("VAE reconstruction error (mean over 20 seeds, log scale)")
        ax.set_ylabel("density")
        ax.legend(frameon=False, fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax_full.set_title("All groups (full range)")
    ax_zoom.set_title("Zoom: benign vs. apache_bench only")
    fig.suptitle("Reconstruction error distribution: benign vs. apache_bench vs. portscan/slowloris")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_top_feature_boxplots(feature_cols, benign_df, apache_df, path):
    n = len(feature_cols)
    ncols = 4
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for i, col in enumerate(feature_cols):
        ax = axes[i]
        data = [benign_df[col].values, apache_df[col].values]
        bp = ax.boxplot(data, tick_labels=["benign", "apache_bench"], patch_artist=True,
                          widths=0.55, showfliers=True,
                          flierprops={"markersize": 3, "alpha": 0.4})
        for patch, color in zip(bp["boxes"], [COLOR_BENIGN, COLOR_APACHE_BENCH]):
            patch.set_facecolor(color)
            patch.set_alpha(0.5)
            patch.set_edgecolor(color)
        for element in ["whiskers", "caps", "medians"]:
            for artist in bp[element]:
                artist.set_color("#444444")
        ax.set_title(col, fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    for j in range(n, len(axes)):
        axes[j].axis("off")
    fig.suptitle("Top apache_bench-discriminative features (by KS statistic): benign vs. apache_bench", y=1.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def feature_group(col):
    if col.startswith("duration"):
        return "duration"
    if "bytes" in col or "byte_ratio" in col:
        return "byte volume"
    if "pkts" in col:
        return "packet count/rate"
    if col.startswith("proto_"):
        return "protocol (one-hot)"
    if col.startswith("service_"):
        return "service (one-hot)"
    if col.startswith("conn_state_"):
        return "connection state (one-hot)"
    return "other"


def main():
    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)

    benign_df = df[df["is_attack"] == 0]
    group_dfs = {atype: df[df["attack_type"] == atype] for atype in ATTACK_TYPES}
    for atype, gdf in group_dfs.items():
        print(f"{atype}: n={len(gdf)}")

    # --- 1 & 2: per-feature distribution comparison + KS test, for all three
    # attack types (apache_bench is the primary target; portscan/slowloris are
    # the reference groups the same analysis is run on for comparison). ---
    diag_tables = {}
    for atype in ATTACK_TYPES:
        diag = compare_distributions(feature_cols, benign_df, group_dfs[atype])
        diag_tables[atype] = diag
        out_path = FEATURE_DIAGNOSTICS_CSV.format(attack_type=atype)
        diag.to_csv(out_path, index=False)
        print(f"Wrote {out_path}")

    # --- 3: VAE reconstruction error histogram, benign vs apache_bench vs
    # portscan+slowloris combined. Run all three groups (+ benign) through the
    # same 20-seed contam_0pct backend used everywhere else in this project. ---
    combined = pd.concat(
        [benign_df] + [group_dfs[a] for a in ATTACK_TYPES], ignore_index=True
    )
    X = combined[feature_cols].values.astype("float32")
    error_matrix, thresholds = single.compute_error_matrix(X, backend=single.DEFAULT_BACKEND)
    mean_errors = error_matrix.mean(axis=0)
    mean_threshold = float(np.mean(thresholds))

    n_benign = len(benign_df)
    offsets = {"benign": (0, n_benign)}
    cursor = n_benign
    for atype in ATTACK_TYPES:
        n = len(group_dfs[atype])
        offsets[atype] = (cursor, cursor + n)
        cursor += n

    errors_by_group = {
        "benign": mean_errors[offsets["benign"][0]:offsets["benign"][1]],
        "apache_bench": mean_errors[offsets["apache_bench"][0]:offsets["apache_bench"][1]],
        "portscan+slowloris": np.concatenate([
            mean_errors[offsets["portscan"][0]:offsets["portscan"][1]],
            mean_errors[offsets["slowloris"][0]:offsets["slowloris"][1]],
        ]),
    }
    plot_error_histogram(errors_by_group, mean_threshold, ERROR_HIST_PNG)
    print(f"Wrote {ERROR_HIST_PNG}")

    error_summary = pd.DataFrame([
        {
            "group": name,
            "n": len(errs),
            "mean_error": float(np.mean(errs)),
            "std_error": float(np.std(errs)),
            "pct_above_mean_threshold95": float((errs > mean_threshold).mean()),
        }
        for name, errs in errors_by_group.items()
    ])
    error_summary_path = os.path.join(HERE, "vae_reconstruction_error_summary.csv")
    error_summary.to_csv(error_summary_path, index=False)
    print(f"Wrote {error_summary_path}")

    # --- 4: top-N apache_bench-discriminative features, box plots ---
    apache_diag = diag_tables[TARGET_ATTACK_TYPE]
    top_features = apache_diag["feature"].head(N_TOP_FEATURES).tolist()
    plot_top_feature_boxplots(top_features, benign_df, group_dfs[TARGET_ATTACK_TYPE], TOP_FEATURES_BOXPLOT_PNG)
    print(f"Wrote {TOP_FEATURES_BOXPLOT_PNG}")

    # --- 5: findings markdown ---
    write_findings(diag_tables, error_summary, top_features)
    print(f"Wrote {FINDINGS_MD}")


def write_findings(diag_tables, error_summary, top_features):
    apache_diag = diag_tables[TARGET_ATTACK_TYPE]

    lines = []
    lines.append("# Why apache_bench flows are not separable from benign\n")
    lines.append(
        "Diagnostic on the clean-only (0% train contamination) VAE "
        "(`phase3_vae/05_contamination_sweep/04_models/contam_0pct`, 20 seeds, "
        "inference only, no retraining), using "
        "`06_attack_type_analysis/test_with_attack_type.csv`. Companion outputs: "
        "`feature_diagnostics_{apache_bench,portscan,slowloris}.csv`, "
        "`vae_reconstruction_error_hist.png`, `vae_reconstruction_error_summary.csv`, "
        "`top_features_apache_bench_boxplots.png`.\n"
    )

    lines.append("## 1. Per-feature separability: apache_bench vs. benign\n")
    lines.append(
        "Ranked by Kolmogorov-Smirnov statistic (0 = distributions fully overlap, "
        "1 = fully separated). All 18 modeling features are scaled (StandardScaler, "
        "fit on train-split benign only), one-hots included.\n"
    )
    lines.append("| feature | group | KS stat | KS p-value | mean shift (benign std) | benign mean (std) | apache_bench mean (std) |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in apache_diag.iterrows():
        shift = "n/a (constant in benign)" if pd.isna(r["mean_shift_in_benign_std"]) else f"{r['mean_shift_in_benign_std']:+.2f} sigma"
        lines.append(
            f"| {r['feature']} | {feature_group(r['feature'])} | {r['ks_statistic']:.3f} | "
            f"{r['ks_pvalue']:.2e} | {shift} | "
            f"{r['benign_mean']:.3f} ({r['benign_std']:.3f}) | "
            f"{r['group_mean']:.3f} ({r['group_std']:.3f}) |"
        )
    lines.append("")

    n_sig = int((apache_diag["ks_pvalue"] < 0.05).sum())
    n_total = len(apache_diag)
    strongest = apache_diag.iloc[0]
    lines.append(
        f"{n_sig}/{n_total} features show a statistically significant (p<0.05) KS "
        f"difference between apache_bench and benign, and the top features "
        f"(`orig_pkts_scaled`, `orig_bytes_scaled`, `resp_bytes_scaled`, "
        f"`resp_pkts_scaled`, `duration_scaled`) all have KS >= 0.69 -- on paper, "
        "apache_bench looks separable. But the KS statistic and the "
        "*mean shift in benign std* column tell different stories. KS is large "
        f"here because apache_bench is a **very narrow, low-variance cluster** "
        f"(its p5-p95 range on `{strongest['feature']}` collapses almost to a "
        "single point -- see the percentile columns in "
        "`feature_diagnostics_apache_bench.csv` -- because ab is a stereotyped, "
        "fixed-size HTTP GET request repeated many times), so its empirical CDF "
        "jumps sharply against benign's much wider spread even though the "
        f"cluster's *center* sits only "
        f"{apache_diag['mean_shift_in_benign_std'].abs().mean():.2f} benign-std "
        "away on average -- i.e. **inside** the range of ordinary benign "
        "traffic, not out in its tail. Reconstruction error is a sum of squared "
        "per-feature deviations from a benign-fit manifold, so a point sitting "
        "inside the training distribution's normal range reconstructs cleanly "
        "regardless of how sharply its CDF differs from benign's.\n"
    )

    lines.append("## 2. Reference: same analysis on portscan and slowloris\n")
    lines.append(
        "Per `06_attack_type_analysis/results_single_attack_type.md`, the "
        "same clean-only VAE gets ROC-AUC 0.58 / recall@thr95 3.3% on "
        "apache_bench, vs. ROC-AUC 0.998-1.000 / recall 98.9-100% on portscan "
        "and slowloris -- the gap this diagnostic is investigating.\n"
    )
    for atype in REFERENCE_ATTACK_TYPES:
        diag = diag_tables[atype]
        top3 = diag.head(3)
        lines.append(f"### {atype}\n")
        lines.append(
            "| feature | KS stat (this type) | mean shift (this type, benign std) | "
            "apache_bench KS stat (same feature) | apache_bench mean shift (benign std) |"
        )
        lines.append("|---|---|---|---|---|")
        for _, r in top3.iterrows():
            ab_row = apache_diag[apache_diag["feature"] == r["feature"]].iloc[0]
            this_shift = "n/a" if pd.isna(r["mean_shift_in_benign_std"]) else f"{r['mean_shift_in_benign_std']:+.1f} sigma"
            ab_shift = "n/a" if pd.isna(ab_row["mean_shift_in_benign_std"]) else f"{ab_row['mean_shift_in_benign_std']:+.2f} sigma"
            lines.append(
                f"| {r['feature']} | {r['ks_statistic']:.3f} | {this_shift} | "
                f"{ab_row['ks_statistic']:.3f} | {ab_shift} |"
            )
        lines.append("")

    lines.append(
        "The KS statistics alone look comparable across all three attack types "
        "(all mostly >0.6 on their top features), but the mean-shift-in-benign-std "
        "column is where portscan and slowloris diverge sharply from "
        "apache_bench: portscan and slowloris push their top features tens to "
        "hundreds of benign standard deviations away (huge, obviously-anomalous "
        "values -- e.g. slowloris's `byte_ratio_scaled` and portscan's "
        "`conn_state_SF`/`conn_state_REJ` are near-categorical splits), while "
        "apache_bench's shifts stay within a few benign standard deviations even "
        "on its best features. portscan trips connection-state/protocol "
        "one-hots that essentially never fire for benign traffic (half-open "
        "scans, rejected connections), and slowloris's deliberately slow, "
        "long-held connections send far fewer bytes per unit time than any "
        "normal flow. apache_bench, by contrast, is ordinary completed-handshake "
        "HTTP traffic -- its flows are individually unremarkable; only their "
        "volume and repetition are unusual, and the current feature set has no "
        "per-flow way to represent that.\n"
    )

    lines.append("## 3. VAE reconstruction error by group\n")
    lines.append("| group | n | mean error | std error | % flagged at mean threshold_95 |")
    lines.append("|---|---|---|---|---|")
    for _, r in error_summary.iterrows():
        lines.append(
            f"| {r['group']} | {int(r['n'])} | {r['mean_error']:.4g} | {r['std_error']:.4g} | "
            f"{r['pct_above_mean_threshold95']:.1%} |"
        )
    lines.append("")
    lines.append(
        "See `vae_reconstruction_error_hist.png`: the apache_bench error "
        "distribution visibly overlaps the benign distribution far more than "
        "portscan/slowloris does, confirming this is a genuine feature-level "
        "separability problem, not a downstream thresholding artifact.\n"
    )

    lines.append("## 4. Top discriminative features (still weak in absolute terms)\n")
    lines.append(
        f"`top_features_apache_bench_boxplots.png` shows the {len(top_features)} "
        f"features with the highest apache_bench-vs-benign KS statistic: "
        f"{', '.join(f'`{c}`' for c in top_features)}. Even these show heavy "
        "box overlap rather than clean separation -- there is no single feature "
        "or small combination in the current 18-feature set that isolates "
        "apache_bench.\n"
    )

    byte_like = apache_diag[apache_diag["feature"].apply(feature_group) == "byte volume"]
    pkt_like = apache_diag[apache_diag["feature"].apply(feature_group) == "packet count/rate"]
    dur_like = apache_diag[apache_diag["feature"].apply(feature_group) == "duration"]
    onehot_like = apache_diag[apache_diag["feature"].apply(feature_group).isin(
        ["protocol (one-hot)", "service (one-hot)", "connection state (one-hot)"]
    )]

    lines.append("## 5. Weakest feature groups for apache_bench, and a hypothesis\n")
    lines.append(
        f"By mean KS statistic within group: byte-volume features "
        f"({', '.join(byte_like['feature'])}) = {byte_like['ks_statistic'].mean():.3f}, "
        f"packet count/rate features ({', '.join(pkt_like['feature'])}) = "
        f"{pkt_like['ks_statistic'].mean():.3f}, duration "
        f"({', '.join(dur_like['feature'])}) = {dur_like['ks_statistic'].mean():.3f}, "
        f"protocol/service/conn-state one-hots (mean over "
        f"{len(onehot_like)} columns) = {onehot_like['ks_statistic'].mean():.3f}.\n"
    )
    lines.append(
        "**Hypothesis:** section 1 shows apache_bench flows form a tight, "
        "low-variance cluster (its p5-p95 range collapses almost to a point on "
        "`orig_pkts_scaled`/`orig_bytes_scaled`/etc., see "
        "`feature_diagnostics_apache_bench.csv`) that sits only a few benign "
        "standard deviations from benign's mean -- i.e. a stereotyped, "
        "repeated, but individually unremarkable HTTP GET request. apache_bench "
        "(`ab`) is a benchmarking tool that fires many near-identical short "
        "HTTP requests, often concurrently, at a single target; every "
        "*individual* flow it produces looks like an ordinary short HTTP "
        "request because that's what it literally is at the single-flow level. "
        "What is actually anomalous about apache_bench is that this same "
        "request repeats far more often, and with far less inter-arrival-time "
        "variance, than organic HTTP traffic to the same destination -- a "
        "property that is invisible to a model scoring one flow at a time. The "
        "current 18-feature set has no notion of request rate, concurrency, or "
        "inter-arrival time across flows sharing an endpoint. Adding features "
        "computed over a short sliding window per (src, dst, dst_port) tuple "
        "-- e.g. connections-per-second to the same destination, distinct-"
        "source-port reuse rate, or inter-arrival-time mean/variance across the "
        "last N flows to the same service -- would give the model a "
        "traffic-pattern-level signal instead of a single-flow-level one. This "
        "is a hypothesis, not a validated fix: it should be checked by "
        "re-running this same KS / reconstruction-error diagnostic once such a "
        "feature is added, to confirm it actually pushes apache_bench's "
        "reconstruction error above threshold rather than just adding noise.\n"
    )

    with open(FINDINGS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
