"""
Check whether the near-perfect apache_bench recall achieved by adding
conn_count_60s / unique_dst_ports_60s (see
attack_type_breakdown_v1_vs_v2_comparison.py, 0.00% -> 100.00% recall) is a
genuine behavioral signal or an artifact of "source identity" -- i.e. whether
benign and apache_bench occupy completely non-overlapping ranges on these
raw (unscaled) features, and if so, why.

Recomputes the 4 rolling features directly from raw Zeek conn.log across all
8 windows (same logic as add_rolling_source_ip_features() in
faz2_feature_extraction.py, but kept local/unscaled here for interpretability
-- features_all_windows.csv only stores the scaled versions). attack_type
attribution uses the same signature rule validated in
attack_type_breakdown_evaluation.py.

Read-only: does not modify any project file, only reads raw conn.log.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import attack_type_separability as base  # noqa: E402

RAW_ROOT = Path(base.RAW_DATA_DIR)
WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
]
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}
ATTACKER_IP = "192.168.10.2"
CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto",
    "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]
FAILED_STATES = {"REJ", "RSTO", "S1"}


def classify_attack_type(row):
    if row["is_attack"] == 0:
        return "benign"
    if row["id.resp_p"] != 80:
        return "portscan"
    if row["conn_state"] == "SF" and row["orig_bytes"] == 80 and row["duration"] < 1.0:
        return "apache_bench"
    if row["conn_state"] in ("RSTO", "S1") and row["duration"] > 10.0:
        return "slowloris"
    return "unclassified"


def main():
    frames = []
    for w in WINDOWS:
        conn = pd.read_csv(RAW_ROOT / w / "zeek" / "conn.log", sep="\t", comment="#", names=CONN_COLS, na_values="-")
        conn_lab = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
        conn_lab["is_attack"] = (conn_lab["id.orig_h"] == ATTACKER_IP).astype(int)
        conn_lab["window_id"] = w
        conn_lab["duration"] = conn_lab["duration"].fillna(0.0)
        conn_lab["orig_bytes"] = conn_lab["orig_bytes"].fillna(0)
        frames.append(conn_lab)
    conn_all = pd.concat(frames, ignore_index=True)

    df = conn_all.sort_values(["window_id", "id.orig_h", "ts"]).copy()
    df["_dt"] = pd.to_datetime(df["ts"], unit="s")
    df["_resp_ip_code"] = pd.factorize(df["id.resp_h"])[0]
    df["_failed"] = df["conn_state"].isin(FAILED_STATES).astype(float)
    pieces = []
    for (wid, src), g in df.groupby(["window_id", "id.orig_h"], sort=False):
        gi = g.set_index("_dt")
        cc = gi["ts"].rolling("60s").count()
        up = gi["id.resp_p"].rolling("60s").apply(lambda x: np.unique(x).size, raw=True)
        ui = gi["_resp_ip_code"].rolling("60s").apply(lambda x: np.unique(x).size, raw=True)
        fr = gi["_failed"].rolling("60s").mean()
        pieces.append(pd.DataFrame({
            "conn_count_60s": cc.values, "unique_dst_ports_60s": up.values,
            "unique_dst_ips_60s": ui.values, "failed_conn_ratio_60s": fr.values,
        }, index=g.index))
    rolling = pd.concat(pieces).sort_index()
    conn_all = conn_all.join(rolling)
    conn_all["attack_type"] = conn_all.apply(classify_attack_type, axis=1)

    print("=== Pooled (all 8 windows) distribution by attack_type (raw, unscaled) ===")
    for col in ["conn_count_60s", "unique_dst_ports_60s"]:
        print(f"\n{col}:")
        print(conn_all.groupby("attack_type")[col].agg(["mean", "median", "max", "min", "count"]))

    benign = conn_all[conn_all["attack_type"] == "benign"]
    ab = conn_all[conn_all["attack_type"] == "apache_bench"]

    print("\n=== Critical overlap check ===")
    for col in ["conn_count_60s", "unique_dst_ports_60s"]:
        b_max, ab_min = benign[col].max(), ab[col].min()
        overlap = b_max >= ab_min
        print(
            f"{col}: benign max = {b_max}, apache_bench min = {ab_min} -> "
            f"{'OVERLAP EXISTS (benign max >= apache_bench min)' if overlap else 'NO OVERLAP (clean separation)'}"
        )

    print("\n=== Ports ever contacted by BENIGN traffic (across all 8 windows) ===")
    print(benign["id.resp_p"].value_counts())

    print("\n=== apache_bench: unique_dst_ports_60s per window (min/max/mean) -- checking constancy ===")
    print(ab.groupby("window_id")["unique_dst_ports_60s"].agg(["min", "max", "mean"]))

    print("\n=== apache_bench: conn_count_60s per window (min/max/mean) vs benign max, same window ===")
    for w in sorted(ab["window_id"].unique()):
        ab_w = ab[ab["window_id"] == w]["conn_count_60s"]
        ben_w = benign[benign["window_id"] == w]["conn_count_60s"]
        print(
            f"  {w}: apache_bench conn_count_60s min={ab_w.min():.0f} mean={ab_w.mean():.1f} max={ab_w.max():.0f} | "
            f"benign conn_count_60s mean={ben_w.mean():.1f} max={ben_w.max():.0f} | "
            f"apache_bench mean {'BELOW' if ab_w.mean() < ben_w.mean() else 'above'} benign mean in this window"
        )


if __name__ == "__main__":
    main()
