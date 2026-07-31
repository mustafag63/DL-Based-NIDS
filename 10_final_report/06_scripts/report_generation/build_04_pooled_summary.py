"""
User wants the 4-panel (PR-AUC / F1 / Benign FPR / Attack Recall) summary WITHOUT
the per-attack-type split -- one pooled number per model (benign + all 3 attack
types together in the same evaluation run), for all four of
dense_v1 / vae_v1 / dense_v2 / vae_v2.

Same underlying flows (test_with_attack_type.csv, 9931 rows) for all four, so
this is an apples-to-apples population across v1<->v2 and dense<->vae, unlike
the earlier per-seed notebook numbers which came from each notebook's own
original split.

Live model weight caveat (same as build_04_vae_v1_5seed.py): the v1 model
directories (phase3_dense/04_phase3_models/full_features and
phase3_vae/.../04_models/contam_0pct) were overwritten in place by the v2
retrain -- v1 (18-feature) weights only survive under V1_ARCHIVE/. v2 backends
use the live (current) paths, which are correct for v2.

Writes 07_pooled_summary_4panel.png into each of
04_model_notebooks_results/{dense_v1,vae_v1,dense_v2,vae_v2}/ and appends a
pooled-results table + figure link to each results.md.
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "04_model_notebooks_results")

sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

sys.path.insert(0, os.path.join(PROJECT_ROOT, "06_attack_type_analysis"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "08_dense_v1_comparison"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "09_dense_v2_comparison"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "10_vae_v2_comparison"))
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend import DenseBackend  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2, DEFAULT_DENSE_V2_BACKEND  # noqa: E402
from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND  # noqa: E402
from evaluate_by_attack_type_dense_v2 import assemble_labeled_features_df_v2  # noqa: E402

SEEDS = [0, 1, 2, 3, 4]
V1_ARCHIVE = os.path.join(PROJECT_ROOT, "V1_ARCHIVE")

PANELS = [
    ("pr_auc", "PR-AUC"),
    ("f1", "F1 (threshold_95)"),
    ("benign_fpr", "Benign FPR (threshold_95)"),
    ("attack_recall", "Attack Recall (threshold_95, pooled)"),
]


def pooled_metrics(df, feature_cols, backend, label):
    rows = single.evaluate_group(df, feature_cols, label, backend=backend)
    out = {}
    for key in ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]:
        vals = np.array([r[key] for r in rows])
        out[key] = (float(vals.mean()), float(vals.std()))
    out["n_seeds"] = len(rows)
    out["n_benign"] = rows[0]["n_benign"]
    out["n_attack"] = rows[0]["n_attack"]
    return out


def make_figure(model_name, data, color, out_path):
    fig, axes = plt.subplots(2, 2, figsize=(9, 8))
    for ax, (key, title) in zip(axes.flat, PANELS):
        m, s = data[key]
        bar = ax.bar(["pooled\n(all 3 types)"], [m], yerr=[s], capsize=6, color=color, width=0.4)
        ax.text(0, m + 0.03, f"{m:.3f}", ha="center", fontsize=12)
        ax.set_title(title)
        ax.set_ylim(0, 1.15)
    fig.suptitle(f"{model_name} — pooled (benign + apache_bench + portscan + slowloris together)\n"
                 f"{data['n_seeds']}-seed mean +/- std, n_benign={data['n_benign']}, n_attack={data['n_attack']}",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def append_section(out_dir, data, png_name):
    md_path = os.path.join(out_dir, "results.md")
    with open(md_path) as f:
        content = f.read()
    marker = "## Pooled (all attack types together) summary"
    if marker in content:
        return
    section = f"""
{marker}

Ayrı ayrı attack-type kırılımı yerine, benign + apache_bench + portscan + slowloris
hepsi AYNI koşuda birlikte değerlendirilmiş (test_with_attack_type.csv, pooled,
n_benign={data['n_benign']}, n_attack={data['n_attack']}), {data['n_seeds']}-seed mean +/- std:

