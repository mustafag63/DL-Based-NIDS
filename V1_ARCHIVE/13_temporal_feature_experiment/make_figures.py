"""
Figures for the temporal-feature experiment README:
  fig_iat_hist.png        -- scaled log-IAT distribution, benign vs apache_bench
                             (test set), the feature the experiment added
  fig_metric_comparison.png -- Dense v1 baseline (18f, 5 seed) vs +IAT (19f,
                             3 seed): recall / ROC-AUC / benign FPR per type
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
C_BENIGN = "#2a78d6"   # categorical slot 1 (blue)
C_ATTACK = "#e87ba4"   # slot 3 (magenta)
C_BASE = "#2a78d6"
C_IAT = "#008300"      # slot 2 (green)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e6e5e2", "grid.linewidth": 0.6,
    "font.size": 10,
})

# ------------------------------------------------------------- fig 1: IAT hist
iat = pd.read_csv(os.path.join(HERE, "iat_feature_all_rows.csv"))
lab = pd.read_csv(os.path.join(PROJECT_ROOT, "06_attack_type_analysis",
                               "test_with_attack_type.csv"))
m = lab.merge(iat[["row_index", "iat_log_scaled"]], on="row_index")
benign = m.loc[m["attack_type"] == "benign", "iat_log_scaled"]
ab = m.loc[m["attack_type"] == "apache_bench", "iat_log_scaled"]

fig, ax = plt.subplots(figsize=(8, 4.2), dpi=160)
bins = np.linspace(min(benign.min(), ab.min()), max(benign.max(), ab.max()), 70)
ax.hist(benign, bins=bins, density=True, histtype="stepfilled",
        color=C_BENIGN, alpha=0.45, edgecolor=C_BENIGN, linewidth=1.5)
ax.hist(ab, bins=bins, density=True, histtype="stepfilled",
        color=C_ATTACK, alpha=0.45, edgecolor=C_ATTACK, linewidth=1.5)
ax.text(1.6, 0.62, f"benign (n={len(benign)})", color=C_BENIGN, fontweight="bold")
ax.text(-1.15, 1.9, f"apache_bench (n={len(ab)})", color="#c94f7f", fontweight="bold")
ax.set_xlabel("iat_log_scaled  —  log10(kaynak-IP IAT + 1e-6), benign-train'e göre standardize")
ax.set_ylabel("yoğunluk")
ax.set_title("Yeni feature test setinde: apache_bench, benign'in bursty modunun İÇİNDE oturuyor (KS=0.375)",
             fontsize=10.5, loc="left")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig_iat_hist.png"))
plt.close(fig)

# ---------------------------------------------- fig 2: baseline vs +IAT bars
base = pd.read_csv(os.path.join(PROJECT_ROOT, "08_dense_v1_comparison",
                                "results_single_attack_type_dense.csv"))
new = pd.read_csv(os.path.join(HERE, "results_single_attack_type_iat.csv"))
types = ["apache_bench", "portscan", "slowloris"]
metrics = [("attack_recall", "Attack recall @thr95"),
           ("roc_auc", "ROC-AUC"),
           ("benign_fpr", "Benign FPR @thr95")]

fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), dpi=160)
x = np.arange(len(types))
w = 0.36
for ax, (mcol, mtitle) in zip(axes, metrics):
    for off, src, color, name in [(-w / 2, base, C_BASE, "18 feature (baseline, 5 seed)"),
                                  (w / 2, new, C_IAT, "19 feature (+IAT, 3 seed)")]:
        vals = [float(src.loc[src[src.columns[0]] == t, f"{mcol}_mean"].iloc[0]) for t in types]
        errs = [float(src.loc[src[src.columns[0]] == t, f"{mcol}_std"].iloc[0]) for t in types]
        bars = ax.bar(x + off, vals, width=w - 0.03, color=color, label=name,
                      yerr=errs, error_kw={"ecolor": INK2, "capsize": 2, "linewidth": 1})
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, f"{v:.3f}",
                    ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xticks(x, ["apache\nbench", "portscan", "slowloris"])
    ax.set_ylim(0, 1.12)
    ax.set_title(mtitle, fontsize=10)
axes[0].set_ylabel("değer")
axes[2].set_ylim(0, 0.12)
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False,
           bbox_to_anchor=(0.5, 1.06), fontsize=9)
fig.suptitle("")
fig.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig(os.path.join(HERE, "fig_metric_comparison.png"), bbox_inches="tight")
plt.close(fig)
print("wrote fig_iat_hist.png, fig_metric_comparison.png")
