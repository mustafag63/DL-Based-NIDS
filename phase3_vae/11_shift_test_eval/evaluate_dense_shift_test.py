"""Path-corrected re-run of analysis/window01_shift_test_evaluation.py
(that script's SPLIT_DIR/MODEL_DIR/FEATURES_PATH predate the
phase3_dense/phase3_vae split and no longer resolve). Same logic,
unmodified: loads the 10 already-trained Dense autoencoders
(phase3_dense/04_phase3_models/{variant}/autoencoder_seed{seed}.keras),
scores window01_shift_test.csv, reports FPR - purely for the VAE-vs-Dense
comparison table in this folder's README. Read-only, does not retrain or
touch phase3_dense/.

The original analysis/window01_shift_test_evaluation.py was left
unmodified (out of scope for this task - only 11_shift_test_eval/ gets
new files).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # IDS-Project/
DENSE_DIR = PROJECT_ROOT / "phase3_dense"
FEATURES_PATH = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features" / "features_all_windows.csv"
SPLIT_DIR = DENSE_DIR / "03_phase3_splits"
MODEL_DIR = DENSE_DIR / "04_phase3_models"
OUT_DIR = Path(__file__).resolve().parent

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts"]
CONN_STATE_COLS = ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"]
SEEDS = (0, 1, 2, 3, 4)
VARIANTS = ("full_features", "no_conn_state")


def reconstruction_error(model, X):
    recon = model.predict(X, verbose=0)
    return np.mean(np.square(X - recon), axis=1)


def describe(errors, threshold):
    n = len(errors)
    n_flagged = int((errors > threshold).sum())
    return {
        "n": n, "mean": float(np.mean(errors)), "median": float(np.median(errors)),
        "std": float(np.std(errors)), "pct_flagged": 100.0 * n_flagged / n if n else float("nan"),
    }


def main():
    features = pd.read_csv(FEATURES_PATH)
    val_idx = pd.read_csv(SPLIT_DIR / "val_indices.csv")["row_index"].values
    test_idx = pd.read_csv(SPLIT_DIR / "test_indices.csv")["row_index"].values
    shift_idx = pd.read_csv(SPLIT_DIR / "window01_shift_test.csv")["row_index"].values

    val_df = features.iloc[val_idx].reset_index(drop=True)
    test_df = features.iloc[test_idx].reset_index(drop=True)
    shift_df = features.iloc[shift_idx].reset_index(drop=True)
    assert (shift_df["is_attack"] == 0).all()

    full_cols = [c for c in features.columns if c not in META_COLS]
    no_cs_cols = [c for c in full_cols if c not in CONN_STATE_COLS]
    cols_by_variant = {"full_features": full_cols, "no_conn_state": no_cs_cols}

    rows = []
    for variant in VARIANTS:
        cols = cols_by_variant[variant]
        X_val_benign = val_df.loc[val_df["is_attack"] == 0, cols].values.astype("float32")
        X_test_benign = test_df.loc[test_df["is_attack"] == 0, cols].values.astype("float32")
        X_shift = shift_df[cols].values.astype("float32")

        for seed in SEEDS:
            model = tf.keras.models.load_model(MODEL_DIR / variant / f"autoencoder_seed{seed}.keras")
            threshold = float(np.percentile(reconstruction_error(model, X_val_benign), 95))
            stats_test = describe(reconstruction_error(model, X_test_benign), threshold)
            stats_shift = describe(reconstruction_error(model, X_shift), threshold)
            rows.append({
                "variant": variant, "seed": seed, "threshold": threshold,
                "test_benign_fpr_pct": stats_test["pct_flagged"],
                "shift_fpr_pct": stats_shift["pct_flagged"],
                "shift_mean_error": stats_shift["mean"], "shift_median_error": stats_shift["median"],
            })
            print(f"{variant} seed={seed}: test_benign_FPR={stats_test['pct_flagged']:.2f}% "
                  f"shift_FPR={stats_shift['pct_flagged']:.2f}%")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "dense_shift_test_per_seed.csv", index=False)

    print(f"\n{'=' * 70}\n5-seed summary\n{'=' * 70}")
    summary_rows = []
    for variant in VARIANTS:
        v = df[df["variant"] == variant]
        summary_rows.append({
            "variant": variant,
            "test_benign_fpr_mean": v["test_benign_fpr_pct"].mean(),
            "test_benign_fpr_std": v["test_benign_fpr_pct"].std(),
            "shift_fpr_mean": v["shift_fpr_pct"].mean(),
            "shift_fpr_std": v["shift_fpr_pct"].std(),
        })
        print(f"{variant}: test_benign_FPR={v['test_benign_fpr_pct'].mean():.2f}%+/-{v['test_benign_fpr_pct'].std():.2f}%  "
              f"shift_FPR={v['shift_fpr_pct'].mean():.2f}%+/-{v['shift_fpr_pct'].std():.2f}%")
    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "dense_shift_test_summary.csv", index=False)
    print(f"\nSaved: {OUT_DIR / 'dense_shift_test_per_seed.csv'}, {OUT_DIR / 'dense_shift_test_summary.csv'}")


if __name__ == "__main__":
    main()