| metric | pooled mean +/- std |
|---|---|
| ROC-AUC | {data['roc_auc'][0]:.4f} +/- {data['roc_auc'][1]:.4f} |
| PR-AUC | {data['pr_auc'][0]:.4f} +/- {data['pr_auc'][1]:.4f} |
| F1 (thr95) | {data['f1'][0]:.4f} +/- {data['f1'][1]:.4f} |
| benign FPR (thr95) | {data['benign_fpr'][0]:.4f} +/- {data['benign_fpr'][1]:.4f} |
| attack recall (thr95, pooled) | {data['attack_recall'][0]:.4f} +/- {data['attack_recall'][1]:.4f} |

![Pooled summary]({png_name})
"""
    content = content.rstrip("\n") + "\n" + section
    with open(md_path, "w") as f:
        f.write(content)
    print(f"appended pooled section to {md_path}")


# ---- Dense v1 (V1_ARCHIVE weights, 18 feature) ----
print("=== Dense v1 pooled ===")
feature_cols_v1 = single.load_feature_cols()
df_v1 = single.assemble_labeled_features_df(feature_cols_v1)
dense_v1_backend = DenseBackend(
    model_dir=os.path.join(V1_ARCHIVE, "phase3_dense", "04_phase3_models", "full_features"),
    seeds=SEEDS)
dense_v1_data = pooled_metrics(df_v1, feature_cols_v1, dense_v1_backend, "dense_v1_pooled")
make_figure("Dense autoencoder v1 (full_features, 18 feature)", dense_v1_data, sty.COLOR_DENSE,
            os.path.join(OUT_ROOT, "dense_v1", "07_pooled_summary_4panel.png"))
append_section(os.path.join(OUT_ROOT, "dense_v1"), dense_v1_data, "07_pooled_summary_4panel.png")

# ---- VAE v1 (V1_ARCHIVE weights, 18 feature, deterministic z_mean) ----
print("=== VAE v1 pooled ===")
vae_v1_backend = single.VAEBackend(
    model_dir=os.path.join(V1_ARCHIVE, "phase3_vae", "05_contamination_sweep", "04_models", "contam_0pct"),
    deterministic=True, seeds=SEEDS)
vae_v1_data = pooled_metrics(df_v1, feature_cols_v1, vae_v1_backend, "vae_v1_pooled")
make_figure("VAE v1 (contam_0pct, 18 feature, deterministic z_mean)", vae_v1_data, sty.COLOR_VAE,
            os.path.join(OUT_ROOT, "vae_v1", "07_pooled_summary_4panel.png"))
append_section(os.path.join(OUT_ROOT, "vae_v1"), vae_v1_data, "07_pooled_summary_4panel.png")

# ---- Dense v2 (live weights, 19 feature) ----
print("=== Dense v2 pooled ===")
feature_cols_v2 = load_feature_cols_v2()
df_v2 = assemble_labeled_features_df_v2(feature_cols_v2)
dense_v2_backend = DEFAULT_DENSE_V2_BACKEND
dense_v2_backend.seeds = SEEDS
dense_v2_data = pooled_metrics(df_v2, feature_cols_v2, dense_v2_backend, "dense_v2_pooled")
make_figure("Dense autoencoder v2 (full_features + concurrency_src_1s, 19 feature)", dense_v2_data, sty.COLOR_DENSE,
            os.path.join(OUT_ROOT, "dense_v2", "07_pooled_summary_4panel.png"))
append_section(os.path.join(OUT_ROOT, "dense_v2"), dense_v2_data, "07_pooled_summary_4panel.png")

# ---- VAE v2 (live weights, 19 feature, deterministic z_mean) ----
print("=== VAE v2 pooled ===")
vae_v2_backend = DEFAULT_VAE_V2_BACKEND
vae_v2_backend.seeds = SEEDS
vae_v2_data = pooled_metrics(df_v2, feature_cols_v2, vae_v2_backend, "vae_v2_pooled")
make_figure("VAE v2 (contam_0pct, 19 feature: +concurrency_src_1s, deterministic z_mean)", vae_v2_data, sty.COLOR_VAE,
            os.path.join(OUT_ROOT, "vae_v2", "07_pooled_summary_4panel.png"))
append_section(os.path.join(OUT_ROOT, "vae_v2"), vae_v2_data, "07_pooled_summary_4panel.png")

print("done")
