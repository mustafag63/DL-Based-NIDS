"""
Model backend for canonical Dense (full_features: original 18 +
concurrency_src_1s_scaled, 5 seeds) -- same .seeds/.load()/.errors()/
.threshold() interface as 08_dense_v1_comparison/dense_backend.py's
DenseBackend, so evaluate_group()/compute_error_matrix() from
06_attack_type_analysis/evaluate_by_attack_type.py work unchanged.

Feature source: 02_phase2_feature_extraction/features_with_concurrency/
features_v2_all_rows.csv, row_index-indexed exactly like the v1 combined
table (same row_index semantics, v2 just has one extra column). Threshold
convention unchanged: threshold_95 = 95th percentile of reconstruction error
on phase3_dense's own validation-split benign flows (v2 feature values),
computed fresh per seed.
"""
import os

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

FEATURES_V2_PATH = os.path.join(PROJECT_ROOT, "02_phase2_feature_extraction",
                                "features_with_concurrency", "features_v2_all_rows.csv")
DENSE_MODEL_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "04_phase3_models", "full_features")
DENSE_SPLIT_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits")

MODEL_LABEL = "Dense autoencoder (full_features + concurrency_src_1s)"
MODEL_DIR_DESC = "phase3_dense/04_phase3_models/full_features"

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts", "row_index"]


def load_feature_cols_v2():
    features = pd.read_csv(FEATURES_V2_PATH, nrows=1)
    return [c for c in features.columns if c not in META_COLS]


def build_combined_features_v2():
    """row_index -> full v2 feature row, same semantics as v1's
    build_combined_features() in 06_attack_type_analysis/evaluate_by_attack_type.py."""
    df = pd.read_csv(FEATURES_V2_PATH)
    return df.set_index("row_index")


class DenseBackendV2:
    name = "dense_v2_full_features_concurrency"

    def __init__(self, model_dir=DENSE_MODEL_DIR, seeds=range(5)):
        self.model_dir = model_dir
        self.seeds = list(seeds)
        self._val_benign_X = None

    def _val_benign_X_cached(self):
        if self._val_benign_X is None:
            feature_cols = load_feature_cols_v2()
            val_idx = pd.read_csv(os.path.join(DENSE_SPLIT_DIR, "val_indices.csv"))
            combined = build_combined_features_v2()
            val_features = combined.loc[val_idx["row_index"].values, feature_cols].reset_index(drop=True)
            benign_mask = (val_idx["is_attack"].values == 0)
            self._val_benign_X = val_features[benign_mask].values.astype("float32")
            print(f"  [DenseBackendV2] val-benign reference set for threshold_95: {len(self._val_benign_X)} flows")
        return self._val_benign_X

    def load(self, seed):
        return tf.keras.models.load_model(os.path.join(self.model_dir, f"autoencoder_seed{seed}.keras"))

    def errors(self, model, X, seed):
        recon = model.predict(X, verbose=0)
        return np.mean(np.square(X - recon), axis=1)

    def threshold(self, model, seed):
        val_X = self._val_benign_X_cached()
        val_errors = self.errors(model, val_X, seed)
        return float(np.percentile(val_errors, 95))


DEFAULT_DENSE_V2_BACKEND = DenseBackendV2()
