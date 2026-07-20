"""Seed-variance check for the final VAE config (latent=10, beta=0.25).

phase3_vae_autoencoder.ipynb picks beta=0.25 using a single training run
(seed=0) per variant (see 06_beta_selection_audit/ for the leak that was
fixed in that selection). This script asks a different question: how much
does the *final*, already-selected config (latent=10, beta=0.25) move around
just from weight-init seed? Architecture/hyperparameters are copied verbatim
from the notebook's section 9 (build_and_train_v2 / VARIANTS beta=0.25 entry)
- only the seed varies, 10 times (0-9).

Test-set usage note: unlike the beta-selection comparison, there is no
selection happening here - all 10 seeds are scored on the test set purely to
observe the spread of a fixed, already-chosen config. No decision is made
from the test numbers, so scoring all 10 is not leakage (contrast with
06_beta_selection_audit/README.md, where scoring multiple *candidates* on
test before picking one was the problem).

Writes only into 07_seed_variance/ - does not touch 04_phase3_models/,
latest_run/, or 06_beta_selection_audit/.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from scipy.stats import trim_mean
from sklearn.metrics import f1_score, roc_auc_score

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

# --- Frozen final-config hyperparameters (phase3_vae_autoencoder.ipynb, section 9) ---
CHOSEN_LATENT = 10
BETA = 0.25
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
ACTIVE_STD_THRESHOLD = 0.15  # same threshold as the health-check's active-dim diagnostic

SEEDS = list(range(10))
CURRENT_FINAL_MODEL_SEED = 0  # notebook's SEED = 0, used to train vae_encoder_final.keras / vae_decoder_final.keras


def reconstruction_error(model, X):
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def count_active_dims(model, X):
    z_mean, _ = model.encoder(X, training=False)
    stds = z_mean.numpy().std(axis=0)
    return int((stds > ACTIVE_STD_THRESHOLD).sum()), stds


def build_and_train(seed, X_train, X_val_benign):
    tf.keras.utils.set_random_seed(seed)
    model = VAE2(INPUT_DIM, CHOSEN_LATENT, beta_init=BETA, dropout_rate=DROPOUT_RATE)
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
    test_idx = pd.read_csv(DENSE_SPLIT_DIR / "test_indices.csv")["row_index"].values
    val_df = features_all.iloc[val_idx].reset_index(drop=True)
    test_df = features_all.iloc[test_idx].reset_index(drop=True)

    val_benign_mask = val_df["is_attack"] == 0
    X_val_benign = val_df.loc[val_benign_mask, FEATURE_COLS].values.astype("float32")
    X_val_all = val_df[FEATURE_COLS].values.astype("float32")
    y_val = val_df["is_attack"].values
    X_test = test_df[FEATURE_COLS].values.astype("float32")
    y_test = test_df["is_attack"].values

    print(f"train: {len(train_df)}  val: {len(val_df)}  test: {len(test_df)}")
    print(f"config: latent={CHOSEN_LATENT} beta={BETA} dropout={DROPOUT_RATE} "
          f"patience={PATIENCE} clipnorm=1.0 z_log_var_clip=[-10,10]\n")

    rows = []
    for seed in SEEDS:
        model, history, train_time = build_and_train(seed, X_train, X_val_benign)
        n_active_train, _ = count_active_dims(model, X_train)

        val_errors = reconstruction_error(model, X_val_all)
        val_auc = roc_auc_score(y_val, val_errors)

        val_errors_benign = reconstruction_error(model, X_val_benign)
        thr_pctl = float(np.percentile(val_errors_benign, 95))

        test_errors = reconstruction_error(model, X_test)
        test_auc = roc_auc_score(y_test, test_errors)
        test_f1 = f1_score(y_test, (test_errors > thr_pctl).astype(int), zero_division=0)

        rows.append({
            "seed": seed,
            "val_auc": val_auc,
            "test_auc": test_auc,
            "test_f1_pctl95": test_f1,
            "n_active_dims_train": n_active_train,
            "epochs_run": len(history.history["loss"]),
            "train_time_sec": round(train_time, 1),
            "is_current_final_model_seed": seed == CURRENT_FINAL_MODEL_SEED,
        })
        print(f"seed={seed}: val_AUC={val_auc:.4f} test_AUC={test_auc:.4f} test_F1={test_f1:.4f} "
              f"active_dims={n_active_train}/{CHOSEN_LATENT} epochs={len(history.history['loss'])}"
              f"{'  <-- current saved final model' if seed == CURRENT_FINAL_MODEL_SEED else ''}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(OUT_DIR / "results_per_seed.csv", index=False)

    metric_cols = ["val_auc", "test_auc", "test_f1_pctl95", "n_active_dims_train"]

    def trimmed_mean(s):
        # 10 seeds, proportiontocut=0.2 drops the 2 lowest + 2 highest before
        # averaging - same robust-mean convention as 05_contamination_sweep.
        return trim_mean(s, proportiontocut=0.2)

    trimmed_mean.__name__ = "trimmed_mean"

    summary_flat = {}
    for col in metric_cols:
        s = per_seed_df[col]
        summary_flat[f"{col}_mean"] = s.mean()
        summary_flat[f"{col}_std"] = s.std()
        summary_flat[f"{col}_median"] = s.median()
        summary_flat[f"{col}_trimmed_mean"] = trimmed_mean(s.to_numpy())
    summary_df = pd.DataFrame([summary_flat])
    summary_df.insert(0, "n_seeds", len(SEEDS))
    summary_df.to_csv(OUT_DIR / "results_summary.csv", index=False)

    print(f"\nWrote {OUT_DIR / 'results_per_seed.csv'} and {OUT_DIR / 'results_summary.csv'}")
    print(f"\ntest_auc: {summary_flat['test_auc_mean']:.4f} +/- {summary_flat['test_auc_std']:.4f} (mean +/- std, n=10)")
    print(f"test_f1_pctl95: {summary_flat['test_f1_pctl95_mean']:.4f} +/- {summary_flat['test_f1_pctl95_std']:.4f}")
    print(f"active_dims: {summary_flat['n_active_dims_train_mean']:.2f} +/- {summary_flat['n_active_dims_train_std']:.2f}")


if __name__ == "__main__":
    main()
