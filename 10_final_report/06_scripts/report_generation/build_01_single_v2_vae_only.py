"""
STAGE 2 scope: report figures for VAE v2 ONLY (single_attack_type).
Pairwise/segmented v2 are Stage 3, not run here.

Mirrors build_01_single.py's make_roc_pr_figure()/run_model() pattern
exactly (same report_style, same figure layout) but points at the v2 VAE
backend (deterministic z_mean, 19 features). Old v1 report
(10_final_report/01_single_attack_type/vae/) is untouched; writes only to
10_final_report/01_single_attack_type/vae/.
"""
import os
import shutil
import sys

import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc, precision_recall_curve, average_precision_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
VAE_V2_DIR = os.path.join(PROJECT_ROOT, "10_vae_v2_comparison")
DENSE_V2_DIR = os.path.join(PROJECT_ROOT, "09_dense_v2_comparison")
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "01_single_attack_type")

sys.path.insert(0, os.path.join(PROJECT_ROOT, "06_attack_type_analysis"))
sys.path.insert(0, DENSE_V2_DIR)
sys.path.insert(0, VAE_V2_DIR)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2  # noqa: E402
from evaluate_by_attack_type_dense_v2 import assemble_labeled_features_df_v2  # noqa: E402
from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND, MODEL_LABEL  # noqa: E402

feature_cols = load_feature_cols_v2()
df = assemble_labeled_features_df_v2(feature_cols)


def make_roc_pr_figure(model_name, attack_type, y, mean_error, out_path):
    fpr, tpr, _ = roc_curve(y, mean_error)
    roc_auc = auc(fpr, tpr)
    prec, rec, _ = precision_recall_curve(y, mean_error)
    pr_auc = average_precision_score(y, mean_error)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    ax = axes[0]
    ax.plot(fpr, tpr, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AUC = {roc_auc:.3f}")
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.2, label="chance level")
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — {attack_type}")
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    ax = axes[1]
    ax.plot(rec, prec, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AP = {pr_auc:.3f}")
    baseline = float(y.mean())
    ax.axhline(baseline, color="#999999", linestyle="--", linewidth=1.2, label=f"baseline (prevalence = {baseline:.3f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title(f"Precision-Recall Curve — {attack_type}")
    ax.legend(loc="upper right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    fig.suptitle(f"{model_name}\nvs. benign — {attack_type} — n_attack={int(y.sum())}, n_benign={int((y==0).sum())}",
                 fontsize=10.5)
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}  (ROC-AUC={roc_auc:.4f}, PR-AUC={pr_auc:.4f})")


def run_model(model_name, backend, out_dir, results_csv_src, results_md_src):
    os.makedirs(out_dir, exist_ok=True)
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        X = subset[feature_cols].values.astype("float32")
        y = subset["is_attack"].values
        error_matrix, _ = single.compute_error_matrix(X, backend=backend)
        mean_error = error_matrix.mean(axis=0)
        out_path = os.path.join(out_dir, f"roc_pr_{attack_type}.png")
        make_roc_pr_figure(model_name, attack_type, y, mean_error, out_path)
    shutil.copy(results_csv_src, os.path.join(out_dir, "results.csv"))
    shutil.copy(results_md_src, os.path.join(out_dir, "results.md"))
    print(f"  copied results.csv/.md into {out_dir}")


print("=== VAE v2 (5 seeds, deterministic z_mean, +concurrency_src_1s) ===")
run_model(
    MODEL_LABEL, DEFAULT_VAE_V2_BACKEND, os.path.join(OUT_ROOT, "vae"),
    os.path.join(VAE_V2_DIR, "results_single_attack_type_vae_v2.csv"),
    os.path.join(VAE_V2_DIR, "results_single_attack_type_vae_v2.md"),
)
print("done (Stage 2: VAE v2 only -- pairwise/segmented v2 come in Stage 3)")
