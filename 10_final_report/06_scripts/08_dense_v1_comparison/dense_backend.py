"""
Model backend for the Dense autoencoder v1 (full_features variant, 5 seeds),
implementing the same .seeds/.load()/.errors()/.threshold() interface as
06_attack_type_analysis/evaluate_by_attack_type.py's VAEBackend, so
evaluate_group(), compute_error_matrix(), and
07_segmented_injection/evaluate_segmented_injection.py's
run_segmented_evaluation() all work with this backend unchanged -- no
attack-type or segmented-injection evaluation logic is reimplemented here,
only Dense-specific model loading / thresholding.

Model loading and the val-benign-95th-percentile threshold convention are
carried over from analysis/attack_type_breakdown_evaluation.py, the existing
script that already evaluates this exact model by attack type: threshold is
NOT read from a saved metrics file, it is the 95th percentile of
reconstruction error on phase3_dense's own validation-split benign flows,
computed fresh per seed (see that script's module docstring for why).

Unlike the VAE (phase3_vae/05_contamination_sweep), which uses its own
refit scaler (see prepare_contamination_data.py), Dense v1 was trained
directly on features_all_windows.csv's own "_scaled" columns with no refit
-- confirmed by phase3_dense/03_phase3_splits/{train,val,test}_indices.csv's
row_index values landing entirely inside features_all_windows.csv's own
36705 rows (max row_index 36695 there, vs 46494 in the root
03_phase3_splits used for the VAE side, which also spans the two resampled
windows). So Dense v1 flows are looked up via the same
build_combined_features()/load_feature_cols() as the VAE side, with no
separate scaler step needed.
"""
import os

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

DENSE_MODEL_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "04_phase3_models", "full_features")
DENSE_SPLIT_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits")

MODEL_LABEL = "Dense autoencoder v1 (full_features)"
MODEL_DIR_DESC = "phase3_dense/04_phase3_models/full_features"

import sys  # noqa: E402
sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402


class DenseBackend:
    name = "dense_v1_full_features"

    def __init__(self, model_dir=DENSE_MODEL_DIR, seeds=range(5)):
        self.model_dir = model_dir
        self.seeds = list(seeds)
        self._val_benign_X = None

    def _val_benign_X_cached(self):
        if self._val_benign_X is None:
            feature_cols = single.load_feature_cols()
            val_idx = pd.read_csv(os.path.join(DENSE_SPLIT_DIR, "val_indices.csv"))
            combined = single.build_combined_features()
            val_features = combined.loc[val_idx["row_index"].values, feature_cols].reset_index(drop=True)
            benign_mask = (val_idx["is_attack"].values == 0)
            self._val_benign_X = val_features[benign_mask].values.astype("float32")
            print(f"  [DenseBackend] val-benign reference set for threshold_95: {len(self._val_benign_X)} flows")
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


DEFAULT_DENSE_BACKEND = DenseBackend()
