"""Latent-dim ablation for audit finding O1 (11_fable_review/independent_audit.md).

O1: the canonical VAE has latent_dim=10 fed by an 8-unit bottleneck
(18 -> Dense(16) -> Dense(8) -> z_mean/z_log_var(10)), so the latent code can
carry at most 8 degrees of freedom and "latent=10" is nominal capacity that
does not exist. This run trains a second variant with latent_dim=8 (== the
bottleneck width) and compares it to the canonical latent=10 models under the
exact same everything else:

  - same VAE class (imported from train_contamination_sweep_original_seedext),
    beta=0.25, dropout=0.1, batch=64, epochs<=200, patience=12, Adam(clipnorm=1)
  - same clean-only train set (02_contaminated_train_sets/train_contam_0pct.csv),
    same val_benign.csv for early stopping + threshold, same test flows
  - same 20 seeds (0-19)
  - same deterministic z_mean scoring + per-seed val-benign threshold_95
    (VAEBackend(deterministic=True), the post-O2 canonical convention)

Everything lands in 12_latent_ablation/ -- the original latent=10 models and
results are not touched. Comparison metrics are computed on the canonical
(non-dedup) evaluation set for BOTH variants so the paired per-seed diffs are
apples-to-apples (the hybrid dedup correction in 10_final_report only affects
published PR-AUC/F1 and applies equally to both variants).

Active-dim count uses 09_collapse_investigation's convention:
std(z_mean_j) over the clean train set > 0.15.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SWEEP_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SWEEP_DIR))
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

sys.path.insert(0, SWEEP_DIR)
sys.path.insert(0, ATTACK_TYPE_DIR)

import tensorflow as tf  # noqa: E402
from train_contamination_sweep_original_seedext import (  # noqa: E402
    VAE, BETA, DROPOUT_RATE, BATCH_SIZE, EPOCHS, PATIENCE, INPUT_DIM,
    FEATURE_COLS, DATA_DIR, TRAIN_DIR,
)
import evaluate_by_attack_type as single  # noqa: E402

LATENT_DIM_ABLATION = 8
SEEDS = list(range(20))
ACTIVE_STD_THRESHOLD = 0.15  # 09_collapse_investigation/latent_sweep.py convention

MODEL_DIR = os.path.join(HERE, "04_models", "latent8_contam_0pct")
CANONICAL_MODEL_DIR = os.path.join(SWEEP_DIR, "04_models", "contam_0pct")

PER_SEED_L8_CSV = os.path.join(HERE, "results_latent8_per_seed.csv")
PER_SEED_L10_CSV = os.path.join(HERE, "results_latent10_per_seed.csv")
COMPARISON_CSV = os.path.join(HERE, "comparison_latent8_vs_latent10.csv")
COMPARISON_MD = os.path.join(HERE, "comparison_latent8_vs_latent10.md")
ACTIVE_DIMS_CSV = os.path.join(HERE, "active_dims_per_seed.csv")

METRICS = ["roc_auc", "pr_auc", "attack_recall", "f1", "benign_fpr"]
N_BOOT = 10_000
RNG = np.random.default_rng(12_2025)


def train_all_seeds():
    val_benign_df = pd.read_csv(os.path.join(DATA_DIR, "val_benign.csv"))
    assert (val_benign_df["is_attack"] == 0).all()
    X_val = val_benign_df[FEATURE_COLS].values.astype("float32")

    train_df = pd.read_csv(os.path.join(TRAIN_DIR, "train_contam_0pct.csv"))
    assert int(train_df["is_attack"].sum()) == 0
    X_train = train_df[FEATURE_COLS].values.astype("float32")
    print(f"train n={len(X_train)} (clean-only), val_benign n={len(X_val)}, "
          f"latent_dim={LATENT_DIM_ABLATION}, beta={BETA}")

    for seed in SEEDS:
        seed_dir = os.path.join(MODEL_DIR, f"seed_{seed}")
        if os.path.exists(os.path.join(seed_dir, "threshold.json")):
            print(f"  seed {seed}: already trained, skipping")
            continue
        os.makedirs(seed_dir, exist_ok=True)

        tf.keras.utils.set_random_seed(seed)
        model = VAE(INPUT_DIM, LATENT_DIM_ABLATION, beta=BETA, dropout_rate=DROPOUT_RATE)
        model.compile(optimizer=tf.keras.optimizers.Adam(clipnorm=1.0))
        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=PATIENCE, restore_best_weights=True
        )
        t0 = time.time()
        history = model.fit(
            X_train, X_train,
            validation_data=(X_val, X_val),
            epochs=EPOCHS, batch_size=BATCH_SIZE, shuffle=True,
            callbacks=[early_stop], verbose=0,
        )
        train_time = time.time() - t0
        n_epochs = len(history.history["loss"])

        model.encoder.save(os.path.join(seed_dir, "encoder.keras"))
        model.decoder.save(os.path.join(seed_dir, "decoder.keras"))

        # same stochastic threshold.json layout as the canonical seed dirs, so
        # VAEBackend can point here unchanged; the deterministic evaluation
        # below recomputes threshold_95 from val-benign z_mean errors anyway.
        recon, _, _ = model(X_val, training=False)
        val_errors = np.mean(np.square(X_val - recon.numpy()), axis=1)
        threshold_info = {
            "contamination_pct": 0,
            "latent_dim": LATENT_DIM_ABLATION,
            "seed": seed,
            "val_benign_n": len(X_val),
            "epochs_run": n_epochs,
            "train_time_sec": train_time,
            "final_val_loss": float(history.history["val_loss"][-1]),
            "threshold_95": float(np.percentile(val_errors, 95)),
            "threshold_99": float(np.percentile(val_errors, 99)),
        }
        with open(os.path.join(seed_dir, "threshold.json"), "w") as f:
            json.dump(threshold_info, f, indent=2)
        print(f"  seed {seed}: epochs={n_epochs:3d} train_time={train_time:5.1f}s "
              f"val_loss={threshold_info['final_val_loss']:.4f}")

    return X_train


def evaluate_backend(backend, out_csv):
    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)
    rows = []
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        rows.extend(single.evaluate_group(subset, feature_cols, attack_type, backend=backend))
    per_seed = pd.DataFrame(rows)
    per_seed.to_csv(out_csv, index=False)
    return per_seed


def bootstrap_ci(diffs):
    """95% CI of the mean of paired per-seed diffs, bootstrap over seeds."""
    diffs = np.asarray(diffs)
    idx = RNG.integers(0, len(diffs), size=(N_BOOT, len(diffs)))
    boot_means = diffs[idx].mean(axis=1)
    return float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))


def count_active_dims(encoder, X):
    z_mean, _ = encoder(X, training=False)
    stds = z_mean.numpy().std(axis=0)
    return int((stds > ACTIVE_STD_THRESHOLD).sum()), stds


def main():
    X_train = train_all_seeds()

    print("\n" + "=" * 70)
    print("Evaluating latent=8 (deterministic z_mean, per-seed val-benign thr95)")
    print("=" * 70)
    backend_l8 = single.VAEBackend(model_dir=MODEL_DIR, seeds=SEEDS, deterministic=True)
    per_seed_l8 = evaluate_backend(backend_l8, PER_SEED_L8_CSV)

    print("\n" + "=" * 70)
    print("Evaluating canonical latent=10 (same deterministic convention)")
    print("=" * 70)
    backend_l10 = single.VAEBackend(model_dir=CANONICAL_MODEL_DIR, seeds=SEEDS,
                                    deterministic=True)
    per_seed_l10 = evaluate_backend(backend_l10, PER_SEED_L10_CSV)

    # ---- paired comparison ----
    merged = per_seed_l8.merge(per_seed_l10, on=["attack_type", "seed"],
                               suffixes=("_l8", "_l10"))
    comp_rows = []
    for attack_type in single.ATTACK_TYPES:
        sub = merged[merged["attack_type"] == attack_type]
        for metric in METRICS:
            a, b = sub[f"{metric}_l8"].values, sub[f"{metric}_l10"].values
            diffs = a - b
            lo, hi = bootstrap_ci(diffs)
            comp_rows.append({
                "attack_type": attack_type, "metric": metric,
                "latent8_mean": a.mean(), "latent8_std": a.std(ddof=1),
                "latent10_mean": b.mean(), "latent10_std": b.std(ddof=1),
                "paired_diff_mean": diffs.mean(),
                "diff_ci95_lo": lo, "diff_ci95_hi": hi,
                "ci_excludes_zero": bool(lo > 0 or hi < 0),
            })
    comp = pd.DataFrame(comp_rows)
    comp.to_csv(COMPARISON_CSV, index=False)

    # ---- active dims ----
    act_rows = []
    for label, backend, latent_dim in [("latent8", backend_l8, 8),
                                       ("latent10", backend_l10, 10)]:
        for seed in SEEDS:
            model = backend.load(seed)
            n_active, stds = count_active_dims(model["encoder"], X_train)
            act_rows.append({"variant": label, "seed": seed, "latent_dim": latent_dim,
                             "n_active_dims": n_active,
                             "active_ratio": n_active / latent_dim,
                             "zmean_stds": json.dumps([round(float(s), 4) for s in stds])})
    act = pd.DataFrame(act_rows)
    act.to_csv(ACTIVE_DIMS_CSV, index=False)
    act_summary = act.groupby("variant")["n_active_dims"].agg(["mean", "std", "min", "max"])

    # ---- markdown summary ----
    lines = [
        "# Latent-dim ablation: latent=8 (== bottleneck) vs. canonical latent=10",
        "",
        "Audit finding O1: latent_dim (10) > bottleneck width (8), so nominal",
        "latent capacity exceeds what the encoder can express (rank <= 8).",
        "This run: identical everything (clean-only train set, beta=0.25, 20 seeds",
        "0-19, deterministic z_mean scoring, per-seed val-benign threshold_95),",
        "only latent_dim changed 10 -> 8. Paired per-seed diffs, bootstrap 95% CI",
        f"({N_BOOT} resamples over the 20 seeds).",
        "",
        "Metrics computed on the canonical (non-dedup) evaluation set for both",
        "variants; the published hybrid dedup correction affects PR-AUC/F1 only",
        "and would apply identically to both.",
        "",
        "## Per-attack-type comparison (20-seed mean +/- std)",
        "",
        "| attack_type | metric | latent=8 | latent=10 | paired diff (8-10) | 95% CI | CI excludes 0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in comp.iterrows():
        lines.append(
            f"| {r['attack_type']} | {r['metric']} | "
            f"{r['latent8_mean']:.4f} ± {r['latent8_std']:.4f} | "
            f"{r['latent10_mean']:.4f} ± {r['latent10_std']:.4f} | "
            f"{r['paired_diff_mean']:+.4f} | "
            f"[{r['diff_ci95_lo']:+.4f}, {r['diff_ci95_hi']:+.4f}] | "
            f"{'**yes**' if r['ci_excludes_zero'] else 'no'} |"
        )
    lines += [
        "",
        "## Active latent dimensions (std(z_mean) > "
        f"{ACTIVE_STD_THRESHOLD} on the clean train set, "
        "09_collapse_investigation convention)",
        "",
        act_summary.to_markdown(),
        "",
    ]
    with open(COMPARISON_MD, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n" + "=" * 70)
    print(comp.to_string(index=False))
    print()
    print(act_summary.to_string())
    print(f"\nOutputs written to {HERE}")


if __name__ == "__main__":
    main()
