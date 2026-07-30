"""
Model backend for the VAE v2 (contam_0pct, 19-feature, 5 seeds). Same
.seeds/.load()/.errors()/.threshold() interface as
06_attack_type_analysis/evaluate_by_attack_type.py's VAEBackend, so
evaluate_group()/compute_error_matrix() work unchanged.

Scoring is DETERMINISTIC z_mean ONLY (O2 fix applied at v2's creation --
the stochastic single-eps-sample method is not offered here at all, unlike
v1's VAEBackend which keeps both for historical comparison). threshold_95 is
the 95th percentile of DETERMINISTIC error on v2's own held-out val-benign
set (01_data_v2/val_benign.csv, same flow membership as v1's val_benign.csv
-- see prepare_contamination_data_v2_concurrency.py's cross-check),
recalibrated per seed -- the stochastic threshold.json values written by
train_vae_v2.py are NOT used for evaluation, only kept in the model
directory for parity with v1's file format.

Test-time features: 09_dense_v2_comparison/dense_backend_v2.py's
build_combined_features_v2()/load_feature_cols_v2() -- the same v2
(19-feature) combined table Dense v2 evaluates against (row_index spans
windows 01-08 + the two resampled windows, includes concurrency_src_1s_scaled).
This mirrors v1's VAEBackend, which also evaluates against the Dense-side
combined table rather than its own window_10-based test_set.csv.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import tensorflow as tf

import keras.src.utils.python_utils as _keras_python_utils  # noqa: E402
_keras_python_utils.tf = tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DENSE_V2_DIR = os.path.join(PROJECT_ROOT, "09_dense_v2_comparison")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_V2_DIR)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2, build_combined_features_v2  # noqa: E402

SWEEP_DIR = os.path.join(PROJECT_ROOT, "phase3_vae", "05_contamination_sweep")
MODEL_DIR = os.path.join(SWEEP_DIR, "04_models", "contam_0pct")
VAL_BENIGN_PATH = os.path.join(SWEEP_DIR, "01_data_v2", "val_benign.csv")

MODEL_LABEL = "VAE (contam_0pct, 19 features: +concurrency_src_1s, deterministic z_mean)"
MODEL_DIR_DESC = "phase3_vae/05_contamination_sweep/04_models/contam_0pct"

reconstruction_error_zmean = single.reconstruction_error_zmean


class VAEBackendV2:
    name = "vae_v2_clean_contam0pct_zmean"

    def __init__(self, model_dir=MODEL_DIR, seeds=range(5)):
        self.model_dir = model_dir
        self.seeds = list(seeds)
        self._model_cache = {}
        self._val_benign_X = None

    def _val_benign_X_cached(self):
        if self._val_benign_X is None:
            val_df = pd.read_csv(VAL_BENIGN_PATH)
            assert (val_df["is_attack"] == 0).all()
            feature_cols = load_feature_cols_v2()
            self._val_benign_X = val_df[feature_cols].values.astype("float32")
            print(f"  [VAEBackendV2] val-benign reference set for deterministic "
                  f"threshold_95: {len(self._val_benign_X)} flows")
        return self._val_benign_X

    def load(self, seed):
        if seed in self._model_cache:
            return self._model_cache[seed]
        seed_dir = os.path.join(self.model_dir, f"seed_{seed}")
        encoder = tf.keras.models.load_model(os.path.join(seed_dir, "encoder.keras"), safe_mode=False)
        decoder = tf.keras.models.load_model(os.path.join(seed_dir, "decoder.keras"), safe_mode=False)
        val_errors = reconstruction_error_zmean(encoder, decoder, self._val_benign_X_cached())
        threshold_95_zmean = float(np.percentile(val_errors, 95))
        model = {"encoder": encoder, "decoder": decoder, "threshold_95_zmean": threshold_95_zmean}
        self._model_cache[seed] = model
        return model

    def errors(self, model, X, seed):
        return reconstruction_error_zmean(model["encoder"], model["decoder"], X)

    def threshold(self, model, seed):
        return model["threshold_95_zmean"]


DEFAULT_VAE_V2_BACKEND = VAEBackendV2()
