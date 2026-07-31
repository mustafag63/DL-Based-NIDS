"""
Phase 3 (VAE) - contamination sweep EXTENSION: train new resampled-window
contamination levels (from prepare_contamination_data_extended.py).
Architecture/hyperparameters copied verbatim from
train_contamination_sweep.py (same VAE class, same latent_dim=10, beta=0.25) -
only CONTAM_LEVELS_PCT/SEEDS and the train-file source differ. Does not touch
the existing 0/1/2/4/8/12% models under 04_models/.

SEED-EXTENSION RUN (seeds 5-19): the three resampled points
(15/20/22pct-clean) were originally trained with SEEDS=[0,1,2,3,4] only
(04_models/contam_{15,20,22}pct/seed_{0-4}/ already exist and are NOT
retrained here - build_and_train() is seeded per-call via
tf.keras.utils.set_random_seed(seed), so re-running seed 0-4 would
reproduce the exact same weights anyway, but we skip them regardless to
save time). CONTAM_LEVELS_PCT/SEEDS below are set to add seed_5..seed_19
(15 new seeds) on top of the existing 5, bringing each of these three
levels to 20 seeds total - to shrink the resampled points' seed-to-seed std
(0.069/0.029/0.001 at 5 seeds) without touching the original 6 controlled-
injection levels or the existing 5-seed results for any level. The
log-merge logic below keys on (contamination_pct, seed) pairs, not just
contamination_pct, so re-running this file with CONTAM_LEVELS_PCT including
an already-trained level only ADDS the new seeds' log entries instead of
dropping the old ones.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = Path(__file__).parent
DATA_DIR = HERE / "01_data"
TRAIN_DIR = HERE / "02_contaminated_train_sets"
MODEL_DIR = HERE / "04_models"
MODEL_DIR.mkdir(exist_ok=True)

manifest = json.loads((DATA_DIR / "manifest.json").read_text())
FEATURE_COLS = manifest["feature_cols"]
INPUT_DIM = len(FEATURE_COLS)
assert INPUT_DIM == 18, INPUT_DIM

CONTAM_LEVELS_PCT = [15, 20, 22]
SEEDS = list(range(5, 20))

LATENT_DIM = 10
BETA = 0.25
DROPOUT_RATE = 0.1
BATCH_SIZE = 64
EPOCHS = 200
PATIENCE = 12

THRESHOLD_PCTLS = [95, 99]


class VAE(tf.keras.Model):
    def __init__(self, input_dim, latent_dim, beta=1.0, dropout_rate=0.1, **kwargs):
        super().__init__(**kwargs)
        self.latent_dim = latent_dim
        self.beta = beta

        enc_in = tf.keras.Input(shape=(input_dim,))
        x = tf.keras.layers.Dense(16, activation="relu")(enc_in)
        x = tf.keras.layers.Dropout(dropout_rate)(x)
        x = tf.keras.layers.Dense(8, activation="relu")(x)
        z_mean = tf.keras.layers.Dense(latent_dim, name="z_mean")(x)
        z_log_var_raw = tf.keras.layers.Dense(latent_dim, name="z_log_var")(x)
        z_log_var = tf.keras.layers.Lambda(
            lambda t: tf.clip_by_value(t, -10.0, 10.0), output_shape=lambda s: s
        )(z_log_var_raw)
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


def reconstruction_error(model, X):
    recon, _, _ = model(X, training=False)
    return np.mean(np.square(X - recon.numpy()), axis=1)


def build_and_train(X_train, X_val_benign, seed):
    tf.keras.utils.set_random_seed(seed)
    model = VAE(INPUT_DIM, LATENT_DIM, beta=BETA, dropout_rate=DROPOUT_RATE)
    model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
    early_stop = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=PATIENCE, restore_best_weights=True
    )
    t0 = time.time()
    history = model.fit(
        X_train, X_train,
        validation_data=(X_val_benign, X_val_benign),
        epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True,
        callbacks=[early_stop], verbose=0,
    )
    return model, history, time.time() - t0


def main() -> None:
    val_benign_df = pd.read_csv(DATA_DIR / "val_benign.csv")
    assert (val_benign_df["is_attack"] == 0).all()
    X_val_benign = val_benign_df[FEATURE_COLS].values.astype("float32")
    print(f"Threshold/early-stop validation set: {len(X_val_benign)} benign flows (same held-out "
          f"split as the original sweep)")

    run_log = []
    for level_pct in CONTAM_LEVELS_PCT:
        train_df = pd.read_csv(TRAIN_DIR / f"train_contam_{level_pct}pct.csv")
        X_train = train_df[FEATURE_COLS].values.astype("float32")
        n_attack_in_train = int(train_df["is_attack"].sum())
        print(f"\n=== contamination level {level_pct}% (resampled window) "
              f"(train n={len(train_df)}, {n_attack_in_train} attack flows in it - "
              f"unsupervised, labels not used for training) ===")

        level_dir = MODEL_DIR / f"contam_{level_pct}pct"
        level_dir.mkdir(parents=True, exist_ok=True)

        for seed in SEEDS:
            seed_dir = level_dir / f"seed_{seed}"
            if (seed_dir / "threshold.json").exists():
                print(f"  seed {seed}: seed_dir already has a trained model, skipping "
                      f"(SEED-EXTENSION run must not overwrite existing seeds)")
                continue
            seed_dir.mkdir(parents=True, exist_ok=True)

            model, history, train_time = build_and_train(X_train, X_val_benign, seed)
            n_epochs = len(history.history["loss"])

            model.encoder.save(seed_dir / "encoder.keras")
            model.decoder.save(seed_dir / "decoder.keras")

            val_errors = reconstruction_error(model, X_val_benign)
            thresholds = {
                f"threshold_{p}": float(np.percentile(val_errors, p)) for p in THRESHOLD_PCTLS
            }
            threshold_info = {
                "contamination_pct": level_pct,
                "seed": seed,
                "val_benign_n": len(X_val_benign),
                "epochs_run": n_epochs,
                "train_time_sec": train_time,
                "final_val_loss": float(history.history["val_loss"][-1]),
                **thresholds,
            }
            (seed_dir / "threshold.json").write_text(json.dumps(threshold_info, indent=2))

            print(f"  seed {seed}: epochs={n_epochs:3d} train_time={train_time:5.1f}s "
                  f"val_loss={threshold_info['final_val_loss']:.4f} "
                  f"thr95={thresholds['threshold_95']:.4f} thr99={thresholds['threshold_99']:.4f}")

            run_log.append(threshold_info)

    log_path = MODEL_DIR / "training_run_log_extended.json"
    prior_log = json.loads(log_path.read_text()) if log_path.exists() else []
    new_keys = {(r["contamination_pct"], r["seed"]) for r in run_log}
    prior_log = [r for r in prior_log if (r["contamination_pct"], r["seed"]) not in new_keys]
    combined_log = prior_log + run_log
    log_path.write_text(json.dumps(combined_log, indent=2))
    print(f"\nDone: {len(run_log)} models trained this run "
          f"({len(CONTAM_LEVELS_PCT)} levels x up to {len(SEEDS)} new seeds each, "
          f"already-trained seeds skipped). "
          f"Log: {log_path} ({len(combined_log)} entries total, "
          f"{len(prior_log)} pre-existing entries preserved)")


if __name__ == "__main__":
    main()
