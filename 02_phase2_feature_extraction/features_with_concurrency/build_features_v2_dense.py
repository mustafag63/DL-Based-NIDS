"""
Canonical (Dense pipeline) v2 feature extraction: original 18 modeling
features (unchanged, copied verbatim from features_all_windows.csv + the two
resampled by_window feature files) plus ONE new feature,
`concurrency_src_1s_scaled`, promoted from
14_concurrency_feature_experiment/ (Config A there: recall @thr95
0.0262 -> 0.9135 on apache_bench, +0.0026 benign-FPR cost, knock-out
confirmed the gain is genuinely carried by this feature).

Scope of this script: DENSE PIPELINE ONLY (row_index-indexed combined
feature table spanning windows 01-08 + window_resampled_15pct/20pct, the
same 46495-row table 06_attack_type_analysis/evaluate_by_attack_type.py's
build_combined_features() reconstructs). The VAE pipeline (window_10-based)
is a separate, later stage -- not touched here.

Feature definition -- IDENTICAL formula to 14_concurrency_feature_experiment/
build_concurrency_features.py's concurrency_src_1s:
  for each flow, count of flows from the SAME SOURCE IP (id.orig_h, purely
  data-driven, no hardcoded IP value anywhere) with |ts_i - ts_j| <= 1s,
  within the same window_id (no cross-window diffing), excluding itself.
  log1p transform, then StandardScaler fit ONLY on phase3_dense's own
  train_indices.csv (all-benign) -- same leakage-free rule as every other
  feature in this project.

No canonical file is overwritten: reads features_all_windows.csv, the two
by_window resampled CSVs, and phase3_dense/03_phase3_splits/train_indices.csv
read-only; writes only into this new features_with_concurrency/ folder.

Output: features_with_concurrency/features_v2_all_rows.csv
  columns: row_index, window_id, ts, is_attack, <18 original _scaled/one-hot
  columns, unchanged>, concurrency_src_1s_scaled
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
NIDS_DATA_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "data")
RAW_ROOT = os.path.join(NIDS_DATA_DIR, "ids-dataset-raw-backup")

WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
    "window_resampled_15pct", "window_resampled_20pct",
]
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}
ATTACKER_IP = "192.168.10.2"  # alignment-check only, never feeds the feature math
CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]

FEATURES_ALL_WINDOWS = os.path.join(PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv")
RESAMPLED_15 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target15.0_actual15.00_features.csv")
RESAMPLED_20 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target20.0_actual19.99_features.csv")
DENSE_TRAIN_IDX = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits", "train_indices.csv")

OUT_CSV = os.path.join(HERE, "features_v2_all_rows.csv")
OUT_META = os.path.join(HERE, "features_v2_meta.json")

RADIUS = 1.0


def load_raw_src_table():
    frames = []
    for w in WINDOWS:
        conn = pd.read_csv(os.path.join(RAW_ROOT, w, "zeek", "conn.log"),
                           sep="\t", comment="#", names=CONN_COLS, na_values="-")
        conn = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
        conn["is_attack"] = (conn["id.orig_h"] == ATTACKER_IP).astype(int)
        conn["window_id"] = w
        frames.append(conn[["ts", "id.orig_h", "is_attack", "window_id"]])
    return pd.concat(frames, ignore_index=True)


def load_original_18_feature_table():
    base = pd.read_csv(FEATURES_ALL_WINDOWS)
    r15 = pd.read_csv(RESAMPLED_15)
    r20 = pd.read_csv(RESAMPLED_20)
    combined = pd.concat([base, r15, r20], ignore_index=True)
    combined["row_index"] = np.arange(len(combined))
    return combined


def concurrency_src_count(df, r):
    """Vectorized: for each (window_id, id.orig_h) group, sort by ts and use
    searchsorted for O(n log n) window-bound lookup. Returns counts aligned
    to df's original row order."""
    n = len(df)
    out = np.empty(n, dtype="int64")
    for _, idx in df.groupby(["window_id", "id.orig_h"], sort=False).indices.items():
        idx = np.asarray(idx)
        order = np.argsort(df["ts"].values[idx], kind="mergesort")
        idx_sorted = idx[order]
        ts_sorted = df["ts"].values[idx_sorted]
        lo = np.searchsorted(ts_sorted, ts_sorted - r, side="left")
        hi = np.searchsorted(ts_sorted, ts_sorted + r, side="right")
        out[idx_sorted] = (hi - lo) - 1  # exclude self
    return out


def main():
    raw = load_raw_src_table()
    combined = load_original_18_feature_table()
    assert len(raw) == len(combined), f"row mismatch: raw={len(raw)} combined={len(combined)}"
    ts_ok = np.allclose(raw["ts"].values, combined["ts"].values, rtol=0, atol=1e-6)
    atk_ok = (raw["is_attack"].values == combined["is_attack"].values).all()
    win_ok = (raw["window_id"].values == combined["window_id"].values).all()
    assert ts_ok and atk_ok and win_ok, (
        f"alignment failed: ts_ok={ts_ok} is_attack_ok={atk_ok} window_id_ok={win_ok}")
    print(f"Alignment verified on FULL dataset: {len(raw)} rows "
          f"(ts + is_attack + window_id exact match, no subsampling).")

    raw_count = concurrency_src_count(raw, RADIUS)
    log_count = np.log1p(raw_count)

    train_idx = pd.read_csv(DENSE_TRAIN_IDX)
    assert (train_idx["is_attack"] == 0).all(), "dense train split must be all benign"
    train_rows = train_idx["row_index"].values
    train_mask = np.isin(combined["row_index"].values, train_rows)

    mu = float(log_count[train_mask].mean())
    sigma = float(log_count[train_mask].std(ddof=0)) or 1.0
    scaled = (log_count - mu) / sigma

    out = combined.copy()
    out["concurrency_src_1s_scaled"] = scaled
    out.to_csv(OUT_CSV, index=False)

    meta = {
        "n_rows": len(out),
        "new_feature": "concurrency_src_1s_scaled",
        "formula": "log1p(count of same-source-IP flows within |dt|<=1s, same window_id, excl. self)",
        "provenance": "promoted from 14_concurrency_feature_experiment/ Config A "
                      "(apache_bench recall 0.0262 -> 0.9135, benign FPR +0.0026, knock-out confirmed)",
        "scaler": {"fit_on": "phase3_dense train split (all benign)",
                   "n_fit_rows": int(train_mask.sum()), "mean_log": mu, "std_log": sigma},
        "note": "no hardcoded attacker/benign IP value used in the feature math; "
                "ATTACKER_IP only used to verify alignment against the combined table's is_attack column.",
        "original_18_features": "copied verbatim from features_all_windows.csv + the two "
                                "resampled by_window feature CSVs, unchanged.",
    }
    json.dump(meta, open(OUT_META, "w"), indent=2)
    print(json.dumps(meta, indent=2))
    print(f"\nWrote {OUT_CSV}")

    for name, mask in [("benign", out["is_attack"] == 0), ("attack", out["is_attack"] == 1)]:
        s = out.loc[mask, "concurrency_src_1s_scaled"]
        print(f"{name}: n={len(s)} mean={s.mean():.3f} median={s.median():.3f}")


if __name__ == "__main__":
    main()
