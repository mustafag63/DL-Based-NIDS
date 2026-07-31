"""Multi-seed re-evaluation of the beta-variant comparison (phase3_vae, section 9).

06_beta_selection_audit/rerun_beta_selection.py fixed the test-set leakage in
the original beta selection (test_auc -> val_auc as the selection metric,
test touched once instead of once-per-variant) but still trained each of the
4 variants (1.0/0.5/0.25/KL-annealing) with a single seed. 07_seed_variance/
then showed that for a *fixed* config, active-latent-dim count varies wildly
across seeds (1/10-9/10) with no relationship to test AUC - so the original
9.3 selection rule ("prefer more active dims, within an AUC tolerance") was
built on a signal that doesn't actually track quality.

This script re-does the beta comparison properly:
  - Phase A: each of the 4 variants trained with 5 seeds (0-4), val-only
    (X_test/y_test are not even loaded until Phase B). Selection uses ONLY
    val_auc mean/std across the 5 seeds - active-dim count is recorded for
    reference but plays no role in picking a winner.
  - Phase B: the 5 already-trained models for the winning variant (no
    retraining) are evaluated on the test set exactly once each, to report a
    test AUC/F1 mean +/- std comparable to 07_seed_variance/'s format.

Does not touch 04_phase3_models/, latest_run/, 06_beta_selection_audit/, or
07_seed_variance/ - everything is written under 08_beta_multiseed/ only.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from scipy.stats import ttest_ind
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

CHOSEN_LATENT = 10
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
ACTIVE_STD_THRESHOLD = 0.15
ANNEAL_EPOCHS = 40
SEEDS = list(range(5))  # 0-4, time-boxed per today's scope

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
    val_df = features_all.iloc[val_idx].reset_index(drop=True)

    val_benign_mask = val_df["is_attack"] == 0
    X_val_benign = val_df.loc[val_benign_mask, FEATURE_COLS].values.astype("float32")
    X_val_all = val_df[FEATURE_COLS].values.astype("float32")
    y_val = val_df["is_attack"].values

    print(f"train: {len(train_df)}  val: {len(val_df)}  "
          f"(test not loaded yet - Phase A is val-only)\n")

    # ---- Phase A: 4 variants x 5 seeds, VAL ONLY ----
    rows = []
    models = {}  # (variant, seed) -> model
    for name, beta_target, anneal_epochs in VARIANTS:
        for seed in SEEDS:
            model, history, train_time = build_and_train_v2(
                CHOSEN_LATENT, beta_target, seed=seed, anneal_epochs=anneal_epochs,
                X_train=X_train, X_val_benign=X_val_benign,
            )
            n_active_train, _ = count_active_dims(model, X_train)

            val_errors = reconstruction_error(model, X_val_all)
            val_auc = roc_auc_score(y_val, val_errors)

            rows.append({
                "variant": name, "beta_target": beta_target, "seed": seed,
                "val_auc": val_auc, "n_active_dims_train": n_active_train,
                "epochs_run": len(history.history["loss"]),
                "train_time_sec": round(train_time, 1),
            })
            models[(name, seed)] = model
            print(f"{name} seed={seed}: val_AUC={val_auc:.4f} "
                  f"active_dims={n_active_train}/{CHOSEN_LATENT} epochs={len(history.history['loss'])}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(OUT_DIR / "results_per_seed.csv", index=False)

    # ---- Summary per variant (val_auc mean/std/median across 5 seeds) ----
    summary_rows = []
    for name, beta_target, anneal_epochs in VARIANTS:
        sub = per_seed_df[per_seed_df["variant"] == name]
        summary_rows.append({
            "variant": name,
            "n_seeds": len(sub),
            "val_auc_mean": sub["val_auc"].mean(),
            "val_auc_std": sub["val_auc"].std(),
            "val_auc_median": sub["val_auc"].median(),
            "active_dims_mean": sub["n_active_dims_train"].mean(),
            "active_dims_std": sub["n_active_dims_train"].std(),
        })
    summary_df = pd.DataFrame(summary_rows).set_index("variant")
    summary_df.to_csv(OUT_DIR / "results_summary.csv")
    print("\n", summary_df, "\n")

    # ---- Step: selection on val_auc mean ONLY (active dims not a criterion) ----
    ranked = summary_df.sort_values("val_auc_mean", ascending=False)
    winner_name = ranked.index[0]
    winner_mean = ranked.loc[winner_name, "val_auc_mean"]
    winner_std = ranked.loc[winner_name, "val_auc_std"]

    reasoning = [
        "Selection criterion: val_auc mean across 5 seeds ONLY "
        "(active-dim count dropped per 07_seed_variance/ finding - no relationship to AUC).",
        f"Ranking (val_auc mean +/- std, n=5 seeds each):",
    ]
    for name in ranked.index:
        m, s = ranked.loc[name, "val_auc_mean"], ranked.loc[name, "val_auc_std"]
        reasoning.append(f"  {name}: {m:.4f} +/- {s:.4f}")

    runner_up_name = ranked.index[1]
    runner_mean = ranked.loc[runner_up_name, "val_auc_mean"]
    runner_std = ranked.loc[runner_up_name, "val_auc_std"]

    winner_vals = per_seed_df.loc[per_seed_df["variant"] == winner_name, "val_auc"].to_numpy()
    runner_vals = per_seed_df.loc[per_seed_df["variant"] == runner_up_name, "val_auc"].to_numpy()
    t_stat, p_value = ttest_ind(winner_vals, runner_vals, equal_var=False)

    overlap = (winner_mean - winner_std) <= (runner_mean + runner_std)
    reasoning.append(f"\nWinner: '{winner_name}' ({winner_mean:.4f} +/- {winner_std:.4f})")
    reasoning.append(f"Runner-up: '{runner_up_name}' ({runner_mean:.4f} +/- {runner_std:.4f})")
    reasoning.append(f"Mean-+-std bands overlap: {overlap}. Welch t-test p-value: {p_value:.4f}")
    if overlap or p_value > 0.05:
        reasoning.append(
            f"=> '{winner_name}' and '{runner_up_name}' are NOT statistically distinguishable "
            f"at n=5 seeds (overlapping std bands / p={p_value:.4f} > 0.05)."
        )
    else:
        reasoning.append(f"=> '{winner_name}' is a statistically clear winner over '{runner_up_name}'.")

    print("\n".join(reasoning))

    # ---- Phase B: ONE-TIME test evaluation of the winning variant's 5 already-trained seeds ----
    test_idx = pd.read_csv(DENSE_SPLIT_DIR / "test_indices.csv")["row_index"].values
    test_df = features_all.iloc[test_idx].reset_index(drop=True)
    X_test = test_df[FEATURE_COLS].values.astype("float32")
    y_test = test_df["is_attack"].values

    test_rows = []
    for seed in SEEDS:
        model = models[(winner_name, seed)]
        val_errors_benign = reconstruction_error(model, X_val_benign)
        thr_pctl = float(np.percentile(val_errors_benign, 95))

        test_errors = reconstruction_error(model, X_test)
        test_auc = float(roc_auc_score(y_test, test_errors))
        test_f1 = float(f1_score(y_test, (test_errors > thr_pctl).astype(int), zero_division=0))
        test_rows.append({"seed": seed, "test_auc": test_auc, "test_f1_pctl95": test_f1})
        print(f"[Phase B] {winner_name} seed={seed}: test_AUC={test_auc:.4f} test_F1={test_f1:.4f}")

    winner_test_df = pd.DataFrame(test_rows)
    winner_test_df.to_csv(OUT_DIR / "winner_test_per_seed.csv", index=False)

    winner_test_summary = {
        "winner_variant": winner_name,
        "n_seeds": len(SEEDS),
        "test_auc_mean": winner_test_df["test_auc"].mean(),
        "test_auc_std": winner_test_df["test_auc"].std(),
        "test_f1_mean": winner_test_df["test_f1_pctl95"].mean(),
        "test_f1_std": winner_test_df["test_f1_pctl95"].std(),
    }
    print(f"\n[Phase B] {winner_name}: test_AUC = {winner_test_summary['test_auc_mean']:.4f} "
          f"+/- {winner_test_summary['test_auc_std']:.4f} (n={len(SEEDS)})")
    print(f"[Phase B] {winner_name}: test_F1  = {winner_test_summary['test_f1_mean']:.4f} "
          f"+/- {winner_test_summary['test_f1_std']:.4f} (n={len(SEEDS)})")

    # Reference: 07_seed_variance/'s existing 10-seed beta=0.25 result
    existing_10seed_ref = {"variant": "beta=0.25", "n_seeds": 10, "test_auc_mean": 0.9197, "test_auc_std": 0.0149}
    print(f"\nReference (07_seed_variance/, beta=0.25, n=10): "
          f"test_AUC = {existing_10seed_ref['test_auc_mean']:.4f} +/- {existing_10seed_ref['test_auc_std']:.4f}")

    summary = {
        "seeds_used": SEEDS,
        "phase_a_variant_summary": summary_df.reset_index().to_dict(orient="records"),
        "selection_reasoning": reasoning,
        "winner_variant": winner_name,
        "runner_up_variant": runner_up_name,
        "welch_ttest_p_value": float(p_value),
        "distinguishable_from_runner_up": bool(not (overlap or p_value > 0.05)),
        "phase_b_winner_test_summary": winner_test_summary,
        "reference_07_seed_variance_beta025_10seed": existing_10seed_ref,
    }
    with open(OUT_DIR / "multiseed_selection_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved -> {OUT_DIR / 'multiseed_selection_results.json'}")


if __name__ == "__main__":
    main()
