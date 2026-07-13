"""
Phase 3 v2: retrain the autoencoder on the enlarged feature set that adds 4
rolling 60-second source-IP time-window features (conn_count_60s,
unique_dst_ports_60s, unique_dst_ips_60s, failed_conn_ratio_60s) to the
original 18 flow-level columns, per the context.md TODO on IP-based
time-window aggregation. Motivation: attack_type_breakdown_evaluation.py
showed the v1 (18-column) autoencoder has 0.00% recall on apache_bench across
all 5 seeds, because a single apache_bench flow looks just like a normal fast
HTTP request at the flow level. The rolling features are meant to expose the
one thing a single flow can't: that dozens/hundreds of near-identical
requests to the same source arrived within the last 60 seconds.

This is the exact same architecture, training loop, and threshold-calibration
logic as `phase3_autoencoder.ipynb` (cells 2, 4, 8) -- only the column lists
and output directories differ:
  - full_features:  22 columns (18 original + 4 new rolling features)
  - no_conn_state:  18 columns (22 - 4 conn_state one-hot columns)
    (previously this variant had 14 columns; it grows by the same 4 new
    columns, since conn_state removal is orthogonal to the rolling-feature
    addition)

Models are saved to `04_phase3_models_v2/`, metrics to `05_phase3_results_v2/`
-- the original `04_phase3_models/` (v1, 18-column) is left untouched so the
two can be compared side by side.
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, accuracy_score

BASE = Path(__file__).resolve().parent
FEAT_PATH = BASE / "02_phase2_feature_extraction" / "features_all_windows.csv"
SPLIT_DIR = BASE / "03_phase3_splits"
MODEL_DIR = BASE / "04_phase3_models_v2"
RESULTS_DIR = BASE / "05_phase3_results_v2"
MODEL_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

print(f"TensorFlow {tf.__version__}, GPU: {tf.config.list_physical_devices('GPU')}")

features = pd.read_csv(FEAT_PATH)
train_idx = pd.read_csv(SPLIT_DIR / "train_indices.csv")["row_index"].values
val_idx = pd.read_csv(SPLIT_DIR / "val_indices.csv")["row_index"].values
test_idx = pd.read_csv(SPLIT_DIR / "test_indices.csv")["row_index"].values

train_df = features.iloc[train_idx].reset_index(drop=True)
val_df = features.iloc[val_idx].reset_index(drop=True)
test_df = features.iloc[test_idx].reset_index(drop=True)

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts"]
CONN_STATE_COLS = ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"]
FULL_COLS = [c for c in features.columns if c not in META_COLS]
NO_CS_COLS = [c for c in FULL_COLS if c not in CONN_STATE_COLS]

assert (train_df["is_attack"] == 0).all(), "train split must be 100% benign"
print(f"train={len(train_df)} (all benign), val={len(val_df)}, test={len(test_df)}")
print(f"full_features: {len(FULL_COLS)} columns, no_conn_state: {len(NO_CS_COLS)} columns")
assert len(FULL_COLS) == 22, f"expected 22 full columns, got {len(FULL_COLS)}"
assert len(NO_CS_COLS) == 18, f"expected 18 no_conn_state columns, got {len(NO_CS_COLS)}"


def build_model(n_features, seed):
    tf.keras.utils.set_random_seed(seed)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(n_features,)),
        tf.keras.layers.Dense(16, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4)),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.Dense(8, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4), name="bottleneck"),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.Dense(16, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4)),
        tf.keras.layers.Dense(n_features, activation="linear"),
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


def reconstruction_error(model, X):
    recon = model.predict(X, verbose=0)
    return np.mean(np.square(X - recon), axis=1)


def evaluate_at_threshold(y_true, errors, threshold):
    y_pred = (errors > threshold).astype(int)
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "threshold": float(threshold),
    }


def run_variant(variant_name, cols, seeds=(0, 1, 2, 3, 4)):
    n_features = len(cols)
    X_train = train_df[cols].values.astype("float32")
    val_benign_mask = val_df["is_attack"] == 0
    X_val_benign = val_df.loc[val_benign_mask, cols].values.astype("float32")
    X_val_all = val_df[cols].values.astype("float32")
    y_val = val_df["is_attack"].values
    X_test = test_df[cols].values.astype("float32")
    y_test = test_df["is_attack"].values

    model_dir = MODEL_DIR / variant_name
    model_dir.mkdir(parents=True, exist_ok=True)
    results_dir = RESULTS_DIR / variant_name
    results_dir.mkdir(parents=True, exist_ok=True)

    seed_metrics = []
    for seed in seeds:
        t0 = time.time()
        model = build_model(n_features, seed)
        early_stop = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=12, restore_best_weights=True)
        history = model.fit(
            X_train, X_train, validation_data=(X_val_benign, X_val_benign),
            epochs=200, batch_size=128, shuffle=True, callbacks=[early_stop], verbose=0,
        )
        train_time = time.time() - t0
        model.save(model_dir / f"autoencoder_seed{seed}.keras")

        val_errors_benign = reconstruction_error(model, X_val_benign)
        val_errors_all = reconstruction_error(model, X_val_all)
        test_errors = reconstruction_error(model, X_test)

        thr_pctl = float(np.percentile(val_errors_benign, 95))
        fpr, tpr, roc_thresholds = __import__("sklearn.metrics", fromlist=["roc_curve"]).roc_curve(y_val, val_errors_all)
        youden_idx = int(np.argmax(tpr - fpr))
        thr_youden = float(roc_thresholds[youden_idx])

        test_auc = float(roc_auc_score(y_test, test_errors))
        metrics = {
            "seed": seed, "variant": variant_name, "n_features": n_features,
            "train_time_sec": round(train_time, 2), "epochs_run": len(history.history["loss"]),
            "final_train_loss": history.history["loss"][-1], "final_val_loss": history.history["val_loss"][-1],
            "test_auc": test_auc,
            "threshold_pctl95": evaluate_at_threshold(y_test, test_errors, thr_pctl),
            "threshold_youden": evaluate_at_threshold(y_test, test_errors, thr_youden),
        }
        seed_metrics.append(metrics)
        (results_dir / f"seed{seed}_metrics.json").write_text(json.dumps(metrics, indent=2))
        print(
            f"[{variant_name}] seed={seed} epochs={metrics['epochs_run']} "
            f"train_time={train_time:.2f}s test_auc={test_auc:.4f} "
            f"pctl95_f1={metrics['threshold_pctl95']['f1']:.4f} "
            f"pctl95_recall={metrics['threshold_pctl95']['recall']:.4f}"
        )

    def mean_std(values):
        arr = np.array(values, dtype=float)
        return {"mean": float(arr.mean()), "std": float(arr.std())}

    summary = {
        "variant": variant_name, "n_features": n_features,
        "test_auc": mean_std([m["test_auc"] for m in seed_metrics]),
        "threshold_pctl95": {
            k: mean_std([m["threshold_pctl95"][k] for m in seed_metrics])
            for k in ["precision", "recall", "f1", "accuracy"]
        },
    }
    (RESULTS_DIR / f"{variant_name}_summary.json").write_text(json.dumps(summary, indent=2))
    return seed_metrics, summary


print("\n" + "=" * 70)
print("Training full_features (22 columns: 18 original + 4 rolling)")
print("=" * 70)
full_seed_metrics, full_summary = run_variant("full_features", FULL_COLS)

print("\n" + "=" * 70)
print("Training no_conn_state (18 columns: 14 original + 4 rolling)")
print("=" * 70)
no_cs_seed_metrics, no_cs_summary = run_variant("no_conn_state", NO_CS_COLS)

print("\n" + "=" * 70)
print("5-seed summary (mean +/- std)")
print("=" * 70)
for name, summary in [("full_features", full_summary), ("no_conn_state", no_cs_summary)]:
    print(f"\n{name} ({summary['n_features']} cols):")
    print(f"  test_auc: {summary['test_auc']['mean']:.4f} +/- {summary['test_auc']['std']:.4f}")
    for k in ["precision", "recall", "f1", "accuracy"]:
        v = summary["threshold_pctl95"][k]
        print(f"  pctl95_{k}: {v['mean']:.4f} +/- {v['std']:.4f}")

ablation_comparison = {"full_features": full_summary, "no_conn_state": no_cs_summary}
(RESULTS_DIR / "ablation_comparison.json").write_text(json.dumps(ablation_comparison, indent=2))
print(f"\nSaved all models under {MODEL_DIR}/, all metrics under {RESULTS_DIR}/")
