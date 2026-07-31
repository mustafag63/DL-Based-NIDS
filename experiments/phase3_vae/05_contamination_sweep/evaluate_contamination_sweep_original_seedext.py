"""
Phase 3 (VAE) - contamination sweep SEED-EXTENSION evaluation for the
ORIGINAL 6 controlled-injection levels (0/1/2/4/8/12%): evaluates the newly
trained seed_5..seed_19 models (see train_contamination_sweep_original_seedext.py)
on the SAME fixed test set as the rest of the sweep, then APPENDS their rows
to 05_results/results_per_seed.csv (existing seed_0..seed_4 rows for these
levels are left untouched - this script only adds rows for (level, seed)
keys not already present) and regenerates results_summary.csv +
contamination_curve.png from the combined, now-20-seeds-everywhere, 9-point
data (0/1/2/4/8/12/14.33/19.30/21.29%).
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

import keras.src.utils.python_utils as _keras_python_utils  # noqa: E402
_keras_python_utils.tf = tf

HERE = Path(__file__).parent
DATA_DIR = HERE / "01_data"
MODEL_DIR = HERE / "04_models"
RESULTS_DIR = HERE / "05_results"

manifest = json.loads((DATA_DIR / "manifest.json").read_text())
FEATURE_COLS = manifest["feature_cols"]

ORIGINAL_LEVELS_PCT = [0, 1, 2, 4, 8, 12]
NEW_SEEDS = list(range(5, 20))
RESAMPLED_LEVELS_PCT = {15, 20, 22}


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
    print(f"Fixed test set (unchanged, same as original sweep): {len(test_df)} flows "
          f"({int((y_test == 0).sum())} benign, {int((y_test == 1).sum())} attack)")

    rows = []
    for level_pct in ORIGINAL_LEVELS_PCT:
        for seed in NEW_SEEDS:
            seed_dir = MODEL_DIR / f"contam_{level_pct}pct" / f"seed_{seed}"
            if not (seed_dir / "threshold.json").exists():
                print(f"  level={level_pct}% seed={seed}: no trained model found, skipping")
                continue
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

    new_rows_df = pd.DataFrame(rows)

    per_seed_path = RESULTS_DIR / "results_per_seed.csv"
    existing_df = pd.read_csv(per_seed_path)
    existing_keys = set(zip(existing_df["contamination_pct"], existing_df["seed"]))
    new_keys = set(zip(new_rows_df["contamination_pct"], new_rows_df["seed"]))
    overlap = existing_keys & new_keys
    assert not overlap, f"refusing to duplicate existing rows: {overlap}"

    combined_df = pd.concat([existing_df, new_rows_df], ignore_index=True)
    combined_df = combined_df.sort_values(["contamination_pct", "seed"]).reset_index(drop=True)
    combined_df.to_csv(per_seed_path, index=False)
    print(f"\nAppended {len(new_rows_df)} new rows (levels {sorted(ORIGINAL_LEVELS_PCT)}, "
          f"seeds 5-19) to {per_seed_path} ({len(combined_df)} rows total, "
          f"{len(existing_df)} pre-existing rows preserved untouched)")

    metric_cols = ["threshold_95", "threshold_99", "pr_auc", "roc_auc", "f1", "f2", "benign_fpr", "attack_recall"]

    def trimmed_mean(s):
        return trim_mean(s, proportiontocut=0.2)

    trimmed_mean.__name__ = "trimmed_mean"

    n_seeds = combined_df.groupby("contamination_pct")["seed"].nunique().rename("n_seeds")
    summary = combined_df.groupby("contamination_pct")[metric_cols].agg(["mean", "std", "median", trimmed_mean])
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.join(n_seeds).reset_index()
    cols = ["contamination_pct", "n_seeds"] + [c for c in summary.columns if c not in ("contamination_pct", "n_seeds")]
    summary = summary[cols]
    summary.to_csv(RESULTS_DIR / "results_summary.csv", index=False)
    print(f"Wrote {RESULTS_DIR / 'results_summary.csv'} (levels: {sorted(summary['contamination_pct'].tolist())}, "
          f"n_seeds per level: {dict(zip(summary['contamination_pct'], summary['n_seeds']))})")

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    panels = [
        ("pr_auc", "PR-AUC", axes[0, 0]),
        ("f1", "F1 (threshold_95)", axes[0, 1]),
        ("benign_fpr", "Benign FPR (threshold_95)", axes[1, 0]),
        ("attack_recall", "Attack Recall (threshold_95)", axes[1, 1]),
    ]
    x = summary["contamination_pct"].values
    is_resampled = summary["contamination_pct"].isin(RESAMPLED_LEVELS_PCT).values
    for metric, title, ax in panels:
        mean = summary[f"{metric}_mean"].values
        std = summary[f"{metric}_std"].fillna(0).values
        ax.plot(x, mean, color="#3b6fa0", linewidth=1.2, zorder=1)
        ax.fill_between(x, mean - std, mean + std, alpha=0.25, color="#3b6fa0")
        ax.scatter(x[~is_resampled], mean[~is_resampled], marker="o", color="#3b6fa0",
                   s=40, zorder=2, label="controlled injection (0-12%)")
        ax.scatter(x[is_resampled], mean[is_resampled], marker="^", color="#c0392b",
                   s=55, zorder=3, label="resampled window (14.33-21.29%)")
        ax.axvline(12, color="#999999", linestyle="--", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("Train contamination (%)")
        ax.set_ylabel(title)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8, loc="best")
    fig.suptitle("VAE contamination sweep (latent=10, beta=0.25) - fixed test set, mean +/- std\n"
                 "(all 9 points now n=20 seeds; triangle = resampled-window train set)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "contamination_curve.png", dpi=150)
    print(f"Wrote {RESULTS_DIR / 'contamination_curve.png'}")


if __name__ == "__main__":
    main()
