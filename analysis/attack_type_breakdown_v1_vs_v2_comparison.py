"""
Compare the v1 autoencoders (04_phase3_models/, 18/14 flow-level columns) vs
the v2 autoencoders (04_phase3_models_v2/, 22/18 columns = the same set plus
4 rolling 60s source-IP time-window features: conn_count_60s,
unique_dst_ports_60s, unique_dst_ips_60s, failed_conn_ratio_60s) on
attack_type-level recall, extending attack_type_breakdown_evaluation.py's
methodology to a second model generation.

Hypothesis under test: v1 misses apache_bench entirely (0.00% recall, 5/5
seeds, both variants -- see attack_type_breakdown_evaluation.py) because a
single apache_bench flow is behaviorally identical to a normal fast HTTP
request. The rolling features are meant to expose the one thing a single
flow can't: many near-identical requests arriving from the same source
within the last 60 seconds. If that hypothesis is right, v2 should recover
apache_bench recall without degrading portscan/slowloris recall or raising
the benign false-positive rate.

Both v1 and v2 models are loaded (never retrained here). Preprocessing
follows phase3_autoencoder.ipynb / phase3_autoencoder_v2_train.py exactly:
threshold = 95th percentile of the model's own reconstruction error on
VAL's benign-only flows, computed fresh per seed/variant, not read from a
metrics JSON.

attack_type attribution uses the same raw-conn.log signature rule
established in attack_type_breakdown_evaluation.py (port != 80 -> portscan;
SF + orig_bytes==80 + duration<1s -> apache_bench; RSTO/S1 + duration>10s ->
slowloris; 100% coverage on the test split, verified there).

Read-only: does not modify features_all_windows.*, splits/, models/,
models_v2/, results/, or results_v2/, and does not retrain or resave any
model.
"""

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import attack_type_separability as base  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = PROJECT_ROOT / "02_phase2_feature_extraction" / "features_all_windows.csv"
SPLIT_DIR = PROJECT_ROOT / "03_phase3_splits"
RAW_DATA_DIR = Path(base.RAW_DATA_DIR)

MODEL_DIRS = {"v1": PROJECT_ROOT / "04_phase3_models", "v2": PROJECT_ROOT / "04_phase3_models_v2"}

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts"]
CONN_STATE_COLS = ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"]
ROLLING_COLS = ["conn_count_60s_scaled", "unique_dst_ports_60s_scaled", "unique_dst_ips_60s_scaled", "failed_conn_ratio_60s_scaled"]

