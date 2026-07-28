"""
Full deconfounded sweep, step 2: train all missing V2 levels (20 seeds each,
levels from manifest_full.json; 0%/4% models from train_and_evaluate_v2.py
are reused as-is) and evaluate every level deterministically (z_mean) on the
fixed V2 test set. Also rescores the ORIGINAL v1 sweep's 9 levels
deterministically on the v1 test set, so the findings doc can compare
pipelines without the stochastic-vs-deterministic scoring difference
muddying the comparison.

Architecture/hyperparameters and the threshold convention are identical to
train_and_evaluate_v2.py (imported from it): latent=10, beta=0.25,
threshold_95 = 95th pctl of the deterministic error on val_benign_v2.csv per
seed (v1 rescore: v1's own val_benign.csv).

Progress: prints one "LEVEL DONE ..." line per finished level (used by the
session monitor to report progress).

Outputs (this directory):
  ../04_models/contam_{lvl}pct_v2/seed_*/          (new models)
  results_all_points.csv                            (v2 per-seed, all 9 points)
  v1_deterministic_results_per_seed.csv             (v1 rescore, all 9 points)
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = Path(__file__).parent
CHECK_DIR = HERE.parent
SWEEP_DIR = CHECK_DIR.parent
DATA_DIR = CHECK_DIR / "01_data"
MODEL_DIR = CHECK_DIR / "04_models"
V1_DATA_DIR = SWEEP_DIR / "01_data"
V1_MODEL_ROOT = SWEEP_DIR / "04_models"

_spec = importlib.util.spec_from_file_location("train_and_evaluate_v2",
                                               CHECK_DIR / "train_and_evaluate_v2.py")
_tev2 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _tev2
_spec.loader.exec_module(_tev2)
train_v2_level = _tev2.train_v2_level
zmean_error = _tev2.zmean_error
metrics_row = _tev2.metrics_row
FEATURE_COLS = _tev2.FEATURE_COLS
SEEDS = _tev2.SEEDS

manifest_full = json.loads((HERE / "manifest_full.json").read_text())
LEVELS = manifest_full["levels"]  # sorted by curve_pct; target_pct names the files/dirs

V1_LEVELS = [0, 1, 2, 4, 8, 12, 15, 20, 22]
# v1 curve x values: nominal for injection, actual for resampled (as in
# 05_results/results_per_seed.csv, which uses 15/20/22 for the resampled rows
# -- we keep target_pct as the join key and store v1's own convention).


def main():
    val = pd.read_csv(DATA_DIR / "val_benign_v2.csv")
    X_val = val[FEATURE_COLS].values.astype("float32")
    test = pd.read_csv(DATA_DIR / "test_set_v2.csv")
    X_test = test[FEATURE_COLS].values.astype("float32")
    y_test = test["is_attack"].values
    source = test["benign_source"].fillna("").values
    print(f"V2 val: {len(val)}; V2 test: {len(test)} "
          f"({int((y_test == 0).sum())} benign / {int(y_test.sum())} attack)")

    # ---------------- V2: train missing levels + evaluate all ----------------
    rows = []
    for lvl in LEVELS:
        target = lvl["target_pct"]
        curve_pct = lvl["curve_pct"]
        train_path = DATA_DIR / f"train_contam_{target}pct_v2.csv"
        train_df = pd.read_csv(train_path)
        X_train = train_df[FEATURE_COLS].values.astype("float32")
        print(f"\n=== V2 level target={target}% (curve x={curve_pct}, "
              f"n={len(train_df)}, attack_in_train={int(train_df['is_attack'].sum())}) ===")
        train_v2_level(target, X_train, X_val)

        level_dir = MODEL_DIR / f"contam_{target}pct_v2"
        for seed in SEEDS:
            seed_dir = level_dir / f"seed_{seed}"
            encoder = tf.keras.models.load_model(seed_dir / "encoder.keras")
            decoder = tf.keras.models.load_model(seed_dir / "decoder.keras")
            thr95 = json.loads((seed_dir / "threshold.json").read_text())["threshold_95"]
            errors = zmean_error(encoder, decoder, X_test)
            rows.append({"contamination_pct": curve_pct, "target_pct": target, "seed": seed,
                         **metrics_row(y_test, errors, thr95, source)})
        lvl_df = pd.DataFrame([r for r in rows if r["target_pct"] == target])
        print(f"LEVEL DONE v2 target={target}% curve={curve_pct}: "
              f"PR-AUC={lvl_df['pr_auc'].mean():.4f}+/-{lvl_df['pr_auc'].std():.4f} "
              f"recall={lvl_df['attack_recall'].mean():.4f} FPR={lvl_df['benign_fpr'].mean():.4f}")
        pd.DataFrame(rows).to_csv(HERE / "results_all_points.csv", index=False)  # checkpoint

    pd.DataFrame(rows).to_csv(HERE / "results_all_points.csv", index=False)
    print(f"\nWrote {HERE / 'results_all_points.csv'} ({len(rows)} rows)")

    # ---------------- V1 deterministic rescore (reference arm) ----------------
    v1_val = pd.read_csv(V1_DATA_DIR / "val_benign.csv")
    X_v1_val = v1_val[FEATURE_COLS].values.astype("float32")
    v1_test = pd.read_csv(V1_DATA_DIR / "test_set.csv")
    X_v1_test = v1_test[FEATURE_COLS].values.astype("float32")
    y_v1_test = v1_test["is_attack"].values

    v1_rows = []
    for target in V1_LEVELS:
        level_dir = V1_MODEL_ROOT / f"contam_{target}pct"
        for seed in SEEDS:
            seed_dir = level_dir / f"seed_{seed}"
            encoder = tf.keras.models.load_model(seed_dir / "encoder.keras", safe_mode=False)
            decoder = tf.keras.models.load_model(seed_dir / "decoder.keras", safe_mode=False)
            thr95 = float(np.percentile(zmean_error(encoder, decoder, X_v1_val), 95))
            errors = zmean_error(encoder, decoder, X_v1_test)
            v1_rows.append({"target_pct": target, "seed": seed,
                            **metrics_row(y_v1_test, errors, thr95)})
        lvl_df = pd.DataFrame([r for r in v1_rows if r["target_pct"] == target])
        print(f"LEVEL DONE v1_det target={target}%: "
              f"PR-AUC={lvl_df['pr_auc'].mean():.4f}+/-{lvl_df['pr_auc'].std():.4f} "
              f"recall={lvl_df['attack_recall'].mean():.4f} FPR={lvl_df['benign_fpr'].mean():.4f}")
        pd.DataFrame(v1_rows).to_csv(HERE / "v1_deterministic_results_per_seed.csv", index=False)

    pd.DataFrame(v1_rows).to_csv(HERE / "v1_deterministic_results_per_seed.csv", index=False)
    print(f"Wrote {HERE / 'v1_deterministic_results_per_seed.csv'} ({len(v1_rows)} rows)")
    print("ALL DONE")


if __name__ == "__main__":
    main()
