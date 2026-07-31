"""
Phase 3 (VAE) - window_10_0pct clean-train feature prep.

window_10_0pct is VAE-only: it must NEVER be merged into the Dense
pipeline's WINDOWS list (faz2_feature_extraction.py) or its 03_phase3_splits/
- doing so would reshuffle Dense's frozen GroupShuffleSplit (signature_id is
window_id-prefixed, so window_10 would land in its own groups, but adding
it to benign_rest changes the group population fed into GroupShuffleSplit
for ALL windows, invalidating the existing 23274/6576/6581 split and the
already-recorded AUC=0.9463 Dense result).

Instead: window_10's raw conn.log is fed through the same derived-feature
formulas (bytes_per_sec, pkts_per_sec, byte_ratio) as faz2_feature_extraction.py,
then scaled/encoded with a StandardScaler + OneHotEncoder refit ONLY on
Dense's own train split (phase3_dense/03_phase3_splits/train_indices.csv) -
not fit fresh on window_10 - so the output stays on the exact same scale as
the val/test set the VAE will eventually be evaluated against. Dense's own
files (faz2_feature_extraction.py, features_all_windows.csv/parquet,
phase3_dense/03_phase3_splits/) are read-only here, never written.

Caveat (see printed report): window_10 contains proto=icmp and
conn_state in {OTH, S0}, none of which Dense's OneHotEncoder ever saw
(Dense's 8 windows only produced tcp/udp and REJ/RSTO/S1/SF). Those flows
keep handle_unknown="ignore"'s all-zero encoding for that column - the
categorical signal for icmp/OTH/S0 flows is lost, not fabricated.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, OneHotEncoder

RAW_ROOT = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-raw-backup"
PROJECT_ROOT = Path(__file__).parent.parent
DENSE_TRAIN_INDICES = PROJECT_ROOT / "phase3_dense" / "03_phase3_splits" / "train_indices.csv"
OUT_PATH = Path(__file__).parent / "window10_clean_train.csv"

# Windows + column layout duplicated from faz2_feature_extraction.py on
# purpose (that script isn't import-safe - it executes and writes files at
# module scope) - kept in the exact same order so a freshly rebuilt
# conn_all reproduces the same row_index -> row mapping as the frozen run.
DENSE_WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
]
WINDOW_10 = "window_10_0pct"

ATTACKER_IP = "192.168.10.2"
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}

CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]
NUMERIC_COLS = [
    "duration", "orig_bytes", "resp_bytes",
    "orig_pkts", "resp_pkts",
    "bytes_per_sec", "pkts_per_sec", "byte_ratio",
]
CATEGORICAL_COLS = ["proto", "service", "conn_state"]


def load_window(window_id: str) -> pd.DataFrame:
    win_dir = RAW_ROOT / window_id
    conn = pd.read_csv(win_dir / "zeek" / "conn.log", sep="\t", comment="#", names=CONN_COLS, na_values="-")
    conn_lab = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
    conn_lab["is_attack"] = (conn_lab["id.orig_h"] == ATTACKER_IP).astype(int)
    conn_lab["window_id"] = window_id

    meta = json.loads((win_dir / "window_meta.json").read_text())
    conn_lab["actual_attack_pct"] = meta["actual_attack_pct"]

    conn_lab["duration"] = conn_lab["duration"].fillna(0.0)
    conn_lab["orig_bytes"] = conn_lab["orig_bytes"].fillna(0)
    conn_lab["resp_bytes"] = conn_lab["resp_bytes"].fillna(0)
    conn_lab["orig_pkts"] = conn_lab["orig_pkts"].fillna(0)
    conn_lab["service"] = conn_lab["service"].fillna("none")

    zero_duration = conn_lab["duration"] == 0
    conn_lab["bytes_per_sec"] = 0.0
    conn_lab["pkts_per_sec"] = 0.0
    conn_lab.loc[~zero_duration, "bytes_per_sec"] = (
        conn_lab.loc[~zero_duration, "orig_bytes"] / conn_lab.loc[~zero_duration, "duration"]
    )
    conn_lab.loc[~zero_duration, "pkts_per_sec"] = (
        conn_lab.loc[~zero_duration, "orig_pkts"] / conn_lab.loc[~zero_duration, "duration"]
    )
    conn_lab["byte_ratio"] = conn_lab["orig_bytes"] / (conn_lab["resp_bytes"] + 1)
    return conn_lab


def build_dense_conn_all() -> pd.DataFrame:
    frames = [load_window(w) for w in DENSE_WINDOWS]
    conn_all = pd.concat(frames, ignore_index=True)
    conn_all["row_index"] = np.arange(len(conn_all))
    return conn_all


def refit_dense_scaler_and_encoder(conn_all: pd.DataFrame) -> tuple[StandardScaler, OneHotEncoder]:
    train_row_index = pd.read_csv(DENSE_TRAIN_INDICES)["row_index"].values
    train_rows = conn_all[conn_all["row_index"].isin(train_row_index)]
    assert len(train_rows) == len(train_row_index), (
        f"Rebuilt conn_all doesn't reproduce Dense's train_indices.csv row_index set "
        f"({len(train_rows)} matched vs {len(train_row_index)} expected) - "
        "raw conn.log files must have changed since the frozen Dense run."
    )

    scaler = StandardScaler()
    scaler.fit(train_rows[NUMERIC_COLS])

    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoder.fit(conn_all[CATEGORICAL_COLS])

    return scaler, encoder


def main() -> None:
    print("Rebuilding Dense's conn_all (windows 01-08) to refit scaler/encoder read-only...")
    dense_conn_all = build_dense_conn_all()
    scaler, encoder = refit_dense_scaler_and_encoder(dense_conn_all)
    print(f"Scaler refit on {scaler.n_samples_seen_} train rows (expected 23274).")
    print(f"Encoder categories: {dict(zip(CATEGORICAL_COLS, encoder.categories_))}")

    print(f"\nLoading {WINDOW_10}...")
    w10 = load_window(WINDOW_10)
    n_raw = len(w10)

    unseen = {}
    for col, cats in zip(CATEGORICAL_COLS, encoder.categories_):
        seen_mask = w10[col].isin(cats)
        if (~seen_mask).any():
            unseen[col] = sorted(w10.loc[~seen_mask, col].unique().tolist())
    if unseen:
        print(f"WARNING: window_10 has categorical values Dense's encoder never saw "
              f"(will be all-zero encoded, handle_unknown='ignore'): {unseen}")

    n_attack = int(w10["is_attack"].sum())
    w10_benign = w10[w10["is_attack"] == 0].copy()
    n_benign = len(w10_benign)
    print(f"\n{WINDOW_10}: {n_raw} total lab-IP flows, {n_attack} attacker-IP flows excluded "
          f"(clean train set requires 100% benign, matching Dense's train invariant), "
          f"{n_benign} benign flows kept.")

    scaled = pd.DataFrame(
        scaler.transform(w10_benign[NUMERIC_COLS]),
        columns=[f"{c}_scaled" for c in NUMERIC_COLS],
        index=w10_benign.index,
    )
    encoded = pd.DataFrame(
        encoder.transform(w10_benign[CATEGORICAL_COLS]),
        columns=encoder.get_feature_names_out(CATEGORICAL_COLS),
        index=w10_benign.index,
    )

    final = pd.concat([scaled, encoded], axis=1)
    final["is_attack"] = w10_benign["is_attack"].values
    final["actual_attack_pct"] = w10_benign["actual_attack_pct"].values
    final["window_id"] = w10_benign["window_id"].values
    final["ts"] = w10_benign["ts"].values

    final.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH} ({final.shape[0]} rows, {final.shape[1]} cols)")

    print("\n=== window_10 scaled numeric features: mean/std/min/max ===")
    print(final[[f"{c}_scaled" for c in NUMERIC_COLS]].agg(["mean", "std", "min", "max"]).T)


if __name__ == "__main__":
    main()
