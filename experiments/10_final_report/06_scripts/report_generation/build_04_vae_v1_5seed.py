"""
The user asked for the VAE v1 number in 04_model_notebooks_results/vae_v1/
to be a 5-seed result instead of the single-seed number the original
health-check notebook produced (that notebook's job was architecture
selection -- latent_dim/beta -- not a multi-seed score, see its own caveat
in results.md).

This computes a proper 5-seed (seeds 0-4, matching Dense v1's 5 seeds)
pooled evaluation of the already-trained canonical v1 VAE (contam_0pct,
18 features, deterministic z_mean scoring -- same convention as the
per-attack-type v1 table in 01_single_attack_type/vae/), against the SAME
pooled test set framing as the Dense v1 notebook's single overall TEST AUC
number: benign + all three attack types together, not broken out per type.

Writes into 04_model_notebooks_results/vae_v1/ as a new section (existing
content is kept, not overwritten) plus two new figures.
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_DIR = os.path.join(PROJECT_ROOT, "10_final_report", "04_model_notebooks_results", "vae_v1")

sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

sys.path.insert(0, os.path.join(PROJECT_ROOT, "06_attack_type_analysis"))
import evaluate_by_attack_type as single  # noqa: E402

SEEDS = [0, 1, 2, 3, 4]
BENIGN_COLOR = "#0072B2"
ATTACK_COLOR = "#D55E00"

feature_cols = single.load_feature_cols()
df = single.assemble_labeled_features_df(feature_cols)  # pooled: benign + all 3 attack types

# The live phase3_vae/.../04_models/contam_0pct/ checkpoints were overwritten in
# place by the v2 (19-feature) retrain -- input_shape is now (None, 19), not
# loadable against the 18-feature v1 table. The original v1 (18-feature) weights
# only still exist under V1_ARCHIVE/, so point the backend there explicitly.
# val_benign.csv (used for threshold_95) is untouched at the live path (still 18
# columns, no concurrency_src_1s), so that stays as VAEBackend's default.
V1_ARCHIVE_VAE_MODEL_DIR = os.path.join(
    PROJECT_ROOT, "V1_ARCHIVE", "phase3_vae", "05_contamination_sweep", "04_models", "contam_0pct")
backend = single.VAEBackend(model_dir=V1_ARCHIVE_VAE_MODEL_DIR, deterministic=True, seeds=SEEDS)

rows = single.evaluate_group(df, feature_cols, "pooled_all_types", backend=backend)

roc_aucs = np.array([r["roc_auc"] for r in rows])
pr_aucs = np.array([r["pr_auc"] for r in rows])
f1s = np.array([r["f1"] for r in rows])
fprs = np.array([r["benign_fpr"] for r in rows])
recalls = np.array([r["attack_recall"] for r in rows])
thresholds = np.array([r["threshold_95"] for r in rows])

error_matrix, _ = single.compute_error_matrix(df[feature_cols].values.astype("float32"), backend=backend)
mean_error = error_matrix.mean(axis=0)
mean_threshold = float(thresholds.mean())
y = df["is_attack"].values

# --- ROC figure (mean-of-5-seed error) ---
fpr, tpr, _ = roc_curve(y, mean_error)
fig, ax = plt.subplots(figsize=(6.5, 6.5))
ax.plot(fpr, tpr, color=BENIGN_COLOR, linewidth=2.5,
        label=f"ROC curve (mean-error AUC = {roc_aucs.mean():.4f})")
ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.2, label="random baseline")
ax.set_xlabel("False Positive Rate")
ax.set_ylabel("True Positive Rate")
ax.set_title(f"ROC Curve — Test Set, all attack types pooled ({len(SEEDS)} seeds)")
ax.legend(loc="lower right", frameon=False)
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
fig.suptitle("VAE v1 (contam_0pct, 18 features, deterministic z_mean)", fontsize=11)
fig.tight_layout(rect=[0, 0, 1, 0.94])
roc_path = os.path.join(OUT_DIR, "04_roc_curve_5seed.png")
fig.savefig(roc_path, dpi=170, bbox_inches="tight")
plt.close(fig)
print(f"wrote {roc_path}  (per-seed ROC-AUC mean={roc_aucs.mean():.4f} +/- {roc_aucs.std():.4f})")

# --- histogram figure (mean-of-5-seed error) ---
benign_errors = mean_error[y == 0]
attack_errors = mean_error[y == 1]
fig, ax = plt.subplots(figsize=(9, 5.2))
bins = np.linspace(0, np.percentile(mean_error, 99), 60)
ax.hist(benign_errors, bins=bins, alpha=0.6, label="benign", color=BENIGN_COLOR, density=True)
ax.hist(attack_errors, bins=bins, alpha=0.6, label="attack", color=ATTACK_COLOR, density=True)
ax.axvline(mean_threshold, color="black", linestyle="--",
           label=f"mean threshold (val pctl95={mean_threshold:.4f})")
ax.set_xlabel("Reconstruction error (deterministic z_mean)")
ax.set_ylabel("Density")
ax.set_title(f"Test-set reconstruction error: benign vs attack, all attack types pooled ({len(SEEDS)} seeds)")
ax.legend(frameon=False)
fig.suptitle("VAE v1 (contam_0pct, 18 features, deterministic z_mean)", fontsize=11)
fig.tight_layout(rect=[0, 0, 1, 0.94])
hist_path = os.path.join(OUT_DIR, "05_reconstruction_error_histogram_5seed.png")
fig.savefig(hist_path, dpi=170, bbox_inches="tight")
plt.close(fig)
print(f"wrote {hist_path}")

# --- append section to results.md ---
md_path = os.path.join(OUT_DIR, "results.md")
with open(md_path) as f:
    content = f.read()

marker = "## 7. 5-seed pooled sonuç"
if marker not in content:
    section = f"""
{marker} (kullanıcı isteği üzerine eklendi)

Bölüm 4-6'daki tek-seed sayılar, mimari seçim sürecinin (latent-dim/beta sweep) bir yan
ürünüydü. Burada Dense v1 notebook'unun demo-run'ıyla aynı çerçevede (benign + 3 attack
tipi birlikte, pooled), aynı 5 seed (0-4), kanonik `contam_0pct` modeli ve deterministik
z_mean skorlama ile 5-seed ortalama sonuç var -- bu, `01_single_attack_type/vae/results.md`'deki
20-seed attack-type-bazlı tablonun pooled/5-seed karşılığı.

| metric | 5-seed mean +/- std |
|---|---|
| ROC-AUC | {roc_aucs.mean():.4f} +/- {roc_aucs.std():.4f} |
| PR-AUC | {pr_aucs.mean():.4f} +/- {pr_aucs.std():.4f} |
| F1 (thr95) | {f1s.mean():.4f} +/- {f1s.std():.4f} |
| benign FPR (thr95) | {fprs.mean():.4f} +/- {fprs.std():.4f} |
| attack recall (thr95, pooled) | {recalls.mean():.4f} +/- {recalls.std():.4f} |

n_benign={int((y == 0).sum())}, n_attack={int((y == 1).sum())} (test_with_attack_type.csv, pooled).

ROC (mean-of-5-seed error): bkz. `04_roc_curve_5seed.png`. Reconstruction error histogramı
(mean-of-5-seed error): bkz. `05_reconstruction_error_histogram_5seed.png`.
"""
    content = content.rstrip("\n") + "\n" + section
    with open(md_path, "w") as f:
        f.write(content)
    print(f"appended 5-seed section to {md_path}")
else:
    print(f"5-seed section already present in {md_path}, not re-appended")

print("done")
