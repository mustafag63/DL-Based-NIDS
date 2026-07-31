"""
Phase 3 (VAE) - contamination sweep, ADIM 4: evaluate all 30 trained models
(6 contamination levels x 5 seeds) on the one fixed test set built in ADIM 1,
and produce per-seed / summary tables + the contamination curve figure.

Loading note (see phase3_vae/README.md's caveat): the saved encoder/decoder
`.keras` files are ordinary functional models - the reparameterization trick
and the recon-error definition are not part of either graph, so they're
reimplemented here exactly as in the training script / original notebook
(`z = z_mean + exp(0.5*z_log_var) * eps`, error = mean squared reconstruction
error per flow). A per-model random seed is set before sampling eps so
re-running this script reproduces the same numbers.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from scipy.stats import trim_mean
from sklearn.metrics import average_precision_score, fbeta_score, roc_auc_score

# Keras's Lambda-layer deserialization (safe_mode=False) reconstructs the
# log-var-clip closure via `func_load(..., globs=None)`, which falls back to
# `globals()` of keras's own python_utils module - a namespace that never
# imports tensorflow, so `tf.clip_by_value` inside the closure raises
# NameError on load in a fresh process (reproduces identically on the
# existing vae_encoder_final.keras, confirmed independently of this sweep).
# Injecting `tf` into that module's globals before loading is the minimal fix.
import keras.src.utils.python_utils as _keras_python_utils  # noqa: E402
_keras_python_utils.tf = tf

HERE = Path(__file__).parent
DATA_DIR = HERE / "01_data"
MODEL_DIR = HERE / "04_models"
RESULTS_DIR = HERE / "05_results"
RESULTS_DIR.mkdir(exist_ok=True)

manifest = json.loads((DATA_DIR / "manifest.json").read_text())
FEATURE_COLS = manifest["feature_cols"]

CONTAM_LEVELS_PCT = [0, 1, 2, 4, 8, 12]
SEEDS = [0, 1, 2, 3, 4]


def reconstruction_error(encoder, decoder, X, eval_seed):
    tf.random.set_seed(eval_seed)
    z_mean, z_log_var = encoder(X, training=False)
    eps = tf.random.normal(shape=tf.shape(z_mean))
    z = z_mean + tf.exp(0.5 * z_log_var) * eps
    recon = decoder(z, training=False).numpy()
    return np.mean(np.square(X - recon), axis=1)


def main() -> None:
    test_df = pd.read_csv(DATA_DIR / "test_set.csv")
    X_test = test_df[FEATURE_COLS].values.astype("float32")
    y_test = test_df["is_attack"].values
    print(f"Fixed test set: {len(test_df)} flows ({int((y_test == 0).sum())} benign, "
          f"{int((y_test == 1).sum())} attack)")

    rows = []
    for level_pct in CONTAM_LEVELS_PCT:
        for seed in SEEDS:
            seed_dir = MODEL_DIR / f"contam_{level_pct}pct" / f"seed_{seed}"
            encoder = tf.keras.models.load_model(seed_dir / "encoder.keras", safe_mode=False)
            decoder = tf.keras.models.load_model(seed_dir / "decoder.keras", safe_mode=False)
            threshold_info = json.loads((seed_dir / "threshold.json").read_text())

            eval_seed = 100_000 + level_pct * 100 + seed
            errors = reconstruction_error(encoder, decoder, X_test, eval_seed)

            thr95 = threshold_info["threshold_95"]
            thr99 = threshold_info["threshold_99"]
            pred95 = (errors > thr95).astype(int)

            pr_auc = average_precision_score(y_test, errors)
            roc_auc = roc_auc_score(y_test, errors)
            f1 = fbeta_score(y_test, pred95, beta=1.0, zero_division=0)
            f2 = fbeta_score(y_test, pred95, beta=2.0, zero_division=0)

            benign_mask = y_test == 0
            attack_mask = y_test == 1
            benign_fpr = float(pred95[benign_mask].mean()) if benign_mask.any() else float("nan")
            attack_recall = float(pred95[attack_mask].mean()) if attack_mask.any() else float("nan")

            rows.append({
                "contamination_pct": level_pct,
                "seed": seed,
                "threshold_95": thr95,
                "threshold_99": thr99,
                "pr_auc": pr_auc,
                "roc_auc": roc_auc,
                "f1": f1,
                "f2": f2,
                "benign_fpr": benign_fpr,
                "attack_recall": attack_recall,
            })
            print(f"  level={level_pct:2d}% seed={seed}: PR-AUC={pr_auc:.4f} ROC-AUC={roc_auc:.4f} "
                  f"F1={f1:.4f} F2={f2:.4f} benign_FPR={benign_fpr:.4f} attack_recall={attack_recall:.4f}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(RESULTS_DIR / "results_per_seed.csv", index=False)

    metric_cols = ["threshold_95", "threshold_99", "pr_auc", "roc_auc", "f1", "f2", "benign_fpr", "attack_recall"]

    def trimmed_mean(s):
        # 5 seeds, proportiontocut=0.2 drops the single lowest and highest
        # value before averaging - a mean-alternative that isn't dragged
        # around by one unstable training run (see README's 8% discussion).
        return trim_mean(s, proportiontocut=0.2)

    trimmed_mean.__name__ = "trimmed_mean"

    summary = per_seed_df.groupby("contamination_pct")[metric_cols].agg(["mean", "std", "median", trimmed_mean])
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.reset_index()
    summary.to_csv(RESULTS_DIR / "results_summary.csv", index=False)

    print(f"\nWrote {RESULTS_DIR / 'results_per_seed.csv'} and {RESULTS_DIR / 'results_summary.csv'}")

    # --- contamination curve figure ---
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    panels = [
        ("pr_auc", "PR-AUC", axes[0, 0]),
        ("f1", "F1 (threshold_95)", axes[0, 1]),
        ("benign_fpr", "Benign FPR (threshold_95)", axes[1, 0]),
        ("attack_recall", "Attack Recall (threshold_95)", axes[1, 1]),
    ]
    x = summary["contamination_pct"].values
    for metric, title, ax in panels:
        mean = summary[f"{metric}_mean"].values
        std = summary[f"{metric}_std"].fillna(0).values
        ax.plot(x, mean, marker="o", color="#3b6fa0")
        ax.fill_between(x, mean - std, mean + std, alpha=0.25, color="#3b6fa0")
        ax.set_title(title)
        ax.set_xlabel("Train contamination (%)")
        ax.set_ylabel(title)
        ax.grid(alpha=0.3)
    fig.suptitle("VAE contamination sweep (latent=10, beta=0.25) - fixed test set, 5-seed mean +/- std")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "contamination_curve.png", dpi=150)
    print(f"Wrote {RESULTS_DIR / 'contamination_curve.png'}")


if __name__ == "__main__":
    main()
