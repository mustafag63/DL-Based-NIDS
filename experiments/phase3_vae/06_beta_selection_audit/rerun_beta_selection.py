"""Leak-free re-run of the beta-variant comparison (phase3_vae, section 9).

Original notebook cells (phase3_vae_autoencoder.ipynb, cells 22 & 26) computed
test_auc/test_f1 for ALL 4 variants during the sweep, and the selection rule
(cell 26) compared variants on test_auc instead of val_auc. Both are test-set
leakage. This script re-runs the exact same 4 variants (same hyperparameters:
latent=10, patience=12, clipnorm=1.0, z_log_var clip [-10,10]) using ONLY
val_indices.csv for selection. The test set is loaded but not touched until
the very end, after the winning config is already fixed, and is evaluated
exactly once.

Does not touch phase3_vae/04_phase3_models/*.keras (the "latest_run" final
artifacts) - models trained here are kept only in 06_beta_selection_audit/.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import f1_score, roc_auc_score

BASE = Path(__file__).resolve().parent.parent  # phase3_vae/
PROJECT_ROOT = BASE.parent
DENSE_SPLIT_DIR = PROJECT_ROOT / "phase3_dense" / "03_phase3_splits"
FEAT_ALL_PATH = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features" / "features_all_windows.csv"
TRAIN_PATH = BASE / "window10_clean_train.csv"

OUT_DIR = Path(__file__).resolve().parent
MODEL_DIR = OUT_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

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

CHOSEN_LATENT = 10  # from the (leak-free) latent sweep in section 4, unaffected by this audit
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
SEED = 0
ACTIVE_STD_THRESHOLD = 0.15
ANNEAL_EPOCHS = 40
ACTIVE_DIM_AUC_TOLERANCE = 0.03  # same tolerance rule as original: allow <=0.03 val AUC drop for more active dims

VARIANTS = [
    ("beta=1.0 (baseline)", 1.0, 0),
    ("beta=0.5", 0.5, 0),
    ("beta=0.25", 0.25, 0),
    ("KL-annealing (sigmoid -> 1.0)", 1.0, ANNEAL_EPOCHS),
]


def reconstruction_error(model, X):
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def count_active_dims(model, X):
    z_mean, _ = model.encoder(X, training=False)
    stds = z_mean.numpy().std(axis=0)
    return int((stds > ACTIVE_STD_THRESHOLD).sum()), stds


class BetaScheduler(tf.keras.callbacks.Callback):
    def __init__(self, target_beta, anneal_epochs):
        super().__init__()
        self.target_beta = target_beta
        self.anneal_epochs = anneal_epochs

    def on_epoch_begin(self, epoch, logs=None):
        if self.anneal_epochs <= 0 or epoch >= self.anneal_epochs:
            new_beta = self.target_beta
        else:
            k = 10.0 / self.anneal_epochs
            new_beta = self.target_beta / (1.0 + np.exp(-k * (epoch - self.anneal_epochs / 2)))
        self.model.beta.assign(new_beta)


def build_and_train_v2(latent_dim, beta_target, seed, anneal_epochs, X_train, X_val_benign):
    tf.keras.utils.set_random_seed(seed)
    beta_init = 0.0 if anneal_epochs > 0 else beta_target
    model = VAE2(INPUT_DIM, latent_dim, beta_init=beta_init, dropout_rate=DROPOUT_RATE)
    model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
    callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE, restore_best_weights=True)]
    if anneal_epochs > 0:
        callbacks.append(BetaScheduler(beta_target, anneal_epochs))
    t0 = time.time()
    history = model.fit(
        X_train, X_train, validation_data=(X_val_benign, X_val_benign),
        epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True, callbacks=callbacks, verbose=0,
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

    # Test set is loaded here for later reference but MUST NOT be touched
    # until the winning variant is fixed below.
    X_test = test_df[FEATURE_COLS].values.astype("float32")
    y_test = test_df["is_attack"].values

    print(f"train: {len(train_df)}  val: {len(val_df)}  test(untouched for now): {len(test_df)}")

    # ---- Step 1: train + compare all 4 variants using VAL ONLY ----
    rows = []
    models = {}
    for name, beta_target, anneal_epochs in VARIANTS:
        model, history, train_time = build_and_train_v2(
            CHOSEN_LATENT, beta_target, seed=SEED, anneal_epochs=anneal_epochs,
            X_train=X_train, X_val_benign=X_val_benign,
        )
        n_active_train, _ = count_active_dims(model, X_train)
        n_active_val, _ = count_active_dims(model, X_val_benign)

        val_errors = reconstruction_error(model, X_val_all)
        val_auc = roc_auc_score(y_val, val_errors)

        rows.append({
            "variant": name, "val_auc": val_auc,
            "n_active_dims_train": n_active_train, "n_active_dims_val": n_active_val,
            "final_recon_loss": history.history["val_recon_loss"][-1],
            "final_kl_loss": history.history["val_kl_loss"][-1],
            "epochs_run": len(history.history["loss"]),
        })
        models[name] = (model, history)
        print(f"{name}: val_AUC={val_auc:.4f} active_dims(train)={n_active_train}/{CHOSEN_LATENT} "
              f"active_dims(val)={n_active_val}/{CHOSEN_LATENT} epochs={len(history.history['loss'])}")

    variant_df = pd.DataFrame(rows).set_index("variant")
    print("\n", variant_df, "\n")

    # ---- Step 2: selection on VAL AUC + active dims only (test untouched) ----
    baseline_name = "beta=1.0 (baseline)"
    baseline_auc = variant_df.loc[baseline_name, "val_auc"]
    baseline_active = variant_df.loc[baseline_name, "n_active_dims_train"]

    reasoning = [f"baseline ({baseline_name}): val_AUC={baseline_auc:.4f}, active_dims={baseline_active}/{CHOSEN_LATENT}"]
    qualifying = [(baseline_name, baseline_active, baseline_auc)]
    for name, _, _ in VARIANTS:
        if name == baseline_name:
            continue
        auc = variant_df.loc[name, "val_auc"]
        active = variant_df.loc[name, "n_active_dims_train"]
        drop = baseline_auc - auc
        if drop <= ACTIVE_DIM_AUC_TOLERANCE and active > baseline_active:
            reasoning.append(f"{name}: val_AUC={auc:.4f} (drop={drop:.4f} <= tolerance {ACTIVE_DIM_AUC_TOLERANCE}), "
                              f"active_dims={active}/{CHOSEN_LATENT} > baseline's {baseline_active} -> QUALIFIES")
            qualifying.append((name, active, auc))
        elif active > baseline_active:
            reasoning.append(f"{name}: val_AUC={auc:.4f} (drop={drop:.4f} > tolerance {ACTIVE_DIM_AUC_TOLERANCE} despite "
                              f"active_dims={active}/{CHOSEN_LATENT} > baseline) -> REJECTED, AUC cost too high")
        else:
            reasoning.append(f"{name}: val_AUC={auc:.4f}, active_dims={active}/{CHOSEN_LATENT} <= baseline's "
                              f"{baseline_active} -> no improvement on the metric that matters here, REJECTED")

    qualifying.sort(key=lambda t: (t[1], t[2]), reverse=True)
    selected_variant = qualifying[0][0]
    reasoning.append(f"\n=> SELECTED variant: '{selected_variant}' "
                      f"(active_dims={qualifying[0][1]}/{CHOSEN_LATENT}, val_AUC={qualifying[0][2]:.4f})")
    print("\n".join(reasoning))

    final_model, final_history = models[selected_variant]

    # ---- Step 3: ONE-TIME test evaluation of the winning config only ----
    val_errors_benign = reconstruction_error(final_model, X_val_benign)
    thr_pctl = float(np.percentile(val_errors_benign, 95))

    test_errors = reconstruction_error(final_model, X_test)
    test_auc = float(roc_auc_score(y_test, test_errors))
    test_f1 = float(f1_score(y_test, (test_errors > thr_pctl).astype(int), zero_division=0))
    print(f"\nFINAL (clean, single-shot) TEST: AUC={test_auc:.4f} F1(pctl95)={test_f1:.4f}")

    # ---- Save everything ----
    final_model.encoder.save(MODEL_DIR / "vae_encoder_selected.keras")
    final_model.decoder.save(MODEL_DIR / "vae_decoder_selected.keras")

    summary = {
        "chosen_latent_dim": CHOSEN_LATENT,
        "variant_comparison_val_only": variant_df.reset_index().to_dict(orient="records"),
        "selection_reasoning": reasoning,
        "selected_variant": selected_variant,
        "threshold_pctl95_from_val": thr_pctl,
        "final_test_auc": test_auc,
        "final_test_f1_pctl95": test_f1,
        "old_leaked_test_auc": 0.9372,
        "old_leaked_test_f1": 0.8413,
    }
    with open(OUT_DIR / "clean_selection_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved -> {OUT_DIR / 'clean_selection_results.json'}")


if __name__ == "__main__":
    main()
