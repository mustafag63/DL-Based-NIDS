"""Step 3: free-bits (per-dimension KL lower bound) experiment at latent=10,
beta=0.25 (fixed).

Standard free-bits trick (Kingma et al. 2016): clamp each latent dimension's
own KL term to a minimum lambda ("free bits", in nats) before summing across
dimensions - `kl_per_dim = max(kl_per_dim, lambda)`. A dimension whose KL
already exceeds lambda is unaffected; a dimension the optimizer is pushing
toward the prior (collapsing) stops getting gradient pressure to shrink
further once its per-dim KL hits lambda, so it can't be driven all the way to
"inactive" purely by the KL term.

VAE2 (model_layers.py) is not modified - this script defines a local
subclass that overrides `_compute_losses` only, so 04_phase3_models/,
06_beta_selection_audit/, 07_seed_variance/, 08_beta_multiseed/ and the
notebook's shared module all stay untouched.

Question: is there a lambda that raises active-dim count without pushing val
AUC below the 08_beta_multiseed/ reference band for beta=0.25
(0.8181 +/- 0.0194, i.e. mean 0.8181, lower edge ~0.7987)?

val-only (test set never loaded) - same clean protocol as the rest of this
investigation.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import roc_auc_score

BASE = Path(__file__).resolve().parent.parent  # phase3_vae/
PROJECT_ROOT = BASE.parent
DENSE_SPLIT_DIR = PROJECT_ROOT / "phase3_dense" / "03_phase3_splits"
FEAT_ALL_PATH = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features" / "features_all_windows.csv"
TRAIN_PATH = BASE / "window10_clean_train.csv"

OUT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE))
from model_layers import ClipLogVar, VAE2  # noqa: E402

FEATURE_COLS = [
    "duration_scaled", "orig_bytes_scaled", "resp_bytes_scaled",
    "orig_pkts_scaled", "resp_pkts_scaled",
    "bytes_per_sec_scaled", "pkts_per_sec_scaled", "byte_ratio_scaled",
    "proto_tcp", "proto_udp",
    "service_dns", "service_http", "service_none", "service_ssh",
    "conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF",
]
INPUT_DIM = len(FEATURE_COLS)
assert INPUT_DIM == 18

LATENT_DIM = 10
BETA = 0.25
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
ACTIVE_STD_THRESHOLD = 0.15
FREE_BITS_LAMBDAS = [0.0, 0.1, 0.25, 0.5, 1.0]  # nats per dim; 0.0 = no free bits (baseline, reproduces 08_beta_multiseed)
SEEDS = list(range(5))

REFERENCE_VAL_AUC_MEAN = 0.8181  # 08_beta_multiseed/, beta=0.25, n=5 seeds
REFERENCE_VAL_AUC_STD = 0.0194
REFERENCE_VAL_AUC_FLOOR = REFERENCE_VAL_AUC_MEAN - REFERENCE_VAL_AUC_STD  # 0.7987


@tf.keras.utils.register_keras_serializable(package="phase3_vae_collapse_investigation")
class VAEFreeBits(VAE2):
    """VAE2 with an optional per-dimension KL floor (free bits)."""
    def __init__(self, *args, free_bits_lambda=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.free_bits_lambda = free_bits_lambda

    def _compute_losses(self, x, y):
        recon, z_mean, z_log_var = self(x, training=True)
        recon_loss = tf.reduce_mean(tf.reduce_sum(tf.square(y - recon), axis=1))
        kl_per_dim = -0.5 * (1 + z_log_var - tf.square(z_mean) - tf.exp(z_log_var))
        if self.free_bits_lambda > 0:
            kl_per_dim = tf.maximum(kl_per_dim, self.free_bits_lambda)
        kl_loss = tf.reduce_mean(tf.reduce_sum(kl_per_dim, axis=1))
        total_loss = recon_loss + self.beta * kl_loss
        return total_loss, recon_loss, kl_loss


def reconstruction_error(model, X):
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def count_active_dims(model, X):
    z_mean, _ = model.encoder(X, training=False)
    stds = z_mean.numpy().std(axis=0)
    return int((stds > ACTIVE_STD_THRESHOLD).sum())


def build_and_train(free_bits_lambda, seed, X_train, X_val_benign):
    tf.keras.utils.set_random_seed(seed)
    model = VAEFreeBits(INPUT_DIM, LATENT_DIM, beta_init=BETA, dropout_rate=DROPOUT_RATE,
                         free_bits_lambda=free_bits_lambda)
    model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
    early_stop = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE, restore_best_weights=True)
    t0 = time.time()
    history = model.fit(
        X_train, X_train, validation_data=(X_val_benign, X_val_benign),
        epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True, callbacks=[early_stop], verbose=0,
    )
    return model, history, time.time() - t0


def main():
    print(f"TensorFlow {tf.__version__}, GPU: {tf.config.list_physical_devices('GPU')}")

    train_df = pd.read_csv(TRAIN_PATH)
    assert (train_df["is_attack"] == 0).all()
    X_train = train_df[FEATURE_COLS].values.astype("float32")

    features_all = pd.read_csv(FEAT_ALL_PATH)
    val_idx = pd.read_csv(DENSE_SPLIT_DIR / "val_indices.csv")["row_index"].values
    val_df = features_all.iloc[val_idx].reset_index(drop=True)

    val_benign_mask = val_df["is_attack"] == 0
    X_val_benign = val_df.loc[val_benign_mask, FEATURE_COLS].values.astype("float32")
    X_val_all = val_df[FEATURE_COLS].values.astype("float32")
    y_val = val_df["is_attack"].values

    print(f"train: {len(train_df)}  val: {len(val_df)}  latent={LATENT_DIM} beta={BETA} "
          f"(test not loaded - val-only)\n")

    rows = []
    for lam in FREE_BITS_LAMBDAS:
        for seed in SEEDS:
            model, history, train_time = build_and_train(lam, seed, X_train, X_val_benign)
            n_active = count_active_dims(model, X_train)

            val_errors = reconstruction_error(model, X_val_all)
            val_auc = roc_auc_score(y_val, val_errors)

            rows.append({
                "free_bits_lambda": lam, "seed": seed, "val_auc": val_auc,
                "n_active_dims": n_active, "active_ratio": n_active / LATENT_DIM,
                "epochs_run": len(history.history["loss"]), "train_time_sec": round(train_time, 1),
            })
            print(f"lambda={lam:.2f} seed={seed}: val_AUC={val_auc:.4f} "
                  f"active={n_active}/{LATENT_DIM} epochs={len(history.history['loss'])}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(OUT_DIR / "03_free_bits_results.csv", index=False)

    summary_rows = []
    for lam in FREE_BITS_LAMBDAS:
        sub = per_seed_df[per_seed_df["free_bits_lambda"] == lam]
        val_auc_mean = sub["val_auc"].mean()
        summary_rows.append({
            "free_bits_lambda": lam,
            "n_seeds": len(sub),
            "val_auc_mean": val_auc_mean,
            "val_auc_std": sub["val_auc"].std(),
            "active_dims_mean": sub["n_active_dims"].mean(),
            "active_dims_std": sub["n_active_dims"].std(),
            "active_ratio_mean": sub["active_ratio"].mean(),
            "meets_reference_floor": bool(val_auc_mean >= REFERENCE_VAL_AUC_FLOOR),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_DIR / "03_free_bits_summary.csv", index=False)
    print("\n", summary_df.to_string(index=False), "\n")
    print(f"Reference (08_beta_multiseed, beta=0.25, no free bits): "
          f"val_AUC = {REFERENCE_VAL_AUC_MEAN} +/- {REFERENCE_VAL_AUC_STD} (floor={REFERENCE_VAL_AUC_FLOOR:.4f})")

    print(f"\nSaved: {OUT_DIR / '03_free_bits_results.csv'}, {OUT_DIR / '03_free_bits_summary.csv'}")


if __name__ == "__main__":
    main()
