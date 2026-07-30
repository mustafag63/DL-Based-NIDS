"""
Build the per-source-IP inter-arrival-time (IAT) feature for the temporal
feature experiment (13_temporal_feature_experiment/), WITHOUT touching any
canonical file.

Feature definition (per findings.md section 5-6 hypothesis, but leakage-free
and IP-agnostic):
  - For each flow, IAT = ts - ts_of_previous_flow_from_same_src_ip, computed
    WITHIN the same window_id only (windows are separate captures; diffing
    across window boundaries would produce meaningless multi-hour gaps).
  - Keyed on source IP only (id.orig_h), NOT on (src, dst) pairs -- a generic
    network-rate feature, not an attacker-IP-specific rule.
  - First flow of a (window, src_ip) group has no previous flow: filled with
    the median raw IAT of BENIGN TRAIN flows (no NaN survives).
  - log10(IAT + 1e-6) transform (raw range spans ~2364x, would break the
    scaler). 1e-6 s floor is below Zeek's ts resolution, so ordering of real
    sub-ms gaps is preserved.
  - StandardScaler fit ONLY on the (all-benign) Dense-v1 train split rows,
    matching the project's leakage-free scaler rule.

Source-IP lookup: features_all_windows.csv (and the combined table used by
06_attack_type_analysis) carries no IP column, so id.orig_h is re-derived by
re-reading the raw Zeek conn.logs with EXACTLY the filtering + concat order
of faz2_feature_extraction.py (lab-IP filter, WINDOWS order, ignore_index).
Alignment is verified hard: ts and is_attack must match the combined feature
table row-for-row on all 46495 rows, else the script aborts.

Outputs (all inside 13_temporal_feature_experiment/):
  - iat_feature_all_rows.csv: row_index, window_id, ts, src_ip(hashed idx),
    is_attack, iat_raw, iat_filled_flag, iat_log, iat_log_scaled
  - iat_feature_meta.json: scaler params, fill value, verification stats
"""
import hashlib
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
NIDS_DATA_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "data")
RAW_ROOT = os.path.join(NIDS_DATA_DIR, "ids-dataset-raw-backup")

# Same order + filter constants as faz2_feature_extraction.py
WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
    "window_resampled_15pct", "window_resampled_20pct",
]
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}
ATTACKER_IP = "192.168.10.2"
CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]

FEATURES_ALL_WINDOWS = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv")
RESAMPLED_15 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target15.0_actual15.00_features.csv")
RESAMPLED_20 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target20.0_actual19.99_features.csv")
DENSE_TRAIN_IDX = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits",
                               "train_indices.csv")

OUT_CSV = os.path.join(HERE, "iat_feature_all_rows.csv")
OUT_META = os.path.join(HERE, "iat_feature_meta.json")

EPS = 1e-6


def load_raw_ip_table():
    frames = []
    for w in WINDOWS:
        conn = pd.read_csv(os.path.join(RAW_ROOT, w, "zeek", "conn.log"),
                           sep="\t", comment="#", names=CONN_COLS, na_values="-")
        conn = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
        conn["is_attack"] = (conn["id.orig_h"] == ATTACKER_IP).astype(int)
        conn["window_id"] = w
        frames.append(conn[["ts", "id.orig_h", "is_attack", "window_id"]])
    return pd.concat(frames, ignore_index=True)


def load_combined_features():
    base = pd.read_csv(FEATURES_ALL_WINDOWS, usecols=["ts", "is_attack", "window_id"])
    r15 = pd.read_csv(RESAMPLED_15, usecols=["ts", "is_attack", "window_id"])
    r20 = pd.read_csv(RESAMPLED_20, usecols=["ts", "is_attack", "window_id"])
    return pd.concat([base, r15, r20], ignore_index=True)


def main():
    raw = load_raw_ip_table()
    combined = load_combined_features()
    assert len(raw) == len(combined), (
        f"row count mismatch: raw={len(raw)} combined={len(combined)}")

    ts_ok = np.allclose(raw["ts"].values, combined["ts"].values, rtol=0, atol=1e-6)
    atk_ok = (raw["is_attack"].values == combined["is_attack"].values).all()
    assert ts_ok and atk_ok, f"alignment failed: ts_ok={ts_ok} is_attack_ok={atk_ok}"
    print(f"alignment verified on {len(raw)} rows (ts + is_attack exact match)")

    df = raw.copy()
    df["row_index"] = np.arange(len(df))

    # IAT per (window_id, src_ip), in time order within the group
    df = df.sort_values(["window_id", "id.orig_h", "ts"], kind="mergesort")
    df["iat_raw"] = df.groupby(["window_id", "id.orig_h"])["ts"].diff()
    df = df.sort_values("row_index").reset_index(drop=True)

    # fill value: median raw IAT over BENIGN TRAIN rows only
    train_idx = pd.read_csv(DENSE_TRAIN_IDX)
    assert (train_idx["is_attack"] == 0).all(), "dense train split must be all benign"
    train_rows = train_idx["row_index"].values
    fill_value = float(df.loc[df["row_index"].isin(train_rows), "iat_raw"].median())
    n_filled = int(df["iat_raw"].isna().sum())
    df["iat_filled_flag"] = df["iat_raw"].isna().astype(int)
    df["iat_raw"] = df["iat_raw"].fillna(fill_value)
    # Zeek ts has finite resolution; identical timestamps give IAT == 0,
    # which the +EPS floor handles before the log.
    df["iat_log"] = np.log10(df["iat_raw"] + EPS)

    # scaler fit ONLY on benign train rows (train split is all benign)
    train_log = df.loc[df["row_index"].isin(train_rows), "iat_log"]
    mu, sigma = float(train_log.mean()), float(train_log.std(ddof=0))
    df["iat_log_scaled"] = (df["iat_log"] - mu) / sigma

    # src ip stored as a stable anonymized token, not the raw address
    df["src_ip_token"] = df["id.orig_h"].map(
        lambda ip: hashlib.sha1(ip.encode()).hexdigest()[:8])

    out = df[["row_index", "window_id", "ts", "src_ip_token", "is_attack",
              "iat_raw", "iat_filled_flag", "iat_log", "iat_log_scaled"]]
    out.to_csv(OUT_CSV, index=False)

    meta = {
        "n_rows": len(df),
        "n_first_flow_filled": n_filled,
        "fill_value_raw_seconds": fill_value,
        "log_transform": f"log10(iat + {EPS})",
        "scaler": {"fit_on": "dense v1 train split (all benign)",
                   "n_fit_rows": int(len(train_log)), "mean": mu, "std": sigma},
        "groupby_key": ["window_id", "id.orig_h (src ip only)"],
    }
    json.dump(meta, open(OUT_META, "w"), indent=2)
    print(json.dumps(meta, indent=2))

    # quick sanity: scaled IAT by group on all rows
    for name, mask in [("benign", df["is_attack"] == 0), ("attack", df["is_attack"] == 1)]:
        s = df.loc[mask, "iat_log_scaled"]
        print(f"{name}: n={len(s)} median_scaled={s.median():.3f} "
              f"p5={s.quantile(0.05):.3f} p95={s.quantile(0.95):.3f}")


if __name__ == "__main__":
    main()
