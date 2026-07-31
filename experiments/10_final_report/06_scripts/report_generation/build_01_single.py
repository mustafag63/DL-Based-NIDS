import os, sys, shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc, precision_recall_curve, average_precision_score

sys.path.insert(0, "/private/tmp/claude-501/-Users-mustafa-Desktop-NIDS-IDS-Project/27367645-50b6-4f4c-ad67-446d3fe33e07/scratchpad")
import report_style as sty
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DENSE_DIR = os.path.join(PROJECT_ROOT, "08_dense_v1_comparison")
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "01_single_attack_type")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_DIR)
import evaluate_by_attack_type as single
from dense_backend import DEFAULT_DENSE_BACKEND, MODEL_LABEL as DENSE_LABEL

feature_cols = single.load_feature_cols()
df = single.assemble_labeled_features_df(feature_cols)


def make_roc_pr_figure(model_name, attack_type, y, mean_error, out_path):
    fpr, tpr, _ = roc_curve(y, mean_error)
    roc_auc = auc(fpr, tpr)
    prec, rec, _ = precision_recall_curve(y, mean_error)
    pr_auc = average_precision_score(y, mean_error)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    ax = axes[0]
    ax.plot(fpr, tpr, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AUC = {roc_auc:.3f}")
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.2, label="chance level")
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — {model_name} — {attack_type}")
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    ax = axes[1]
    ax.plot(rec, prec, color=sty.COLOR_TYPE[attack_type], linewidth=2.5, label=f"AP = {pr_auc:.3f}")
    baseline = float(y.mean())
    ax.axhline(baseline, color="#999999", linestyle="--", linewidth=1.2, label=f"baseline (prevalence = {baseline:.3f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title(f"Precision-Recall Curve — {model_name} — {attack_type}")
    ax.legend(loc="upper right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    fig.suptitle(f"{model_name} vs. benign — {attack_type} — n_attack={int(y.sum())}, n_benign={int((y==0).sum())}")
    fig.tight_layout()
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


print("=== VAE (20 seeds) ===")
run_model(
    "VAE", single.DEFAULT_BACKEND, os.path.join(OUT_ROOT, "vae"),
    single.RESULTS_CSV, single.RESULTS_MD,
)

print("=== Dense v1 (5 seeds) ===")
run_model(
    DENSE_LABEL, DEFAULT_DENSE_BACKEND, os.path.join(OUT_ROOT, "dense_v1"),
    os.path.join(DENSE_DIR, "results_single_attack_type_dense.csv"),
    os.path.join(DENSE_DIR, "results_single_attack_type_dense.md"),
)
print("done")
