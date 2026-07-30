"""
Figures for the concurrency-feature experiment README:
  fig_ks_before_after.png    -- byte_ratio_var KS collapse after winsorize+log
  fig_metric_comparison.png  -- baseline (18f) vs 13's IAT vs A/B/C, per attack type
  fig_knockout_C.png         -- config C: full model vs each feature knocked out
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
C1 = "#2a78d6"   # blue   - baseline
C2 = "#008300"   # green  - config A / winsorized-after
C3 = "#eda100"   # yellow - config B / IAT (exp 13)
C4 = "#e87ba4"   # magenta - config C / raw-before

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e6e5e2", "grid.linewidth": 0.6,
    "font.size": 10,
})

# ------------------------------------------------- fig 1: KS before/after
radii = ["1s", "2s", "5s"]
ks_before = [0.961, 1.000, 1.000]     # log1p(raw), no winsorize -- from ks_test.py run
ks_after = [0.948, 0.986, 0.987]      # log1p(winsorized) -- recomputed after fix

fig, ax = plt.subplots(figsize=(6.5, 4), dpi=160)
x = np.arange(len(radii))
w = 0.34
b1 = ax.bar(x - w / 2, ks_before, width=w, color=C4, label="log1p (winsorize öncesi)")
b2 = ax.bar(x + w / 2, ks_after, width=w, color=C2, label="winsorize(p1-p99)+log1p (düzeltilmiş)")
for bars in (b1, b2):
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{b.get_height():.3f}",
                ha="center", va="bottom", fontsize=8.5)
ax.axhline(0.76, color=INK2, linestyle="--", linewidth=1)
ax.text(2.35, 0.775, "en iyi 18-feature (0.62–0.76)", fontsize=7.5, color=INK2, ha="right")
ax.set_xticks(x, [f"byte_ratio_var_src_{r}" for r in radii])
ax.set_ylim(0, 1.08)
ax.set_ylabel("KS istatistiği (apache_bench vs benign)")
ax.set_title("Winsorize+log sonrası KS düşüyor ama güçlü kalıyor", fontsize=10.5, loc="left")
ax.legend(frameon=False, fontsize=8.5, loc="lower right")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig_ks_before_after.png"))
plt.close(fig)

# ------------------------------------------------- fig 2: metric comparison
base = pd.read_csv(os.path.join(PROJECT_ROOT, "08_dense_v1_comparison", "results_single_attack_type_dense.csv"))
iat = pd.read_csv(os.path.join(PROJECT_ROOT, "13_temporal_feature_experiment", "results_single_attack_type_iat.csv"))
A = pd.read_csv(os.path.join(HERE, "results_A.csv"))
B = pd.read_csv(os.path.join(HERE, "results_B.csv"))
C = pd.read_csv(os.path.join(HERE, "results_C.csv"))

series = [
    ("18f baseline (5 seed)", base, C1),
    ("13: +IAT (3 seed)", iat, "#b7b6ae"),
    ("A: +concurrency_src_1s", A, C2),
    ("B: +byte_ratio_var (wins.)", B, C3),
    ("C: A+dst+B kombinasyonu", C, C4),
]
types = ["apache_bench", "portscan", "slowloris"]
metrics = [("attack_recall", "Attack recall @thr95"),
           ("roc_auc", "ROC-AUC"),
           ("benign_fpr", "Benign FPR @thr95")]

fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), dpi=160)
x = np.arange(len(types))
n = len(series)
w = 0.16
for ax, (mcol, mtitle) in zip(axes, metrics):
    for i, (name, src, color) in enumerate(series):
        off = (i - (n - 1) / 2) * w
        vals = [float(src.loc[src[src.columns[0]] == t, f"{mcol}_mean"].iloc[0]) for t in types]
        errs = [float(src.loc[src[src.columns[0]] == t, f"{mcol}_std"].iloc[0]) for t in types]
        ax.bar(x + off, vals, width=w - 0.015, color=color, label=name,
               yerr=errs, error_kw={"ecolor": INK2, "capsize": 1.5, "linewidth": 0.8})
    ax.set_xticks(x, ["apache_bench", "portscan", "slowloris"])
    ax.set_ylim(0, 1.15 if mcol != "benign_fpr" else 0.16)
    ax.set_title(mtitle, fontsize=10.5)
axes[0].set_ylabel("değer")
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=5, frameon=False,
           bbox_to_anchor=(0.5, 1.06), fontsize=8.5)
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig(os.path.join(HERE, "fig_metric_comparison.png"), bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------- fig 3: config C knockout
ko_src = pd.read_csv(os.path.join(HERE, "results_C_knockout_concurrency_src_1s_scaled.csv"))
ko_dst = pd.read_csv(os.path.join(HERE, "results_C_knockout_concurrency_dst_2s_scaled.csv"))
ko_var = pd.read_csv(os.path.join(HERE, "results_C_knockout_byte_ratio_var_src_2s_wins_log_scaled.csv"))
ko_all = pd.read_csv(os.path.join(HERE, "results_C_knockout_ALL.csv"))

ab_row = lambda d, col: float(d.loc[d[d.columns[0]] == "apache_bench", col].iloc[0])
configs_ko = [
    ("Tam model (C)", C, C1),
    ("src_1s dondurulmuş", ko_src, C4),
    ("dst_2s dondurulmuş", ko_dst, C3),
    ("byte_ratio_var dondurulmuş", ko_var, "#9085e9"),
    ("Hepsi dondurulmuş\n(≈18f baseline)", ko_all, "#b7b6ae"),
]
fig, axes = plt.subplots(1, 2, figsize=(9, 4), dpi=160)
labels = [c[0] for c in configs_ko]
recalls = [ab_row(c[1], "attack_recall_mean") for c in configs_ko]
fprs = [ab_row(c[1], "benign_fpr_mean") for c in configs_ko]
colors = [c[2] for c in configs_ko]

for ax, vals, title, ylim in [(axes[0], recalls, "apache_bench recall @thr95", 1.15),
                               (axes[1], fprs, "benign FPR @thr95", 0.16)]:
    bars = ax.bar(np.arange(len(labels)), vals, color=colors, width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + ylim * 0.015, f"{v:.3f}",
                ha="center", va="bottom", fontsize=8)
    ax.set_xticks(np.arange(len(labels)), labels, fontsize=7.5, rotation=20, ha="right")
    ax.set_ylim(0, ylim)
    ax.set_title(title, fontsize=10)
fig.suptitle("Konfigürasyon C: tek tek feature dondurma (knock-out) — src_1s en büyük katkıyı taşıyor",
             fontsize=10, y=1.03)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig_knockout_C.png"), bbox_inches="tight")
plt.close(fig)

print("wrote fig_ks_before_after.png, fig_metric_comparison.png, fig_knockout_C.png")
