"""
Break down the Phase 3 autoencoders' test-set detection performance by
attack_type (portscan / apache_bench / slowloris), instead of the aggregate
"attack" label used everywhere so far (e.g. F1=0.862 in
05_phase3_results/full_features/seed0_metrics.json). This closes the open
context.md TODO: it was noted that ~33% of attack flows have |z|>3 on
pkts_per_sec/byte_ratio, but how that 33% distributes across the 3 attack
types was never checked.

This script does NOT train anything -- it loads the 10 existing `.keras`
models (5 seeds x 2 variants) from `04_phase3_models/` and follows the exact
preprocessing/threshold logic from `phase3_autoencoder.ipynb`
(also used identically in window01_shift_test_evaluation.py):
  - FULL_COLS = all columns except META_COLS -> 18 columns.
  - NO_CS_COLS = FULL_COLS minus the 4 conn_state one-hot columns -> 14.
  - threshold = 95th percentile of reconstruction error on VAL's benign-only
    flows, computed fresh per seed/variant (not read from metrics JSONs).

Attack_type attribution uses the CORRECTED method established in
attack_type_separability.py / attack_type_strict_boundary_check.py /
attack_type_low_n_observation.py, not the original loose ts-tolerance
method (which was shown to bleed slowloris flows into apache_bench across
the ~0.4s gap between commands). Rather than re-deriving attack_log.csv
time windows, this script uses the STRONGER, simpler signature check that
emerged from that investigation, applied directly against each flow's raw
Zeek conn.log record (joined back via the exact (window_id, ts) key,
which is unique and lossless from Phase 2's feature extraction):

  - portscan:      id.resp_p != 80
                    (only nmap targets ports other than 80 in this dataset;
                    ab.exe and slowloris exclusively target port 80/http,
                    confirmed in every raw-log spot check across all 8
                    windows in the prior validation rounds)
  - apache_bench:   id.resp_p == 80, conn_state == SF, orig_bytes == 80,
                    duration < 1.0s
                    (ab.exe's GET request is a fixed 80-byte request that
                    completes and closes cleanly; verified against raw
                    conn.log in both high-N and low-N windows)
  - slowloris:      id.resp_p == 80, conn_state in {RSTO, S1}, duration > 10s
                    (slowloris deliberately holds the connection open until
                    a ~28-30s OS-level timeout forces a reset/half-open
                    state; RSTO is the majority case, S1 -- connection
                    established, no further data -- accounts for a small
                    number of same-duration variants)

  This 3-way rule set achieves 100% coverage on the test split's 1903
  attack flows (895 portscan, 630 slowloris, 378 apache_bench, 0
  unclassified) -- verified before writing this script.

Read-only: does not modify features_all_windows.*, splits/, models/, or
results/, and does not retrain or resave any model.
"""

import glob
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import attack_type_separability as base  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = PROJECT_ROOT / "02_phase2_feature_extraction" / "features_all_windows.csv"
SPLIT_DIR = PROJECT_ROOT / "03_phase3_splits"
MODEL_DIR = PROJECT_ROOT / "04_phase3_models"
RAW_DATA_DIR = Path(base.RAW_DATA_DIR)

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts"]
CONN_STATE_COLS = ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"]
SEEDS = (0, 1, 2, 3, 4)
VARIANTS = ("full_features", "no_conn_state")
ATTACK_TYPES = ("portscan", "apache_bench", "slowloris")

CONN_LOG_COLUMNS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]


