"""
Canonical Dense architecture retrained on the 19-feature (original 18 +
concurrency_src_1s_scaled) dataset, 5 seeds -- this is the current canonical
model (see 02_phase2_feature_extraction/features_with_concurrency/ and
CHANGELOG.md). The former 18-feature model that used to live at
full_features/ has been archived to V1_ARCHIVE/phase3_dense/04_phase3_models/
full_features/ (2026-07-30 v1->v2 rollout); this script's own output now
occupies the full_features/ name directly, no version suffix.

Architecture/hyperparameters copied verbatim from phase3_dense_autoencoder.ipynb
/ 08_dense_v1_comparison/dense_backend.py (same threshold_95 convention):
Input(N) -> Dense(16, relu, L2 1e-4) -> Dropout(0.15) -> Dense(8, relu, L2,
bottleneck) -> Dropout(0.15) -> Dense(16, relu, L2) -> Dense(N, linear);
adam/mse, epochs<=200, batch 128, EarlyStopping(val_loss, patience=12,
restore_best_weights). Same phase3_dense/03_phase3_splits/*_indices.csv
splits as before -- only the feature table changed (19th column added).
"""
import json
import os
import time

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
SPLIT_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits")
FEATURES_V2 = os.path.join(PROJECT_ROOT, "02_phase2_feature_extraction",
                           "features_with_concurrency", "features_v2_all_rows.csv")
MODEL_DIR = os.path.join(HERE, "full_features")
os.makedirs(MODEL_DIR, exist_ok=True)

SEEDS = [0, 1, 2, 3, 4]
META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts", "row_index"]


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


def main():
    features = pd.read_csv(FEATURES_V2)
    feature_cols = [c for c in features.columns if c not in META_COLS]
    print(f"n_features={len(feature_cols)}: {feature_cols}")

    train_idx = pd.read_csv(os.path.join(SPLIT_DIR, "train_indices.csv"))["row_index"].values
    val_idx = pd.read_csv(os.path.join(SPLIT_DIR, "val_indices.csv"))["row_index"].values

    train_df = features.iloc[train_idx].reset_index(drop=True)
    val_df = features.iloc[val_idx].reset_index(drop=True)
    assert (train_df["is_attack"] == 0).all(), "train split must be 100% benign"

    X_train = train_df[feature_cols].values.astype("float32")
    val_benign_mask = val_df["is_attack"] == 0
    X_val_benign = val_df.loc[val_benign_mask, feature_cols].values.astype("float32")
    print(f"train={len(X_train)} (all benign), val_benign={len(X_val_benign)}")

    meta = []
    for seed in SEEDS:
        t0 = time.time()
        model = build_model(len(feature_cols), seed)
        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=12, restore_best_weights=True)
        history = model.fit(
            X_train, X_train, validation_data=(X_val_benign, X_val_benign),
            epochs=200, batch_size=128, shuffle=True, callbacks=[early_stop], verbose=0)
        model.save(os.path.join(MODEL_DIR, f"autoencoder_seed{seed}.keras"))
        meta.append({
            "seed": seed, "epochs_run": len(history.history["loss"]),
            "final_val_loss": float(np.min(history.history["val_loss"])),
            "train_time_sec": round(time.time() - t0, 1),
        })
        print(f"seed={seed}: epochs={meta[-1]['epochs_run']} "
              f"best_val_loss={meta[-1]['final_val_loss']:.5f} time={meta[-1]['train_time_sec']}s")

    json.dump({"feature_cols": feature_cols, "seeds": meta},
              open(os.path.join(HERE, "training_meta.json"), "w"), indent=2)
    print(f"\nWrote models to {MODEL_DIR}")


if __name__ == "__main__":
    main()
