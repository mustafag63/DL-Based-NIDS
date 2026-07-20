"""Compare three anomaly-scoring functions on top of the final VAE config
(latent=10, beta=0.25, confirmed in 08_beta_multiseed/) - architecture is
NOT retrained/changed, only the inference-time score.

  a) baseline    - plain reconstruction MSE (what every other phase3_vae/
                   experiment uses)
  b) elbo_score  - recon_loss + beta*KL, per sample (the training loss
                   itself, evaluated per-example at inference time)
  c) recon_prob  - reconstruction probability (An & Cho, 2015): sample z
                   from q(z|x) L=10 times (Monte Carlo), average the
                   Gaussian log-likelihood of x under each decoded
                   reconstruction, negate (so higher = more anomalous,
                   same direction as the other two scores)

Own 5 models (seeds 0-4, latent=10, beta=0.25) are trained here - this does
NOT load the saved 04_phase3_models/vae_*_final.keras files, to stay
consistent with 08_beta_multiseed/'s multi-seed protocol (a single model
would not let us report a mean+/-std per score function).

Phase A: all 3 scores computed on val_indices.csv only, for all 5 models -
this is comparing score *functions*, not selecting a model, so no leakage
question there; test set is not loaded until Phase B.
Phase B: only the winning score function is evaluated on the test set,
once per model (5 evaluations total, no selection made from test numbers).

recon_prob's decoder has no variance head (linear output, deterministic
reconstruction) - the Gaussian log-likelihood below assumes unit variance
(sigma^2=1), matching the implicit assumption behind the raw-MSE
reconstruction loss the model was trained with. This is a simplifying
approximation, called out in the README.

Writes only into 10_probabilistic_scoring/.
"""
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

LATENT_DIM = 10
BETA = 0.25
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12
SEEDS = list(range(5))
MC_SAMPLES = 10  # L for reconstruction probability


def build_and_train(seed, X_train, X_val_benign):
    tf.keras.utils.set_random_seed(seed)
    model = VAE2(INPUT_DIM, LATENT_DIM, beta_init=BETA, dropout_rate=DROPOUT_RATE)
    model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
    early_stop = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE, restore_best_weights=True)
    t0 = time.time()
    history = model.fit(
        X_train, X_train, validation_data=(X_val_benign, X_val_benign),
        epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True, callbacks=[early_stop], verbose=0,
    )
    return model, history, time.time() - t0


def score_baseline(model, X):
    """Plain reconstruction MSE, single stochastic forward pass (matches
    every other phase3_vae/ experiment's reconstruction_error())."""
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def score_elbo(model, X, beta):
    """Per-sample training loss (recon_loss_sum + beta*KL), single
    stochastic forward pass - same sample used for score_baseline's
    reconstruction, just summed instead of averaged and with the KL term
    added, so the two are directly comparable apples-to-apples."""
    recon, z_mean, z_log_var = model(X, training=False)
    recon_np, z_mean_np, z_log_var_np = recon.numpy(), z_mean.numpy(), z_log_var.numpy()
    recon_loss = np.sum(np.square(X - recon_np), axis=1)
    kl = -0.5 * np.sum(1 + z_log_var_np - np.square(z_mean_np) - np.exp(z_log_var_np), axis=1)
    return recon_loss + beta * kl


def score_recon_prob(model, X, n_samples=MC_SAMPLES):
    """An & Cho (2015) reconstruction probability, Monte Carlo estimate.
    Decoder has no variance head (linear, deterministic output) - assumes
    unit-variance isotropic Gaussian p(x|z), matching the implicit
    assumption of the raw-MSE training loss. Returns NEGATIVE mean
    log-likelihood (higher = more anomalous, same direction as the other
    two scores)."""
    z_mean, z_log_var = model.encoder(X, training=False)
    z_mean_np, z_log_var_np = z_mean.numpy(), z_log_var.numpy()
    std_np = np.exp(0.5 * z_log_var_np)
    D = X.shape[1]
    log_probs = np.zeros((X.shape[0], n_samples))
    for l in range(n_samples):
        eps = np.random.normal(size=z_mean_np.shape).astype("float32")
        z_l = z_mean_np + std_np * eps
        recon_l = model.decoder(z_l, training=False).numpy()
        sq_err = np.sum(np.square(X - recon_l), axis=1)
        log_probs[:, l] = -0.5 * sq_err - 0.5 * D * np.log(2 * np.pi)
    mean_log_prob = log_probs.mean(axis=1)
    return -mean_log_prob


