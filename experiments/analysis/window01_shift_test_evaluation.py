"""
Evaluate the 10 already-trained Phase 3 autoencoders (5 seeds x 2 feature-set
variants) on `03_phase3_splits/window01_shift_test.csv` -- the held-out half
of window_01 (274 pure-benign flows) that was deliberately kept OUT of
train/val/test to probe how well the benign reconstruction-error profile
generalizes to a statistically distinct benign sample (window_01's duration
CV was flagged as an outlier vs the other 7 windows in the 11 Temmuz EDA).

This script does NOT train anything. It loads the existing `.keras` models
from `04_phase3_models/{variant}/autoencoder_seed{seed}.keras` and follows
the exact preprocessing / threshold logic from `phase3_autoencoder.ipynb`
(cells 2 and 8):
  - features_all_windows.csv, row-indexed via `03_phase3_splits/*.csv`'s
    `row_index` column (0-based position in the Phase 2 feature matrix).
  - FULL_COLS = all columns except META_COLS (is_attack, actual_attack_pct,
    window_id, ts) -> 18 columns.
  - NO_CS_COLS = FULL_COLS minus the 4 conn_state one-hot columns -> 14.
  - reconstruction_error(model, X) = per-row mean squared error.
  - threshold = 95th percentile of the model's OWN reconstruction error on
    VAL's benign-only flows (thr_pctl in the notebook) -- this threshold is
    loaded fresh per seed/variant here, not re-read from the metrics JSONs,
    so it is reproduced from the same val split rather than assumed.

For each of the 10 models, three error distributions are compared:
  (a) test-set benign flows (reference: "normal" benign behavior)
  (b) test-set attack flows (reference: "normal" attack behavior)
  (c) window01_shift_test flows (the actual question: does this benign-only,
      statistically-distinct sample look like (a) or drift toward (b)?)

Read-only: does not modify features_all_windows.*, splits/, models/, or
results/. Does not retrain or resave any model.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = PROJECT_ROOT / "02_phase2_feature_extraction" / "features_all_windows.csv"
SPLIT_DIR = PROJECT_ROOT / "03_phase3_splits"
MODEL_DIR = PROJECT_ROOT / "04_phase3_models"

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
        "n": n,
        "mean": float(np.mean(errors)),
        "median": float(np.median(errors)),
        "std": float(np.std(errors)),
        "pct_flagged": 100.0 * n_flagged / n if n else float("nan"),
    }


def main():
    print("Loading features_all_windows.csv and the 4 split files (read-only)...")
    features = pd.read_csv(FEATURES_PATH)
    train_idx = pd.read_csv(SPLIT_DIR / "train_indices.csv")["row_index"].values
    val_idx = pd.read_csv(SPLIT_DIR / "val_indices.csv")["row_index"].values
    test_idx = pd.read_csv(SPLIT_DIR / "test_indices.csv")["row_index"].values
    shift_idx = pd.read_csv(SPLIT_DIR / "window01_shift_test.csv")["row_index"].values

    val_df = features.iloc[val_idx].reset_index(drop=True)
    test_df = features.iloc[test_idx].reset_index(drop=True)
    shift_df = features.iloc[shift_idx].reset_index(drop=True)

    print(f"val n={len(val_df)}, test n={len(test_df)}, window01_shift_test n={len(shift_df)}")
    assert (shift_df["is_attack"] == 0).all(), "window01_shift_test is expected to be 100% benign"
    assert (shift_df["window_id"] == "window_01_0pct").all()

    full_cols = [c for c in features.columns if c not in META_COLS]
    no_cs_cols = [c for c in full_cols if c not in CONN_STATE_COLS]
    cols_by_variant = {"full_features": full_cols, "no_conn_state": no_cs_cols}

    all_rows = []
    per_variant_shift_fp = {v: [] for v in VARIANTS}
    per_variant_benign_fp = {v: [] for v in VARIANTS}

    for variant in VARIANTS:
        cols = cols_by_variant[variant]
        X_val_benign = val_df.loc[val_df["is_attack"] == 0, cols].values.astype("float32")
        X_test_benign = test_df.loc[test_df["is_attack"] == 0, cols].values.astype("float32")
        X_test_attack = test_df.loc[test_df["is_attack"] == 1, cols].values.astype("float32")
        X_shift = shift_df[cols].values.astype("float32")

        print(f"\n{'=' * 90}\nVariant: {variant} ({len(cols)} columns)\n{'=' * 90}")

        for seed in SEEDS:
            model_path = MODEL_DIR / variant / f"autoencoder_seed{seed}.keras"
            model = tf.keras.models.load_model(model_path)

            val_benign_errors = reconstruction_error(model, X_val_benign)
            threshold = float(np.percentile(val_benign_errors, 95))

            test_benign_errors = reconstruction_error(model, X_test_benign)
            test_attack_errors = reconstruction_error(model, X_test_attack)
            shift_errors = reconstruction_error(model, X_shift)

            stats_benign = describe(test_benign_errors, threshold)
            stats_attack = describe(test_attack_errors, threshold)
            stats_shift = describe(shift_errors, threshold)

            per_variant_shift_fp[variant].append(stats_shift["pct_flagged"])
            per_variant_benign_fp[variant].append(stats_benign["pct_flagged"])

            print(f"\n--- seed={seed} (threshold = val-benign pctl95 = {threshold:.5f}) ---")
            print(
                f"{'group':<28s} {'n':>6s} {'mean':>10s} {'median':>10s} {'std':>10s} {'%flagged':>10s}"
            )
            print(
                f"{'test benign (reference)':<28s} {stats_benign['n']:>6d} "
                f"{stats_benign['mean']:>10.5f} {stats_benign['median']:>10.5f} "
                f"{stats_benign['std']:>10.5f} {stats_benign['pct_flagged']:>9.2f}%"
            )
            print(
                f"{'test attack (reference)':<28s} {stats_attack['n']:>6d} "
                f"{stats_attack['mean']:>10.5f} {stats_attack['median']:>10.5f} "
                f"{stats_attack['std']:>10.5f} {stats_attack['pct_flagged']:>9.2f}%"
            )
            print(
                f"{'window01_shift_test (Q)':<28s} {stats_shift['n']:>6d} "
                f"{stats_shift['mean']:>10.5f} {stats_shift['median']:>10.5f} "
                f"{stats_shift['std']:>10.5f} {stats_shift['pct_flagged']:>9.2f}%"
            )

            all_rows.append(
                {
                    "variant": variant, "seed": seed, "threshold": threshold,
                    "benign_mean": stats_benign["mean"], "benign_median": stats_benign["median"],
                    "benign_pct_flagged": stats_benign["pct_flagged"],
                    "attack_mean": stats_attack["mean"], "attack_median": stats_attack["median"],
                    "attack_pct_flagged": stats_attack["pct_flagged"],
                    "shift_mean": stats_shift["mean"], "shift_median": stats_shift["median"],
                    "shift_pct_flagged": stats_shift["pct_flagged"],
                }
            )

    summary = pd.DataFrame(all_rows)
    print(f"\n{'=' * 90}\n5-seed summary (mean +/- std across seeds)\n{'=' * 90}")
    for variant in VARIANTS:
        v = summary[summary["variant"] == variant]
        print(f"\n{variant}:")
        print(
            f"  test-set BENIGN false-positive rate (error > val-pctl95 threshold): "
            f"{v['benign_pct_flagged'].mean():.2f}% +/- {v['benign_pct_flagged'].std():.2f}% "
            f"(expected ~5% by construction, since threshold = val-benign pctl95)"
        )
        print(
            f"  test-set ATTACK detection rate (recall @ pctl95 threshold):          "
            f"{v['attack_pct_flagged'].mean():.2f}% +/- {v['attack_pct_flagged'].std():.2f}%"
        )
        print(
            f"  window01_shift_test false-positive rate:                            "
            f"{v['shift_pct_flagged'].mean():.2f}% +/- {v['shift_pct_flagged'].std():.2f}%"
        )
        print(
            f"  window01_shift_test mean error vs benign/attack reference (seed-averaged): "
            f"shift={v['shift_mean'].mean():.5f}, benign={v['benign_mean'].mean():.5f}, "
            f"attack={v['attack_mean'].mean():.5f}"
        )

    print(f"\n{'=' * 90}\nInterpretation\n{'=' * 90}")
    for variant in VARIANTS:
        v = summary[summary["variant"] == variant]
        shift_fp = v["shift_pct_flagged"].mean()
        benign_fp = v["benign_pct_flagged"].mean()
        gap = shift_fp - benign_fp
        print(f"\n{variant}: shift-test FP rate = {shift_fp:.2f}% vs test-benign FP rate = {benign_fp:.2f}% (gap = {gap:+.2f}pp)")
        if shift_fp <= benign_fp + 5:
            print(
                "  -> CLOSE to the benign reference (~5% expected by construction). "
                "The model generalizes well to window_01's distinct benign profile; "
                "window01_shift_test's error distribution resembles normal benign "
                "traffic, not attack traffic."
            )
        elif shift_fp <= benign_fp + 20:
            print(
                "  -> MODERATELY elevated above the benign reference. Some sensitivity "
                "to window_01's natural variation exists, worth monitoring but not "
                "alarming on its own."
            )
        else:
            print(
                "  -> SUBSTANTIALLY elevated (>20pp above the ~5% benign reference). "
                "The model is sensitive to this kind of natural benign variation and "
                "carries a real false-alarm risk on traffic that merely differs "
                "statistically from the training distribution, without being an attack."
            )


if __name__ == "__main__":
    main()
