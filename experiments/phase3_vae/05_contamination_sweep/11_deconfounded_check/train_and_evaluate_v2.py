"""
Deconfounded verification arm (audit K1+K2), step 2: train + evaluate.
Data comes from prepare_contamination_data_v2.py (01_data/ here).

- Trains contamination 0% and 4%, 20 seeds each, with the EXACT architecture
  and hyperparameters of the original sweep (train_contamination_sweep*.py:
  latent_dim=10, beta=0.25, dropout=0.1, batch=64, epochs<=200, patience=12,
  Adam clipnorm=1.0, early stop on val_loss over the window_10 val-benign
  split). Only difference: the z_log_var clip uses the registered ClipLogVar
  layer (model_layers.py) instead of a Lambda, so saved models reload cleanly
  -- numerically identical op.
- Scoring is DETERMINISTIC z_mean throughout (audit O2): threshold_95 is the
  95th percentile of the deterministic error on val_benign_v2.csv, and test
  errors are deterministic too. No stochastic scores anywhere in this arm.
- Also evaluates the ORIGINAL v1 contam_0pct models (04_models/contam_0pct,
  20 seeds) deterministically on the v1 test set (01_data/test_set.csv,
  thresholds recomputed deterministically on v1 val_benign.csv) -- the
  apples-to-apples "old (confounded) deterministic" baseline for the
  comparison. As a confound-magnitude diagnostic, the v1 models are also
  scored on the v2 test set's window_02-08 benign rows (flows no v1 model
  ever saw). The v1 models' FPR on v2's window_10 test rows is NOT a valid
  number (v1's flat random split put most of those flows in v1's own
  train/val), so it is not reported.

Outputs (this directory):
  04_models/contam_{0,4}pct_v2/seed_*/{encoder,decoder}.keras + threshold.json
  v2_0pct_results.csv/.md, v2_4pct_results.csv/.md
  v1_0pct_deterministic_results.csv  (baseline arm, for the findings doc)
  comparison_summary.csv             (all arms, one row per arm x metric)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, fbeta_score, roc_auc_score

import keras.src.utils.python_utils as _keras_python_utils  # noqa: E402
_keras_python_utils.tf = tf

HERE = Path(__file__).parent
SWEEP_DIR = HERE.parent
PHASE3_VAE_DIR = SWEEP_DIR.parent
sys.path.insert(0, str(PHASE3_VAE_DIR))
from model_layers import ClipLogVar  # noqa: E402

DATA_DIR = HERE / "01_data"
MODEL_DIR = HERE / "04_models"
V1_DATA_DIR = SWEEP_DIR / "01_data"
V1_MODEL_DIR = SWEEP_DIR / "04_models" / "contam_0pct"

manifest = json.loads((DATA_DIR / "manifest_v2.json").read_text())
FEATURE_COLS = manifest["feature_cols"]
INPUT_DIM = len(FEATURE_COLS)
assert INPUT_DIM == 18, INPUT_DIM

CONTAM_LEVELS_PCT = [0, 4]
SEEDS = list(range(20))

LATENT_DIM = 10
BETA = 0.25
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12


class VAE(tf.keras.Model):
    """train_contamination_sweep*.py's VAE, with ClipLogVar replacing the
    Lambda clip (same op; reload-safe)."""
    def __init__(self, input_dim, latent_dim, beta=1.0, dropout_rate=0.1, **kwargs):
        super().__init__(**kwargs)
        self.latent_dim = latent_dim
        self.beta = beta

        enc_in = tf.keras.Input(shape=(input_dim,))
        x = tf.keras.layers.Dense(16, activation="relu")(enc_in)
        x = tf.keras.layers.Dropout(dropout_rate)(x)
        x = tf.keras.layers.Dense(8, activation="relu")(x)
        z_mean = tf.keras.layers.Dense(latent_dim, name="z_mean")(x)
        z_log_var = ClipLogVar()(tf.keras.layers.Dense(latent_dim, name="z_log_var")(x))
        self.encoder = tf.keras.Model(enc_in, [z_mean, z_log_var], name="encoder")

        dec_in = tf.keras.Input(shape=(latent_dim,))
        y = tf.keras.layers.Dense(8, activation="relu")(dec_in)
        y = tf.keras.layers.Dense(16, activation="relu")(y)
        dec_out = tf.keras.layers.Dense(input_dim, activation="linear")(y)
        self.decoder = tf.keras.Model(dec_in, dec_out, name="decoder")

        self.total_loss_tracker = tf.keras.metrics.Mean(name="loss")
        self.recon_loss_tracker = tf.keras.metrics.Mean(name="recon_loss")
        self.kl_loss_tracker = tf.keras.metrics.Mean(name="kl_loss")

    @property
    def metrics(self):
        return [self.total_loss_tracker, self.recon_loss_tracker, self.kl_loss_tracker]

    def call(self, inputs, training=False):
        z_mean, z_log_var = self.encoder(inputs, training=training)
        eps = tf.random.normal(shape=tf.shape(z_mean))
        z = z_mean + tf.exp(0.5 * z_log_var) * eps
        recon = self.decoder(z, training=training)
        return recon, z_mean, z_log_var

    def _compute_losses(self, x, y):
        recon, z_mean, z_log_var = self(x, training=True)
        recon_loss = tf.reduce_mean(tf.reduce_sum(tf.square(y - recon), axis=1))
        kl_loss = -0.5 * tf.reduce_mean(
            tf.reduce_sum(1 + z_log_var - tf.square(z_mean) - tf.exp(z_log_var), axis=1)
        )
        total_loss = recon_loss + self.beta * kl_loss
        return total_loss, recon_loss, kl_loss

    def train_step(self, data):
        x, y = data
        with tf.GradientTape() as tape:
            total_loss, recon_loss, kl_loss = self._compute_losses(x, y)
        grads = tape.gradient(total_loss, self.trainable_weights)
        self.optimizer.apply_gradients(zip(grads, self.trainable_weights))
        self.total_loss_tracker.update_state(total_loss)
        self.recon_loss_tracker.update_state(recon_loss)
        self.kl_loss_tracker.update_state(kl_loss)
        return {m.name: m.result() for m in self.metrics}

    def test_step(self, data):
        x, y = data
        total_loss, recon_loss, kl_loss = self._compute_losses(x, y)
        self.total_loss_tracker.update_state(total_loss)
        self.recon_loss_tracker.update_state(recon_loss)
        self.kl_loss_tracker.update_state(kl_loss)
        return {m.name: m.result() for m in self.metrics}


def zmean_error(encoder, decoder, X):
    z_mean, _ = encoder(X, training=False)
    recon = decoder(z_mean, training=False).numpy()
    return np.mean(np.square(X - recon), axis=1)


def metrics_row(y, errors, thr95, source=None):
    pred = (errors > thr95).astype(int)
    benign, attack = y == 0, y == 1
    row = {
        "threshold_95": thr95,
        "pr_auc": average_precision_score(y, errors),
        "roc_auc": roc_auc_score(y, errors),
        "f1": fbeta_score(y, pred, beta=1.0, zero_division=0),
        "benign_fpr": float(pred[benign].mean()),
        "attack_recall": float(pred[attack].mean()),
    }
    if source is not None:
        for s, tag in (("window_10", "fpr_w10"), ("window_02_08", "fpr_0208")):
            m = benign & (source == s)
            row[tag] = float(pred[m].mean()) if m.any() else float("nan")
    return row


def train_v2_level(level_pct, X_train, X_val):
    level_dir = MODEL_DIR / f"contam_{level_pct}pct_v2"
    rows = []
    for seed in SEEDS:
        seed_dir = level_dir / f"seed_{seed}"
        if (seed_dir / "threshold.json").exists():
            print(f"  seed {seed}: exists, skipping training")
            continue
        seed_dir.mkdir(parents=True, exist_ok=True)
        tf.keras.utils.set_random_seed(seed)
        model = VAE(INPUT_DIM, LATENT_DIM, beta=BETA, dropout_rate=DROPOUT_RATE)
        model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
        early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=PATIENCE,
                                                 restore_best_weights=True)
        t0 = time.time()
        history = model.fit(X_train, X_train, validation_data=(X_val, X_val),
                            epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True,
                            callbacks=[early], verbose=0)
        model.encoder.save(seed_dir / "encoder.keras")
        model.decoder.save(seed_dir / "decoder.keras")
        thr95 = float(np.percentile(zmean_error(model.encoder, model.decoder, X_val), 95))
        info = {"contamination_pct": level_pct, "seed": seed, "scoring": "deterministic_zmean",
                "epochs_run": len(history.history["loss"]),
                "train_time_sec": time.time() - t0,
                "final_val_loss": float(history.history["val_loss"][-1]),
                "threshold_95": thr95}
        (seed_dir / "threshold.json").write_text(json.dumps(info, indent=2))
        rows.append(info)
        print(f"  seed {seed}: epochs={info['epochs_run']:3d} "
              f"time={info['train_time_sec']:5.1f}s thr95={thr95:.4f}")
    return rows


def eval_v2_level(level_pct, X_test, y_test, source):
    level_dir = MODEL_DIR / f"contam_{level_pct}pct_v2"
    rows = []
    for seed in SEEDS:
        seed_dir = level_dir / f"seed_{seed}"
        encoder = tf.keras.models.load_model(seed_dir / "encoder.keras")
        decoder = tf.keras.models.load_model(seed_dir / "decoder.keras")
        thr95 = json.loads((seed_dir / "threshold.json").read_text())["threshold_95"]
        errors = zmean_error(encoder, decoder, X_test)
        rows.append({"arm": f"v2_{level_pct}pct", "seed": seed,
                     **metrics_row(y_test, errors, thr95, source)})
        print(f"  v2_{level_pct}pct seed {seed}: PR-AUC={rows[-1]['pr_auc']:.4f} "
              f"recall={rows[-1]['attack_recall']:.4f} FPR={rows[-1]['benign_fpr']:.4f}")
    return rows


def eval_v1_baseline(X_v2_0208_benign):
    """v1 contam_0pct models, deterministic, on the v1 test set; plus their
    FPR on v2's never-seen window_02-08 benign rows (confound diagnostic)."""
    val = pd.read_csv(V1_DATA_DIR / "val_benign.csv")
    X_val = val[FEATURE_COLS].values.astype("float32")
    test = pd.read_csv(V1_DATA_DIR / "test_set.csv")
    X_test = test[FEATURE_COLS].values.astype("float32")
    y_test = test["is_attack"].values
    rows = []
    for seed in SEEDS:
        seed_dir = V1_MODEL_DIR / f"seed_{seed}"
        encoder = tf.keras.models.load_model(seed_dir / "encoder.keras", safe_mode=False)
        decoder = tf.keras.models.load_model(seed_dir / "decoder.keras", safe_mode=False)
        thr95 = float(np.percentile(zmean_error(encoder, decoder, X_val), 95))
        errors = zmean_error(encoder, decoder, X_test)
        row = {"arm": "v1_0pct_det", "seed": seed, **metrics_row(y_test, errors, thr95)}
        err_0208 = zmean_error(encoder, decoder, X_v2_0208_benign)
        row["fpr_0208_neverseen"] = float((err_0208 > thr95).mean())
        rows.append(row)
        print(f"  v1_0pct_det seed {seed}: PR-AUC={row['pr_auc']:.4f} "
              f"recall={row['attack_recall']:.4f} FPR={row['benign_fpr']:.4f} "
              f"FPR(0208 never-seen)={row['fpr_0208_neverseen']:.4f}")
    return rows