# v1's exact original 18 columns, in the exact original order (model weights
# are order-sensitive) -- this is a strict subset of the new 22-column
# features_all_windows.csv, and verified bit-identical to the pre-rolling-
# feature backup for these columns (StandardScaler was refit on the same
# row-identical train split).
V1_FULL_COLS = [
    "duration_scaled", "orig_bytes_scaled", "resp_bytes_scaled", "orig_pkts_scaled",
    "resp_pkts_scaled", "bytes_per_sec_scaled", "pkts_per_sec_scaled", "byte_ratio_scaled",
    "proto_tcp", "proto_udp", "service_dns", "service_http", "service_none", "service_ssh",
    "conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF",
]
V1_NO_CS_COLS = [c for c in V1_FULL_COLS if c not in CONN_STATE_COLS]

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
    val_idx = pd.read_csv(SPLIT_DIR / "val_indices.csv")["row_index"].values
    test_idx = pd.read_csv(SPLIT_DIR / "test_indices.csv")["row_index"].values

    val_df = features.iloc[val_idx].reset_index(drop=True)
    test_df = features.iloc[test_idx].reset_index(drop=True)
    attack_test_df = test_df[test_df["is_attack"] == 1].copy()
    print(f"test set: n={len(test_df)}, attack flows n={len(attack_test_df)}")

    print("Classifying attack_type via raw conn.log signature match...")
    raw_cache = {}
    attack_test_df["attack_type"] = [
        classify_attack_type(w, t, raw_cache)
        for w, t in zip(attack_test_df["window_id"], attack_test_df["ts"])
    ]
    print(attack_test_df["attack_type"].value_counts())

    v2_full_cols = [c for c in features.columns if c not in META_COLS]
    v2_no_cs_cols = [c for c in v2_full_cols if c not in CONN_STATE_COLS]
    cols_by_model_version = {
        "v1": {"full_features": V1_FULL_COLS, "no_conn_state": V1_NO_CS_COLS},
        "v2": {"full_features": v2_full_cols, "no_conn_state": v2_no_cs_cols},
    }

    all_rows = []
    for version in ("v1", "v2"):
        model_dir = MODEL_DIRS[version]
        for variant in VARIANTS:
            cols = cols_by_model_version[version][variant]
            X_val_benign = val_df.loc[val_df["is_attack"] == 0, cols].values.astype("float32")
            X_test_benign = test_df.loc[test_df["is_attack"] == 0, cols].values.astype("float32")
            X_by_type = {
                atype: attack_test_df.loc[attack_test_df["attack_type"] == atype, cols].values.astype("float32")
                for atype in ATTACK_TYPES
            }

            for seed in SEEDS:
                model_path = model_dir / variant / f"autoencoder_seed{seed}.keras"
                model = tf.keras.models.load_model(model_path)

                threshold = float(np.percentile(reconstruction_error(model, X_val_benign), 95))
                benign_errors = reconstruction_error(model, X_test_benign)
                benign_fp = 100.0 * (benign_errors > threshold).mean()

                for atype in ATTACK_TYPES:
                    X = X_by_type[atype]
                    if len(X) == 0:
                        continue
                    errors = reconstruction_error(model, X)
                    recall = 100.0 * (errors > threshold).mean()
                    all_rows.append({
                        "version": version, "variant": variant, "seed": seed,
                        "attack_type": atype, "n": len(X), "recall": recall,
                        "benign_fp": benign_fp,
                    })
                print(f"[{version}/{variant}] seed={seed} threshold={threshold:.5f} benign_fp={benign_fp:.2f}%")

    summary = pd.DataFrame(all_rows)

    print(f"\n{'=' * 100}\nv1 (18/14 cols) vs v2 (22/18 cols) -- recall @ pctl95 by attack_type, 5-seed mean +/- std\n{'=' * 100}")
    for variant in VARIANTS:
        print(f"\n--- variant: {variant} ---")
        print(f"{'attack_type':<14s} {'n':>6s} {'v1 recall':>18s} {'v2 recall':>18s} {'delta':>10s}")
        for atype in ATTACK_TYPES:
            v1_sub = summary[(summary.version == "v1") & (summary.variant == variant) & (summary.attack_type == atype)]
            v2_sub = summary[(summary.version == "v2") & (summary.variant == variant) & (summary.attack_type == atype)]
            if v1_sub.empty or v2_sub.empty:
                continue
            n = int(v1_sub["n"].iloc[0])
            v1_mean, v1_std = v1_sub["recall"].mean(), v1_sub["recall"].std()
            v2_mean, v2_std = v2_sub["recall"].mean(), v2_sub["recall"].std()
            delta = v2_mean - v1_mean
            print(
                f"{atype:<14s} {n:>6d} {v1_mean:>8.2f}% +/-{v1_std:>5.2f}%   "
                f"{v2_mean:>8.2f}% +/-{v2_std:>5.2f}%   {delta:>+8.2f}pp"
            )
        v1_benign = summary[(summary.version == "v1") & (summary.variant == variant)]["benign_fp"]
        v2_benign = summary[(summary.version == "v2") & (summary.variant == variant)]["benign_fp"]
        print(
            f"{'(benign FP ref)':<14s} {'':>6s} {v1_benign.mean():>8.2f}% +/-{v1_benign.std():>5.2f}%   "
            f"{v2_benign.mean():>8.2f}% +/-{v2_benign.std():>5.2f}%   {v2_benign.mean() - v1_benign.mean():>+8.2f}pp"
        )

    print(f"\n{'=' * 100}\nAggregate comparison (all attack types combined, weighted by n)\n{'=' * 100}")
    for variant in VARIANTS:
        for version in ("v1", "v2"):
            sub = summary[(summary.version == version) & (summary.variant == variant)]
            per_seed_agg = sub.groupby("seed").apply(
                lambda g: 100.0 * (g["recall"] / 100.0 * g["n"]).sum() / g["n"].sum()
            )
            print(f"{variant} / {version}: aggregate recall (n-weighted) = {per_seed_agg.mean():.2f}% +/- {per_seed_agg.std():.2f}%")

    print(f"\n{'=' * 100}\nScenario classification\n{'=' * 100}")
    for variant in VARIANTS:
        v1_ab = summary[(summary.version == "v1") & (summary.variant == variant) & (summary.attack_type == "apache_bench")]["recall"]
        v2_ab = summary[(summary.version == "v2") & (summary.variant == variant) & (summary.attack_type == "apache_bench")]["recall"]
        v1_ps = summary[(summary.version == "v1") & (summary.variant == variant) & (summary.attack_type == "portscan")]["recall"]
        v2_ps = summary[(summary.version == "v2") & (summary.variant == variant) & (summary.attack_type == "portscan")]["recall"]
        v1_sl = summary[(summary.version == "v1") & (summary.variant == variant) & (summary.attack_type == "slowloris")]["recall"]
        v2_sl = summary[(summary.version == "v2") & (summary.variant == variant) & (summary.attack_type == "slowloris")]["recall"]
        v1_fp = summary[(summary.version == "v1") & (summary.variant == variant)]["benign_fp"]
        v2_fp = summary[(summary.version == "v2") & (summary.variant == variant)]["benign_fp"]

        ab_gain = v2_ab.mean() - v1_ab.mean()
        ps_delta = v2_ps.mean() - v1_ps.mean()
        sl_delta = v2_sl.mean() - v1_sl.mean()
        fp_delta = v2_fp.mean() - v1_fp.mean()

        print(f"\n{variant}: apache_bench {v1_ab.mean():.2f}%->{v2_ab.mean():.2f}% ({ab_gain:+.2f}pp), "
              f"portscan delta={ps_delta:+.2f}pp, slowloris delta={sl_delta:+.2f}pp, benign FP delta={fp_delta:+.2f}pp")

        if ab_gain > 50 and ps_delta > -5 and sl_delta > -5 and fp_delta < 10:
            print("  -> (a) apache_bench substantially fixed, portscan/slowloris/benign-FP not degraded: HYPOTHESIS CONFIRMED.")
        elif ab_gain > 10 and (ps_delta < -5 or sl_delta < -5 or fp_delta >= 10):
            print("  -> (b) apache_bench partially fixed but with a trade-off elsewhere: mixed result, needs discussion.")
        else:
            print("  -> (c) apache_bench still not caught: hypothesis refuted, root cause is elsewhere.")


if __name__ == "__main__":
    main()
