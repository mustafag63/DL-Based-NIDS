"""
Temporal-feature side experiment: retrain Dense autoencoder v1 with the 18
canonical features + 1 new per-source-IP inter-arrival-time feature
(iat_log_scaled, built by build_iat_feature.py), 3 seeds, and compare per
attack type against the 18-feature Dense v1 baseline
(08_dense_v1_comparison/results_single_attack_type_dense.md).

Everything except the feature set is held fixed:
  - Same splits: phase3_dense/03_phase3_splits (train is all-benign).
  - Same architecture/hyperparameters as phase3_dense_autoencoder.ipynb:
    Input(N) -> Dense(16, relu, L2 1e-4) -> Dropout(0.15) -> Dense(8, relu,
    L2, bottleneck) -> Dropout(0.15) -> Dense(16, relu, L2) -> Dense(N,
    linear); adam, mse, epochs<=200, batch 128, EarlyStopping(val_loss,
    patience=12, restore_best_weights), val loss on benign val flows only.
  - Same threshold convention: threshold_95 = per-seed 95th percentile of
    val-benign reconstruction error.
  - Same evaluation: 06_attack_type_analysis's assemble_labeled_features_df /
    evaluate_group, imported verbatim, on the same test_with_attack_type.csv.

Extra: an IAT knock-out ablation (item 4 of the experiment brief) -- the same
trained 19-feature models evaluated with the iat_log_scaled column frozen to
its benign-train mean, to measure how much of any change is carried by the
new feature itself vs. by retraining jitter/interactions.

Writes (all inside 13_temporal_feature_experiment/):
  models/autoencoder_seed{0,1,2}.keras
  results_single_attack_type_iat.csv / results_knockout.csv
  per-seed training metadata in training_meta.json
Canonical folders are only read, never written.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402

FEATURES_ALL_WINDOWS = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv")
DENSE_SPLIT_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits")
IAT_PATH = os.path.join(HERE, "iat_feature_all_rows.csv")
MODEL_DIR = os.path.join(HERE, "models")

SEEDS = [0, 1, 2]
IAT_COL = "iat_log_scaled"


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


def load_training_frames(feature_cols_19):
    features = pd.read_csv(FEATURES_ALL_WINDOWS)
    iat = pd.read_csv(IAT_PATH, usecols=["row_index", IAT_COL]).set_index("row_index")
    features[IAT_COL] = iat.loc[features.index, IAT_COL].values

    def take(name):
        idx = pd.read_csv(os.path.join(DENSE_SPLIT_DIR, f"{name}_indices.csv"))
        df = features.iloc[idx["row_index"].values].reset_index(drop=True)
        assert (df["is_attack"].values == idx["is_attack"].values).all()
        return df

    train_df, val_df = take("train"), take("val")
    assert (train_df["is_attack"] == 0).all(), "train split must be 100% benign"
    X_train = train_df[feature_cols_19].values.astype("float32")
    X_val_benign = val_df.loc[val_df["is_attack"] == 0, feature_cols_19].values.astype("float32")
    return X_train, X_val_benign


class IATDenseBackend:
    """Same 4-method interface as 08_dense_v1_comparison's DenseBackend, for
    the 19-feature models trained here. `freeze_iat_to` != None replaces the
    IAT column with that constant at inference time (knock-out ablation)."""
    name = "dense_v1_plus_iat"

    def __init__(self, feature_cols, val_benign_X, seeds=SEEDS, freeze_iat_to=None):
        self.feature_cols = feature_cols
        self.seeds = list(seeds)
        self.iat_pos = feature_cols.index(IAT_COL)
        self.freeze_iat_to = freeze_iat_to
        self._val_benign_X = self._maybe_freeze(val_benign_X)

    def _maybe_freeze(self, X):
        if self.freeze_iat_to is None:
            return X
        X = X.copy()
        X[:, self.iat_pos] = self.freeze_iat_to
        return X

    def load(self, seed):
        return tf.keras.models.load_model(os.path.join(MODEL_DIR, f"autoencoder_seed{seed}.keras"))

    def errors(self, model, X, seed):
        recon = model.predict(self._maybe_freeze(np.asarray(X)), verbose=0)
        return np.mean(np.square(self._maybe_freeze(np.asarray(X)) - recon), axis=1)

    def threshold(self, model, seed):
        val_errors = self.errors(model, self._val_benign_X, seed)
        return float(np.percentile(val_errors, 95))


def summarize(per_seed_df):
    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    return summary.reset_index()


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    feature_cols_18 = single.load_feature_cols()
    feature_cols_19 = feature_cols_18 + [IAT_COL]

    # ------------------------------------------------------------------ train
    X_train, X_val_benign = load_training_frames(feature_cols_19)
    print(f"train={len(X_train)} (all benign), val_benign={len(X_val_benign)}, "
          f"n_features={len(feature_cols_19)}")
    meta = []
    for seed in SEEDS:
        t0 = time.time()
        model = build_model(len(feature_cols_19), seed)
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
    json.dump({"seeds": meta, "feature_cols": feature_cols_19},
              open(os.path.join(HERE, "training_meta.json"), "w"), indent=2)

    # ------------------------------------------------------------------- eval
    df18 = single.assemble_labeled_features_df(feature_cols_18)
    iat = pd.read_csv(IAT_PATH, usecols=["row_index", IAT_COL]).set_index("row_index")
    df = df18.copy()
    df[IAT_COL] = iat.loc[df["row_index"].values, IAT_COL].values
    assert not df[IAT_COL].isna().any()

    train_iat_mean = float(iat.loc[
        pd.read_csv(os.path.join(DENSE_SPLIT_DIR, "train_indices.csv"))["row_index"].values,
        IAT_COL].mean())
    print(f"benign-train mean of {IAT_COL} (knock-out constant): {train_iat_mean:.4f}")

    for label, backend, out_csv in [
        ("with IAT", IATDenseBackend(feature_cols_19, X_val_benign),
         os.path.join(HERE, "results_single_attack_type_iat.csv")),
        ("IAT knocked out", IATDenseBackend(feature_cols_19, X_val_benign, freeze_iat_to=train_iat_mean),
         os.path.join(HERE, "results_knockout.csv")),
    ]:
        print(f"\n##### evaluation: {label} #####")
        rows = []
        for attack_type in single.ATTACK_TYPES:
            subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
            rows.extend(single.evaluate_group(subset, feature_cols_19, attack_type, backend=backend))
        per_seed = pd.DataFrame(rows)
        per_seed.to_csv(out_csv.replace(".csv", "_per_seed.csv"), index=False)
        summarize(per_seed).to_csv(out_csv, index=False)
        print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