def main():
    print(f"TensorFlow {tf.__version__}, GPU: {tf.config.list_physical_devices('GPU')}")
    np.random.seed(0)  # for the MC sampling in score_recon_prob (separate from model init seeds)

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
          f"(test not loaded - Phase A is val-only)\n")

    # ---- Train 5 models (seeds 0-4), same protocol as 08_beta_multiseed ----
    models = {}
    rows = []
    for seed in SEEDS:
        model, history, train_time = build_and_train(seed, X_train, X_val_benign)
        models[seed] = model

        t_base0 = time.time()
        s_base = score_baseline(model, X_val_all)
        t_base = time.time() - t_base0

        t_elbo0 = time.time()
        s_elbo = score_elbo(model, X_val_all, BETA)
        t_elbo = time.time() - t_elbo0

        t_rp0 = time.time()
        s_rp = score_recon_prob(model, X_val_all, MC_SAMPLES)
        t_rp = time.time() - t_rp0

        auc_base = roc_auc_score(y_val, s_base)
        auc_elbo = roc_auc_score(y_val, s_elbo)
        auc_rp = roc_auc_score(y_val, s_rp)

        rows.append({
            "seed": seed,
            "val_auc_baseline": auc_base, "val_auc_elbo": auc_elbo, "val_auc_recon_prob": auc_rp,
            "score_time_sec_baseline": round(t_base, 4), "score_time_sec_elbo": round(t_elbo, 4),
            "score_time_sec_recon_prob": round(t_rp, 4),
            "epochs_run": len(history.history["loss"]),
        })
        print(f"seed={seed}: val_AUC baseline={auc_base:.4f} elbo={auc_elbo:.4f} recon_prob={auc_rp:.4f} "
              f"(score time sec: {t_base:.3f} / {t_elbo:.3f} / {t_rp:.3f}, MC L={MC_SAMPLES}) epochs={len(history.history['loss'])}")

    per_seed_df = pd.DataFrame(rows)
    per_seed_df.to_csv(OUT_DIR / "val_score_comparison_per_seed.csv", index=False)

    score_names = ["baseline", "elbo", "recon_prob"]
    summary_rows = []
    for name in score_names:
        col = f"val_auc_{name}"
        s = per_seed_df[col]
        summary_rows.append({
            "score": name, "n_seeds": len(s), "val_auc_mean": s.mean(), "val_auc_std": s.std(),
            "mean_score_time_sec": per_seed_df[f"score_time_sec_{name}"].mean(),
        })
    summary_df = pd.DataFrame(summary_rows).set_index("score")
    summary_df.to_csv(OUT_DIR / "val_score_comparison_summary.csv")
    print("\n", summary_df, "\n")

    ranked = summary_df.sort_values("val_auc_mean", ascending=False)
    winner = ranked.index[0]
    runner_up = ranked.index[1]
    winner_vals = per_seed_df[f"val_auc_{winner}"].to_numpy()
    runner_vals = per_seed_df[f"val_auc_{runner_up}"].to_numpy()
    t_stat, p_value = ttest_ind(winner_vals, runner_vals, equal_var=False)
    overlap = (ranked.loc[winner, "val_auc_mean"] - ranked.loc[winner, "val_auc_std"]) <= \
              (ranked.loc[runner_up, "val_auc_mean"] + ranked.loc[runner_up, "val_auc_std"])

    print(f"Winner: '{winner}' ({ranked.loc[winner, 'val_auc_mean']:.4f} +/- {ranked.loc[winner, 'val_auc_std']:.4f})")
    print(f"Runner-up: '{runner_up}' ({ranked.loc[runner_up, 'val_auc_mean']:.4f} +/- {ranked.loc[runner_up, 'val_auc_std']:.4f})")
    print(f"Overlap: {overlap}, Welch t-test p-value: {p_value:.4f}")

    # ---- Phase B: ONE-TIME test evaluation of the WINNING score function only ----
    test_idx = pd.read_csv(DENSE_SPLIT_DIR / "test_indices.csv")["row_index"].values
    test_df = features_all.iloc[test_idx].reset_index(drop=True)
    X_test = test_df[FEATURE_COLS].values.astype("float32")
    y_test = test_df["is_attack"].values

    score_fn = {
        "baseline": lambda m, X: score_baseline(m, X),
        "elbo": lambda m, X: score_elbo(m, X, BETA),
        "recon_prob": lambda m, X: score_recon_prob(m, X, MC_SAMPLES),
    }[winner]

    test_rows = []
    for seed in SEEDS:
        model = models[seed]
        val_scores_benign = score_fn(model, X_val_benign)
        thr_pctl = float(np.percentile(val_scores_benign, 95))

        test_scores = score_fn(model, X_test)
        test_auc = float(roc_auc_score(y_test, test_scores))
        test_f1 = float(f1_score(y_test, (test_scores > thr_pctl).astype(int), zero_division=0))
        test_rows.append({"seed": seed, "test_auc": test_auc, "test_f1_pctl95": test_f1})
        print(f"[Phase B] {winner} seed={seed}: test_AUC={test_auc:.4f} test_F1={test_f1:.4f}")

    winner_test_df = pd.DataFrame(test_rows)
    winner_test_df.to_csv(OUT_DIR / "winner_test_per_seed.csv", index=False)
    print(f"\n[Phase B] {winner}: test_AUC = {winner_test_df['test_auc'].mean():.4f} "
          f"+/- {winner_test_df['test_auc'].std():.4f} (n={len(SEEDS)})")
    print(f"[Phase B] {winner}: test_F1  = {winner_test_df['test_f1_pctl95'].mean():.4f} "
          f"+/- {winner_test_df['test_f1_pctl95'].std():.4f} (n={len(SEEDS)})")

    print(f"\nReference (07_seed_variance, baseline score, n=10): test_AUC = 0.9197 +/- 0.0149")
    print(f"Reference (08_beta_multiseed, baseline score, n=5): test_AUC = 0.9259 +/- 0.0095")

    print(f"\nSaved: {OUT_DIR / 'val_score_comparison_per_seed.csv'}, "
          f"{OUT_DIR / 'val_score_comparison_summary.csv'}, {OUT_DIR / 'winner_test_per_seed.csv'}")


if __name__ == "__main__":
    main()
