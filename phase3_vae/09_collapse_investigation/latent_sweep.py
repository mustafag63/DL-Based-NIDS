"""Step 2: latent-dimension sweep to separate real posterior collapse from
expected low intrinsic dimensionality.

For latent in {4, 6, 8, 10, 16}, beta=0.25 (confirmed in 08_beta_multiseed/),
train 5 seeds (0-4) each, val-only (test set not touched - same clean
protocol as 06_beta_selection_audit/ and 08_beta_multiseed/). Records val
AUC, active-dim count, and active-dim RATIO (active/latent - the ratio is
the meaningful number here, since the denominator grows with latent).

Question: at small latent (4, 6), is the active ratio high (model is
already using ~all its capacity - genuinely needs that many dims) or does a
chunk still sit inactive even there (real collapse, independent of budget)?

Writes only into 09_collapse_investigation/.
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

BETA = 0.25  # confirmed winner, 08_beta_multiseed/
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
ACTIVE_STD_THRESHOLD = 0.15
LATENTS = [4, 6, 8, 10, 16]
SEEDS = list(range(5))


def reconstruction_error(model, X):
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def count_active_dims(model, X):
    z_mean, _ = model.encoder(X, training=False)
    stds = z_mean.numpy().std(axis=0)
    return int((stds > ACTIVE_STD_THRESHOLD).sum())


def build_and_train(latent_dim, seed, X_train, X_val_benign):
    tf.keras.utils.set_random_seed(seed)
    model = VAE2(INPUT_DIM, latent_dim, beta_init=BETA, dropout_rate=DROPOUT_RATE)
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

    print(f"train: {len(train_df)}  val: {len(val_df)}  beta={BETA} (test not loaded - val-only)\n")

    rows = []
    for latent_dim in LATENTS:
        for seed in SEEDS:
            model, history, train_time = build_and_train(latent_dim, seed, X_train, X_val_benign)
            n_active = count_active_dims(model, X_train)
            active_ratio = n_active / latent_dim

            val_errors = reconstruction_error(model, X_val_all)
            val_auc = roc_auc_score(y_val, val_errors)

            rows.append({
                "latent_dim": latent_dim, "seed": seed, "val_auc": val_auc,
                "n_active_dims": n_active, "active_ratio": active_ratio,
                "epochs_run": len(history.history["loss"]), "train_time_sec": round(train_time, 1),
            })
            print(f"latent={latent_dim:2d} seed={seed}: val_AUC={val_auc:.4f} "
                  f"active={n_active}/{latent_dim} (ratio={active_ratio:.2f}) epochs={len(history.history['loss'])}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(OUT_DIR / "02_latent_sweep_results.csv", index=False)

    summary_rows = []
    for latent_dim in LATENTS:
        sub = per_seed_df[per_seed_df["latent_dim"] == latent_dim]
        summary_rows.append({
            "latent_dim": latent_dim,
            "n_seeds": len(sub),
            "val_auc_mean": sub["val_auc"].mean(),
            "val_auc_std": sub["val_auc"].std(),
            "active_dims_mean": sub["n_active_dims"].mean(),
            "active_dims_std": sub["n_active_dims"].std(),
            "active_ratio_mean": sub["active_ratio"].mean(),
            "active_ratio_std": sub["active_ratio"].std(),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_DIR / "02_latent_sweep_summary.csv", index=False)
    print("\n", summary_df.to_string(index=False), "\n")

    print(f"Saved: {OUT_DIR / '02_latent_sweep_results.csv'}, {OUT_DIR / '02_latent_sweep_summary.csv'}")


if __name__ == "__main__":
    main()