def write_level_report(level_pct, per_seed):
    df = pd.DataFrame(per_seed)
    csv_path = HERE / f"v2_{level_pct}pct_results.csv"
    df.to_csv(csv_path, index=False)
    metric_cols = [c for c in df.columns if c not in ("arm", "seed")]
    s = df[metric_cols].agg(["mean", "std"])
    md_path = HERE / f"v2_{level_pct}pct_results.md"
    lines = [
        f"# V2 (deconfounded) contamination {level_pct}% — deterministic z_mean, 20 seeds",
        "",
        "Pipeline: `prepare_contamination_data_v2.py` (K2: signature-grouped window_10 "
        "split; K1: test benign = 70% window_10 + 30% window_02-08, equal per-window "
        "shares). Architecture/hyperparameters identical to the original sweep "
        "(latent=10, beta=0.25). threshold_95 = 95th pctl of deterministic error on "
        "val_benign_v2.csv, per seed.",
        "",
        "| metric | mean | std |",
        "|---|---|---|",
    ] + [f"| {m} | {s.loc['mean', m]:.4f} | {s.loc['std', m]:.4f} |" for m in metric_cols]
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {csv_path} and {md_path}")
    return df


def main():
    val = pd.read_csv(DATA_DIR / "val_benign_v2.csv")
    X_val = val[FEATURE_COLS].values.astype("float32")
    test = pd.read_csv(DATA_DIR / "test_set_v2.csv")
    X_test = test[FEATURE_COLS].values.astype("float32")
    y_test = test["is_attack"].values
    source = test["benign_source"].fillna("").values
    X_0208 = test.loc[(test["is_attack"] == 0) & (test["benign_source"] == "window_02_08"),
                      FEATURE_COLS].values.astype("float32")
    print(f"V2 val: {len(val)} benign; V2 test: {len(test)} flows "
          f"({int((y_test == 0).sum())} benign, {int(y_test.sum())} attack); "
          f"0208-benign diagnostic rows: {len(X_0208)}")

    all_rows = []
    for level_pct in CONTAM_LEVELS_PCT:
        train_df = pd.read_csv(DATA_DIR / f"train_contam_{level_pct}pct_v2.csv")
        X_train = train_df[FEATURE_COLS].values.astype("float32")
        print(f"\n=== TRAIN v2 contam {level_pct}% (n={len(train_df)}, "
              f"{int(train_df['is_attack'].sum())} attack rows in train) ===")
        train_v2_level(level_pct, X_train, X_val)
        print(f"=== EVAL v2 contam {level_pct}% ===")
        per_seed = eval_v2_level(level_pct, X_test, y_test, source)
        all_rows += per_seed
        write_level_report(level_pct, per_seed)

    print("\n=== EVAL v1 baseline (deterministic, v1 test set) ===")
    v1_rows = eval_v1_baseline(X_0208)
    pd.DataFrame(v1_rows).to_csv(HERE / "v1_0pct_deterministic_results.csv", index=False)
    all_rows += v1_rows

    combined = pd.DataFrame(all_rows)
    metric_cols = [c for c in combined.columns if c not in ("arm", "seed")]
    summary = combined.groupby("arm")[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary.to_csv(HERE / "comparison_summary.csv")
    print(f"\nWrote {HERE / 'comparison_summary.csv'}")
    print(summary[[c for c in summary.columns if c.endswith("_mean")]].to_string())


if __name__ == "__main__":
    main()
