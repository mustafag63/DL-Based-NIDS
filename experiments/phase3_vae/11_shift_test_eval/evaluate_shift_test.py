"""Evaluate the ALREADY-TRAINED final VAE (04_phase3_models/vae_encoder_final.keras
/ vae_decoder_final.keras, latent=10, beta=0.25) on window01_shift_test.csv -
the held-out half of window_01 (274 pure-benign flows, kept out of every
train/val/test split specifically because window_01 was flagged in the
11 Temmuz EDA as statistically distinct from the other 7 windows - higher
mean duration/bytes, duration CV=0.37 - a real, if small, distribution
shift within "benign").

Read-only / inference-only: loads the frozen final encoder/decoder, does
NOT retrain, does NOT touch 04_phase3_models/, latest_run/, or any of the
06-10 audit folders. Writes only into 11_shift_test_eval/.

Baseline reconstruction-error score only (per 08_beta_multiseed /
10_probabilistic_scoring, this is still the recommended default - no
reason to introduce a different score just for this check).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import keras

PHASE3_VAE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PHASE3_VAE_DIR.parent
DENSE_SPLIT_DIR = PROJECT_ROOT / "phase3_dense" / "03_phase3_splits"
FEAT_ALL_PATH = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features" / "features_all_windows.csv"
TRAIN_PATH = PHASE3_VAE_DIR / "window10_clean_train.csv"
MODEL_DIR = PHASE3_VAE_DIR / "04_phase3_models"

OUT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(PHASE3_VAE_DIR))
from model_layers import ClipLogVar, VAE2  # noqa: F401 (registers both with Keras)

FEATURE_COLS = [
    "duration_scaled", "orig_bytes_scaled", "resp_bytes_scaled",
    "orig_pkts_scaled", "resp_pkts_scaled",
    "bytes_per_sec_scaled", "pkts_per_sec_scaled", "byte_ratio_scaled",
    "proto_tcp", "proto_udp",
    "service_dns", "service_http", "service_none", "service_ssh",
    "conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF",
]
RNG_SEED = 0  # for the stochastic z-sample at inference, not model training


def reconstruction_error(encoder, decoder, X, rng):
    z_mean, z_log_var = encoder(X, training=False)
    z_mean_np, z_log_var_np = z_mean.numpy(), z_log_var.numpy()
    eps = rng.normal(size=z_mean_np.shape).astype("float32")
    z = z_mean_np + np.exp(0.5 * z_log_var_np) * eps
    recon = decoder(z, training=False).numpy()
    return np.mean(np.square(X - recon), axis=1)


def describe(errors, threshold):
    return {
        "n": len(errors),
        "mean": float(np.mean(errors)),
        "median": float(np.median(errors)),
        "std": float(np.std(errors)),
        "fpr_pct": 100.0 * float((errors > threshold).mean()),
    }


def main():
    print(f"keras {keras.__version__}")
    rng = np.random.default_rng(RNG_SEED)

    encoder = keras.models.load_model(MODEL_DIR / "vae_encoder_final.keras", safe_mode=True)
    decoder = keras.models.load_model(MODEL_DIR / "vae_decoder_final.keras", safe_mode=True)
    print("Loaded final encoder/decoder (latent=10, beta=0.25) - inference only, not retrained.")

    # ---- Data: train benign, val (for threshold calibration), test benign, window01_shift_test ----
    train_df = pd.read_csv(TRAIN_PATH)
    assert (train_df["is_attack"] == 0).all()
    X_train_benign = train_df[FEATURE_COLS].values.astype("float32")

    features_all = pd.read_csv(FEAT_ALL_PATH)
    val_idx = pd.read_csv(DENSE_SPLIT_DIR / "val_indices.csv")["row_index"].values
    test_idx = pd.read_csv(DENSE_SPLIT_DIR / "test_indices.csv")["row_index"].values
    shift_idx = pd.read_csv(DENSE_SPLIT_DIR / "window01_shift_test.csv")["row_index"].values

    val_df = features_all.iloc[val_idx].reset_index(drop=True)
    test_df = features_all.iloc[test_idx].reset_index(drop=True)
    shift_df = features_all.iloc[shift_idx].reset_index(drop=True)

    assert (shift_df["is_attack"] == 0).all(), "window01_shift_test must be 100% benign"
    assert (shift_df["window_id"] == "window_01_0pct").all()
    print(f"window01_shift_test: {len(shift_df)} flows (all benign, all window_01_0pct)")

    X_val_benign = val_df.loc[val_df["is_attack"] == 0, FEATURE_COLS].values.astype("float32")
    X_test_benign = test_df.loc[test_df["is_attack"] == 0, FEATURE_COLS].values.astype("float32")
    X_shift = shift_df[FEATURE_COLS].values.astype("float32")

    print(f"train_benign n={len(X_train_benign)}, val_benign n={len(X_val_benign)}, "
          f"test_benign n={len(X_test_benign)}, window01_shift n={len(X_shift)}")

    # ---- Threshold: pctl95 of val-benign reconstruction error (same calibration as every other phase3_vae/ script) ----
    val_errors = reconstruction_error(encoder, decoder, X_val_benign, rng)
    threshold = float(np.percentile(val_errors, 95))
    print(f"\nThreshold (val-benign pctl95) = {threshold:.5f}")

    # ---- Reconstruction error on the three comparison distributions ----
    train_errors = reconstruction_error(encoder, decoder, X_train_benign, rng)
    test_errors = reconstruction_error(encoder, decoder, X_test_benign, rng)
    shift_errors = reconstruction_error(encoder, decoder, X_shift, rng)

    stats_train = describe(train_errors, threshold)
    stats_test = describe(test_errors, threshold)
    stats_shift = describe(shift_errors, threshold)

    print(f"\n{'group':<28s} {'n':>6s} {'mean':>10s} {'median':>10s} {'std':>10s} {'FPR%':>8s}")
    for name, s in [("train benign (window_10)", stats_train), ("test benign", stats_test),
                    ("window01_shift_test", stats_shift)]:
        print(f"{name:<28s} {s['n']:>6d} {s['mean']:>10.5f} {s['median']:>10.5f} {s['std']:>10.5f} {s['fpr_pct']:>7.2f}%")

    results = {
        "threshold_pctl95_from_val": threshold,
        "train_benign": stats_train,
        "test_benign": stats_test,
        "window01_shift_test": stats_shift,
    }
    import json
    with open(OUT_DIR / "shift_test_results.json", "w") as f:
        json.dump(results, f, indent=2)

    pd.DataFrame({"error": train_errors}).to_csv(OUT_DIR / "train_benign_errors.csv", index=False)
    pd.DataFrame({"error": test_errors}).to_csv(OUT_DIR / "test_benign_errors.csv", index=False)
    pd.DataFrame({"error": shift_errors, "row_index": shift_idx}).to_csv(OUT_DIR / "window01_shift_errors.csv", index=False)

    # ---- Three-panel histogram ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=False)
    panels = [
        ("train benign\n(window_10_0pct)", train_errors, "tab:blue"),
        ("test benign\n(windows 02-08 held-out)", test_errors, "tab:green"),
        ("window01_shift_test\n(unseen benign, distribution-shifted)", shift_errors, "tab:orange"),
    ]
    max_err = max(np.percentile(train_errors, 99), np.percentile(test_errors, 99), np.percentile(shift_errors, 99))
    bins = np.linspace(0, max_err, 50)
    for ax, (title, errs, color) in zip(axes, panels):
        ax.hist(errs, bins=bins, color=color, alpha=0.75)
        ax.axvline(threshold, color="black", linestyle="--", linewidth=1, label=f"threshold={threshold:.3f}")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("reconstruction error")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("count")
    fig.suptitle("VAE reconstruction error: train / test-benign / window01_shift_test", y=1.03)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "three_distribution_histograms.png", dpi=130, bbox_inches="tight")
    print(f"\nSaved: {OUT_DIR / 'three_distribution_histograms.png'}")

    # ---- Feature-level deviation of window01_shift from train distribution (for Step 3 interpretation) ----
    train_mean = X_train_benign.mean(axis=0)
    train_std = X_train_benign.std(axis=0)
    shift_mean = X_shift.mean(axis=0)
    z_shift = (shift_mean - train_mean) / np.where(train_std > 1e-9, train_std, 1.0)
    dev_df = pd.DataFrame({
        "feature": FEATURE_COLS,
        "train_mean": train_mean, "train_std": train_std,
        "window01_shift_mean": shift_mean,
        "z_deviation": z_shift,
    }).sort_values("z_deviation", key=np.abs, ascending=False)
    dev_df.to_csv(OUT_DIR / "feature_deviation_window01_vs_train.csv", index=False)
    print(f"\nTop feature deviations (window01_shift_test mean vs train_benign, in train-std units):")
    print(dev_df.head(8).to_string(index=False))

    print(f"\nSaved: {OUT_DIR / 'shift_test_results.json'}, "
          f"{OUT_DIR / 'feature_deviation_window01_vs_train.csv'}, "
          f"per-error CSVs")


if __name__ == "__main__":
    main()
