import os, sys, shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import ks_2samp

sys.path.insert(0, "/private/tmp/claude-501/-Users-mustafa-Desktop-NIDS-IDS-Project/27367645-50b6-4f4c-ad67-446d3fe33e07/scratchpad")
import report_style as sty
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
OLD_DIAG_DIR = os.path.join(PROJECT_ROOT, "10_final_deliverables_31_temmuz", "06_diagnostics")
OUT_DIR = os.path.join(PROJECT_ROOT, "10_final_report", "04_apache_bench_diagnostics")
os.makedirs(OUT_DIR, exist_ok=True)

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, OLD_DIAG_DIR)
import evaluate_by_attack_type as single
import diagnose_apache_bench as diag
import test_apache_bench_temporal_hypothesis as temporal

feature_cols = single.load_feature_cols()
df = single.assemble_labeled_features_df(feature_cols)
benign_df = df[df["is_attack"] == 0]
apache_df = df[df["attack_type"] == "apache_bench"]
portscan_df = df[df["attack_type"] == "portscan"]
slowloris_df = df[df["attack_type"] == "slowloris"]

# --- 1. feature_diagnostics_*.csv: regenerate (cheap, no model) so they're
# byte-identical in content to the source, just freshly computed here. ---
for atype, gdf in [("apache_bench", apache_df), ("portscan", portscan_df), ("slowloris", slowloris_df)]:
    out = diag.compare_distributions(feature_cols, benign_df, gdf)
    out.to_csv(os.path.join(OUT_DIR, f"feature_diagnostics_{atype}.csv"), index=False)
print("wrote feature_diagnostics_*.csv")

# --- 2. top feature box plots: reuse diag's actual plotting function (title
# already states apache_bench explicitly; big-font rcParams applied globally) ---
apache_diag = pd.read_csv(os.path.join(OUT_DIR, "feature_diagnostics_apache_bench.csv"))
top_features = apache_diag.sort_values("ks_statistic", ascending=False)["feature"].head(diag.N_TOP_FEATURES).tolist()
diag.plot_top_feature_boxplots(top_features, benign_df, apache_df,
                                os.path.join(OUT_DIR, "top_features_apache_bench_boxplots.png"))
print("wrote top_features_apache_bench_boxplots.png")

# --- 3. VAE reconstruction error histogram: FULL 20-seed ensemble (not the
# notebook's 5-seed demo), custom title that names the model explicitly. ---
combined = pd.concat([benign_df, apache_df, portscan_df, slowloris_df], ignore_index=True)
X = combined[feature_cols].values.astype("float32")
error_matrix, thresholds = single.compute_error_matrix(X, backend=single.DEFAULT_BACKEND)
mean_errors = error_matrix.mean(axis=0)
mean_threshold = float(np.mean(thresholds))

n_b = len(benign_df)
offsets = {"benign": (0, n_b)}
cursor = n_b
for name, gdf in [("apache_bench", apache_df), ("portscan", portscan_df), ("slowloris", slowloris_df)]:
    offsets[name] = (cursor, cursor + len(gdf)); cursor += len(gdf)
errors_by_group = {
    "benign": mean_errors[offsets["benign"][0]:offsets["benign"][1]],
    "apache_bench": mean_errors[offsets["apache_bench"][0]:offsets["apache_bench"][1]],
    "portscan+slowloris": np.concatenate([
        mean_errors[offsets["portscan"][0]:offsets["portscan"][1]],
        mean_errors[offsets["slowloris"][0]:offsets["slowloris"][1]],
    ]),
}
error_summary = pd.DataFrame([
    {"group": name, "n": len(errs), "mean_error": float(np.mean(errs)), "std_error": float(np.std(errs)),
     "pct_above_mean_threshold95": float((errs > mean_threshold).mean())}
    for name, errs in errors_by_group.items()
])
error_summary.to_csv(os.path.join(OUT_DIR, "vae_reconstruction_error_summary.csv"), index=False)

colors = {"benign": sty.COLOR_BENIGN, "apache_bench": sty.COLOR_APACHE_BENCH, "portscan+slowloris": "#56B4E9"}
eps = 1e-6
all_errors = np.concatenate(list(errors_by_group.values()))
bins_full = np.logspace(np.log10(max(all_errors.min(), eps)), np.log10(all_errors.max()), 60)
zoom_errors = np.concatenate([errors_by_group["benign"], errors_by_group["apache_bench"]])
bins_zoom = np.logspace(np.log10(max(zoom_errors.min(), eps)), np.log10(zoom_errors.max()), 50)

fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(15, 6.5))
for ax, bins, groups in [(ax_full, bins_full, errors_by_group.keys()), (ax_zoom, bins_zoom, ["benign", "apache_bench"])]:
    for name in groups:
        errs = errors_by_group[name]
        ax.hist(errs, bins=bins, density=True, histtype="stepfilled", alpha=0.35, color=colors[name], label=f"{name} (n={len(errs)})")
        ax.hist(errs, bins=bins, density=True, histtype="step", linewidth=2.5, color=colors[name])
    ax.axvline(mean_threshold, color="#555555", linestyle="--", linewidth=1.8, label=f"mean threshold_95 = {mean_threshold:.4g}")
    ax.set_xscale("log")
    ax.set_xlabel("VAE Reconstruction Error (log scale, mean of 20 seeds)")
    ax.set_ylabel("Density")
    ax.legend(frameon=False, fontsize=11)
ax_full.set_title("VAE — Reconstruction Error — All Groups (Full Range)")
ax_zoom.set_title("VAE — Reconstruction Error — Zoom: benign vs. apache_bench")
fig.suptitle("VAE (clean-only, contam_0pct) Reconstruction Error by Attack Type", fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "vae_reconstruction_error_hist.png"), dpi=170, bbox_inches="tight")
plt.close(fig)
print("wrote vae_reconstruction_error_hist.png + vae_reconstruction_error_summary.csv")

# --- 4. temporal IAT: reuse temporal's actual functions, full data (cheap, no model) ---
benign_iat = temporal.consecutive_iat(df, df["is_attack"] == 0)
apache_iat = temporal.consecutive_iat(df, df["attack_type"] == "apache_bench")
ks_stat, ks_pvalue = ks_2samp(benign_iat, apache_iat)

summary_rows = []
for name, arr in [("benign", benign_iat), ("apache_bench", apache_iat)]:
    row = {"group": name, "n": len(arr), "mean": np.mean(arr), "std": np.std(arr)}
    for p in temporal.PERCENTILES:
        row[f"p{p}"] = np.percentile(arr, p)
    summary_rows.append(row)
temporal_summary = pd.DataFrame(summary_rows)
temporal_summary["ks_statistic"] = ks_stat
temporal_summary["ks_pvalue"] = ks_pvalue
temporal_summary.to_csv(os.path.join(OUT_DIR, "temporal_iat_summary.csv"), index=False)

# Not calling temporal.plot_iat_histogram() directly: its hard-coded
# figsize=(8.5, 5.5) is too small for this report's larger title font and
# clips the title. Same data prep (already computed above), larger canvas.
eps_iat = 1e-4
all_iat = np.concatenate([benign_iat, apache_iat])
bins_iat = np.logspace(np.log10(max(all_iat.min(), eps_iat)), np.log10(all_iat.max()), 60)
fig, ax = plt.subplots(figsize=(11, 6.5))
for name, arr, color in [("benign", benign_iat, sty.COLOR_BENIGN), ("apache_bench", apache_iat, sty.COLOR_APACHE_BENCH)]:
    ax.hist(arr, bins=bins_iat, density=True, histtype="stepfilled", alpha=0.35, color=color, label=f"{name} (n={len(arr)})")
    ax.hist(arr, bins=bins_iat, density=True, histtype="step", linewidth=2.5, color=color)
ax.set_xscale("log")
ax.set_xlabel("Inter-Arrival Time Between Consecutive Same-Label Flows (seconds, log scale)")
ax.set_ylabel("Density")
ax.set_title("Inter-Arrival Time — benign vs. apache_bench\n(within-window_id, consecutive same-label flows)")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "iat_apache_bench_vs_benign_hist.png"), dpi=170, bbox_inches="tight")
plt.close(fig)
print("wrote iat_apache_bench_vs_benign_hist.png + temporal_iat_summary.csv")

# --- 5. findings.md: copy as-is (already has all 6 sections, incl. temporal) ---
shutil.copy(os.path.join(OLD_DIAG_DIR, "diagnose_apache_bench_findings.md"), os.path.join(OUT_DIR, "findings.md"))
print("copied findings.md")
print("done")