def load_raw_conn_log(window_id):
    path = glob.glob(str(RAW_DATA_DIR / window_id / "zeek" / "conn.log"))[0]
    raw = pd.read_csv(path, sep="\t", comment="#", header=None, names=CONN_LOG_COLUMNS)
    for col in ["duration", "orig_bytes", "resp_bytes", "id.resp_p"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    return raw.set_index("ts")


def classify_attack_type(window_id, ts, raw_cache):
    if window_id not in raw_cache:
        raw_cache[window_id] = load_raw_conn_log(window_id)
    row = raw_cache[window_id].loc[ts]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    if row["id.resp_p"] != 80:
        return "portscan"
    if row["conn_state"] == "SF" and row["orig_bytes"] == 80 and row["duration"] < 1.0:
        return "apache_bench"
    if row["conn_state"] in ("RSTO", "S1") and row["duration"] > 10.0:
        return "slowloris"
    return "unclassified"


def reconstruction_error(model, X):
    recon = model.predict(X, verbose=0)
    return np.mean(np.square(X - recon), axis=1)


def main():
    print("Loading features_all_windows.csv and split files (read-only)...")
    features = pd.read_csv(FEATURES_PATH)
    train_idx = pd.read_csv(SPLIT_DIR / "train_indices.csv")["row_index"].values  # noqa: F841 (kept for parity with notebook loading)
    val_idx = pd.read_csv(SPLIT_DIR / "val_indices.csv")["row_index"].values
    test_idx = pd.read_csv(SPLIT_DIR / "test_indices.csv")["row_index"].values

    val_df = features.iloc[val_idx].reset_index(drop=True)
    test_df = features.iloc[test_idx].reset_index(drop=True)

    attack_test_df = test_df[test_df["is_attack"] == 1].copy()
    print(f"test set: n={len(test_df)}, attack flows n={len(attack_test_df)}")

    print("Classifying attack_type via raw conn.log signature match (port / conn_state / duration / orig_bytes)...")
    raw_cache = {}
    attack_test_df["attack_type"] = [
        classify_attack_type(w, t, raw_cache)
        for w, t in zip(attack_test_df["window_id"], attack_test_df["ts"])
    ]
    print(attack_test_df["attack_type"].value_counts())
    n_unclassified = int((attack_test_df["attack_type"] == "unclassified").sum())
    if n_unclassified:
        print(f"WARNING: {n_unclassified} attack flows did not match any signature and are excluded below.")

    full_cols = [c for c in features.columns if c not in META_COLS]
    no_cs_cols = [c for c in full_cols if c not in CONN_STATE_COLS]
    cols_by_variant = {"full_features": full_cols, "no_conn_state": no_cs_cols}

    all_rows = []
    for variant in VARIANTS:
        cols = cols_by_variant[variant]
        X_val_benign = val_df.loc[val_df["is_attack"] == 0, cols].values.astype("float32")
        X_test_benign = test_df.loc[test_df["is_attack"] == 0, cols].values.astype("float32")
        X_by_type = {
            atype: attack_test_df.loc[attack_test_df["attack_type"] == atype, cols].values.astype("float32")
            for atype in ATTACK_TYPES
        }

        print(f"\n{'=' * 100}\nVariant: {variant} ({len(cols)} columns)\n{'=' * 100}")

        for seed in SEEDS:
            model_path = MODEL_DIR / variant / f"autoencoder_seed{seed}.keras"
            model = tf.keras.models.load_model(model_path)

            threshold = float(np.percentile(reconstruction_error(model, X_val_benign), 95))
            benign_errors = reconstruction_error(model, X_test_benign)
            benign_stats = {
                "mean": float(np.mean(benign_errors)), "median": float(np.median(benign_errors)),
                "std": float(np.std(benign_errors)),
                "pct_flagged": 100.0 * (benign_errors > threshold).mean(),
            }

            print(f"\n--- seed={seed} (threshold = val-benign pctl95 = {threshold:.5f}) ---")
            print(f"{'group':<16s} {'n':>6s} {'mean':>12s} {'median':>10s} {'std':>12s} {'recall/FP%':>10s}")
            print(
                f"{'test benign':<16s} {len(X_test_benign):>6d} {benign_stats['mean']:>12.5f} "
                f"{benign_stats['median']:>10.5f} {benign_stats['std']:>12.5f} {benign_stats['pct_flagged']:>9.2f}%"
            )

            for atype in ATTACK_TYPES:
                X = X_by_type[atype]
                if len(X) == 0:
                    continue
                errors = reconstruction_error(model, X)
                stats = {
                    "mean": float(np.mean(errors)), "median": float(np.median(errors)),
                    "std": float(np.std(errors)),
                    "pct_flagged": 100.0 * (errors > threshold).mean(),
                }
                print(
                    f"{atype:<16s} {len(X):>6d} {stats['mean']:>12.5f} {stats['median']:>10.5f} "
                    f"{stats['std']:>12.5f} {stats['pct_flagged']:>9.2f}%"
                )
                all_rows.append({
                    "variant": variant, "seed": seed, "attack_type": atype, "n": len(X),
                    "mean": stats["mean"], "median": stats["median"], "std": stats["std"],
                    "recall_pctl95": stats["pct_flagged"],
                    "benign_pct_flagged": benign_stats["pct_flagged"],
                })

    summary = pd.DataFrame(all_rows)

    print(f"\n{'=' * 100}\n5-seed summary by attack_type (mean +/- std across seeds)\n{'=' * 100}")
    for variant in VARIANTS:
        print(f"\n{variant}:")
        v = summary[summary["variant"] == variant]
        print(f"  {'attack_type':<14s} {'n(test)':>8s} {'mean error (avg of seed means)':>32s} {'recall @ pctl95':>20s}")
        for atype in ATTACK_TYPES:
            sub = v[v["attack_type"] == atype]
            if sub.empty:
                continue
            n = int(sub["n"].iloc[0])
            mean_of_means = sub["mean"].mean()
            recall_mean = sub["recall_pctl95"].mean()
            recall_std = sub["recall_pctl95"].std()
            print(
                f"  {atype:<14s} {n:>8d} {mean_of_means:>32.5f} "
                f"{recall_mean:>10.2f}% +/- {recall_std:>5.2f}%"
            )
        benign_fp_mean = v["benign_pct_flagged"].mean()
        benign_fp_std = v["benign_pct_flagged"].std()
        print(f"  {'(test benign FP ref)':<14s} {'':>8s} {'':>32s} {benign_fp_mean:>10.2f}% +/- {benign_fp_std:>5.2f}%")

    print(f"\n{'=' * 100}\nComparison across attack types (recall @ pctl95, mean +/- std, 5 seeds)\n{'=' * 100}")
    pivot = summary.pivot_table(
        index="attack_type", columns="variant", values="recall_pctl95", aggfunc=["mean", "std"]
    )
    print(pivot)

    print(f"\n{'=' * 100}\nInterpretation\n{'=' * 100}")
    for variant in VARIANTS:
        v = summary[summary["variant"] == variant]
        recalls = {
            atype: v.loc[v["attack_type"] == atype, "recall_pctl95"].mean()
            for atype in ATTACK_TYPES if not v.loc[v["attack_type"] == atype].empty
        }
        best = max(recalls, key=recalls.get)
        worst = min(recalls, key=recalls.get)
        print(f"\n{variant}: best-detected = {best} ({recalls[best]:.2f}%), worst-detected = {worst} ({recalls[worst]:.2f}%)")


if __name__ == "__main__":
    main()
