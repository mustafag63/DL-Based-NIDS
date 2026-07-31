"""
"Sade" (lightweight) v2 counterpart to 04_model_notebooks_results/{dense_v1,vae_v1}.

No v2 notebook was ever run (see 04_model_notebooks/README.md) and no
per-epoch training history was saved for the v2 models, so this does NOT
reproduce the v1 notebooks' loss curves, ablation sweep, or latent-dim/beta
search -- that would require retraining. Instead it loads the already-trained
canonical v2 models (seed=0, 19 features incl. concurrency_src_1s) via the
existing v2 backends and reproduces just the two purely-inference figures
from the v1 notebooks: the test-set ROC curve and the benign-vs-attack
reconstruction-error histogram, pooled across all attack types (same framing
as v1's "Bölüm 4/ROC" and "reconstruction error histogram" sections).

Writes into 10_final_report/04_model_notebooks_results/{dense_v2,vae_v2}/.
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "04_model_notebooks_results")

sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

sys.path.insert(0, os.path.join(PROJECT_ROOT, "09_dense_v2_comparison"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "10_vae_v2_comparison"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "06_attack_type_analysis"))
from dense_backend_v2 import load_feature_cols_v2, DEFAULT_DENSE_V2_BACKEND, MODEL_LABEL as DENSE_LABEL, MODEL_DIR_DESC as DENSE_DIR_DESC  # noqa: E402
from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND, MODEL_LABEL as VAE_LABEL, MODEL_DIR_DESC as VAE_DIR_DESC  # noqa: E402
from evaluate_by_attack_type_dense_v2 import assemble_labeled_features_df_v2  # noqa: E402

SEED = 0
BENIGN_COLOR = "#0072B2"
ATTACK_COLOR = "#D55E00"


def make_roc_figure(model_name, y, errors, out_path, seed):
    fpr, tpr, _ = roc_curve(y, errors)
    auc_value = roc_auc_score(y, errors)
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.plot(fpr, tpr, color=BENIGN_COLOR, linewidth=2.5, label=f"ROC curve (AUC = {auc_value:.4f})")
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.2, label="random baseline")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — Test Set, all attack types pooled (seed={seed})")
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    fig.suptitle(model_name, fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}  (AUC={auc_value:.4f})")
    return auc_value


def make_histogram_figure(model_name, y, errors, threshold, out_path, seed):
    benign_errors = errors[y == 0]
    attack_errors = errors[y == 1]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    bins = np.linspace(0, np.percentile(errors, 99), 60)
    ax.hist(benign_errors, bins=bins, alpha=0.6, label="benign", color=BENIGN_COLOR, density=True)
    ax.hist(attack_errors, bins=bins, alpha=0.6, label="attack", color=ATTACK_COLOR, density=True)
    ax.axvline(threshold, color="black", linestyle="--", label=f"threshold (val pctl95={threshold:.4f})")
    ax.set_xlabel("Reconstruction error")
    ax.set_ylabel("Density")
    ax.set_title(f"Test-set reconstruction error: benign vs attack, all attack types pooled (seed={seed})")
    ax.legend(frameon=False)
    fig.suptitle(model_name, fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")
    return benign_errors, attack_errors


def write_md(path, model_name, model_dir_desc, n_features, y, benign_errors, attack_errors, auc_value, threshold, seed):
    lines = [
        f"# {model_name} — v2 ({n_features} feature), inference-only figürler",
        "",
        f"Kaynak: zaten eğitilmiş kanonik v2 model (`{model_dir_desc}`, seed={seed}), "
        "sadece inference. v1 notebook'larının aksine burada retraining/loss-curve/ablation/"
        "latent-dim sweep YOK -- v2 için epoch-history hiç kaydedilmedi ve mimari zaten v1'de "
        "seçildi, yeniden aranmadı (bkz. `04_model_notebooks/README.md`). Sadece iki inference "
        "figürü üretildi: ROC eğrisi ve reconstruction-error histogramı, test setinde tüm attack "
        "tiplerinin birleşimi (pooled) üzerinden -- v1 notebook'larındaki eşdeğer bölümlerle aynı çerçeve.",
        "",
        f"Test set: n={len(y)} ({int((y == 0).sum())} benign, {int((y == 1).sum())} attack, tüm tipler dahil).",
        "",
        "## ROC (test, pooled, seed=0)",
        "",
        f"Test AUC = {auc_value:.4f} (bkz. `roc_curve.png`).",
        "",
        "## Reconstruction error (test, pooled, seed=0)",
        "",
        f"Benign test error: mean={benign_errors.mean():.5f}, median={np.median(benign_errors):.5f}. "
        f"Attack test error: mean={attack_errors.mean():.5f}, median={np.median(attack_errors):.5f} "
        f"(threshold_95={threshold:.5f}, bkz. `reconstruction_error_histogram.png`).",
        "",
        "## Kapsam dışı (v1'de var, burada yok)",
        "",
        "Loss curve (training history kaydı yok), full_features vs no_conn_state ablation "
        "(yalnızca dense v1'e özgüydü), VAE latent-dim sweep + beta/annealing varyant "
        "karşılaştırması (mimari v1'de seçildi, v2 aynı mimariyi + 19. feature'ı kullanıyor). "
        "Kanonik 5-seed threshold_95 tam değerlendirme için bkz. "
        "`10_final_report/01_single_attack_type/{dense,vae}/results.md`.",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  wrote {path}")


def run_dense():
    out_dir = os.path.join(OUT_ROOT, "dense_v2")
    os.makedirs(out_dir, exist_ok=True)
    feature_cols = load_feature_cols_v2()
    df = assemble_labeled_features_df_v2(feature_cols)
    X = df[feature_cols].values.astype("float32")
    y = df["is_attack"].values

    backend = DEFAULT_DENSE_V2_BACKEND
    model = backend.load(SEED)
    errors = backend.errors(model, X, SEED)
    threshold = backend.threshold(model, SEED)

    auc_value = make_roc_figure(DENSE_LABEL, y, errors, os.path.join(out_dir, "roc_curve.png"), SEED)
    benign_errors, attack_errors = make_histogram_figure(
        DENSE_LABEL, y, errors, threshold, os.path.join(out_dir, "reconstruction_error_histogram.png"), SEED)
    write_md(os.path.join(out_dir, "results.md"), DENSE_LABEL, DENSE_DIR_DESC, len(feature_cols),
              y, benign_errors, attack_errors, auc_value, threshold, SEED)


def run_vae():
    out_dir = os.path.join(OUT_ROOT, "vae_v2")
    os.makedirs(out_dir, exist_ok=True)
    feature_cols = load_feature_cols_v2()
    df = assemble_labeled_features_df_v2(feature_cols)
    X = df[feature_cols].values.astype("float32")
    y = df["is_attack"].values

    backend = DEFAULT_VAE_V2_BACKEND
    model = backend.load(SEED)
    errors = backend.errors(model, X, SEED)
    threshold = backend.threshold(model, SEED)

    auc_value = make_roc_figure(VAE_LABEL, y, errors, os.path.join(out_dir, "roc_curve.png"), SEED)
    benign_errors, attack_errors = make_histogram_figure(
        VAE_LABEL, y, errors, threshold, os.path.join(out_dir, "reconstruction_error_histogram.png"), SEED)
    write_md(os.path.join(out_dir, "results.md"), VAE_LABEL, VAE_DIR_DESC, len(feature_cols),
              y, benign_errors, attack_errors, auc_value, threshold, SEED)


print("=== Dense v2 (seed=0, inference-only figures) ===")
run_dense()
print("=== VAE v2 (seed=0, inference-only figures) ===")
run_vae()
print("done")
