"""
Test whether apache_bench and slowloris attack flows are separable in the
existing 18-column flow-level feature set (features_all_windows.parquet, Phase 2
output), compared to portscan.

Method:
1. Load window_meta_summaries/*.json to get each window's collection
   [start_iso, end_iso].
2. Load ground_truth/attack_log.csv for each window. This file is cumulative
   (it contains every attack command ever run, not just the ones in this
   window), so it is filtered down to rows whose start_iso falls inside the
   window's own [start_iso, end_iso] range.
3. Each attack flow (is_attack == 1) in features_all_windows is labeled with
   an attack_type by matching its Zeek conn.log timestamp (`ts`, unix epoch
   seconds) against the filtered attack_log intervals for the same window_id.
4. Two separability tests are run using only the 18 existing modeling columns
   (8 scaled numeric + 10 one-hot categorical), never touching stored splits
   or models:
   - apache_bench vs slowloris (the hypothesis: should be near chance, AUC ~0.5)
   - portscan vs (apache_bench + slowloris) (control: should separate well)
   Each test repeats a stratified train/test split n=20 times with Logistic
   Regression and reports mean AUC +/- std.

This script is read-only with respect to the project: it does not modify
features_all_windows.*, splits/, or models/.
"""

import glob
import json
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIDS_ROOT = os.path.dirname(PROJECT_ROOT)

FEATURES_PATH = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.parquet"
)
WINDOW_META_DIR = os.path.join(
    PROJECT_ROOT, "01_phase1_data_collection", "window_meta_summaries"
)
RAW_DATA_DIR = os.path.join(NIDS_ROOT, "data", "ids-dataset-raw-backup")

MODEL_COLUMNS = [
    "duration_scaled",
    "orig_bytes_scaled",
    "resp_bytes_scaled",
    "orig_pkts_scaled",
    "resp_pkts_scaled",
    "bytes_per_sec_scaled",
    "pkts_per_sec_scaled",
    "byte_ratio_scaled",
    "proto_tcp",
    "proto_udp",
    "service_dns",
    "service_http",
    "service_none",
    "service_ssh",
    "conn_state_REJ",
    "conn_state_RSTO",
    "conn_state_S1",
    "conn_state_SF",
]

N_REPEATS = 20
TEST_SIZE = 0.3

# Command [start_iso, end_iso] marks when the attack *process* ran on the
# attacker host, not when the last Zeek-observed flow for that command
# closes (e.g. ab.exe reports "done" slightly before the last TCP connection
# in its burst is logged by the sensor). Empirically, 100% of is_attack
# flows fall within this many seconds of their true interval's edge, so a
# small tolerance is used for nearest-interval matching instead of strict
# containment (checked up to the 99.9th percentile gap of ~0.22s).
MATCH_TOLERANCE_SEC = 1.0


def load_window_meta():
    """Return {window_id: (start_epoch, end_epoch)} from window_meta_summaries/*.json."""
    meta = {}
    for path in sorted(glob.glob(os.path.join(WINDOW_META_DIR, "*_meta.json"))):
        with open(path) as f:
            d = json.load(f)
        start_epoch = pd.Timestamp(d["start_iso"]).timestamp()
        end_epoch = pd.Timestamp(d["end_iso"]).timestamp()
        meta[d["window_label"]] = (start_epoch, end_epoch)
    return meta


def load_attack_intervals(window_meta):
    """Return {window_id: [(attack_type, start_epoch, end_epoch), ...]}.

    attack_log.csv under each window's ground_truth/ folder is cumulative
    across all prior windows, so rows are kept only if their start_iso falls
    inside that window's own collection interval.
    """
    intervals = {}
    for window_id, (win_start, win_end) in window_meta.items():
        matches = glob.glob(
            os.path.join(RAW_DATA_DIR, f"{window_id}", "ground_truth", "attack_log.csv")
        )
        if not matches:
            intervals[window_id] = []
            continue
        df = pd.read_csv(matches[0])
        df["start_epoch"] = pd.to_datetime(df["start_iso"]).map(lambda t: t.timestamp())
        df["end_epoch"] = pd.to_datetime(df["end_iso"]).map(lambda t: t.timestamp())
        in_window = df[(df["start_epoch"] >= win_start) & (df["start_epoch"] <= win_end)]
        intervals[window_id] = list(
            zip(in_window["attack_type"], in_window["start_epoch"], in_window["end_epoch"])
        )
    return intervals


def assign_attack_type(row, intervals_by_window):
    """Match a flow's (window_id, ts) to the nearest attack interval.

    A flow is inside an interval if start <= ts <= end (gap 0). Otherwise the
    gap is the distance to the nearest edge. The closest interval is chosen
    if its gap is within MATCH_TOLERANCE_SEC, to absorb the small lag between
    an attack command finishing and its last flow being logged by the sensor.
    """
    candidates = intervals_by_window.get(row["window_id"], [])
    if not candidates:
        return "unmatched"

    best_type, best_gap = None, None
    ts = row["ts"]
    for atype, start, end in candidates:
        if start <= ts <= end:
            gap = 0.0
        elif ts < start:
            gap = start - ts
        else:
            gap = ts - end
        if best_gap is None or gap < best_gap:
            best_gap, best_type = gap, atype

    if best_gap is not None and best_gap <= MATCH_TOLERANCE_SEC:
        return best_type
    return "unmatched"


def run_separability_test(df, label_a, label_b, group_a_types, group_b_types, name):
    """Repeated stratified train/test AUC for a binary attack_type discrimination task."""
    mask_a = df["attack_type"].isin(group_a_types)
    mask_b = df["attack_type"].isin(group_b_types)
    subset = df[mask_a | mask_b].copy()
    subset["target"] = mask_a[mask_a | mask_b].astype(int).values

    X = subset[MODEL_COLUMNS].values
    y = subset["target"].values

    print(f"\n--- {name} ---")
    print(f"{label_a}: {int((y == 1).sum())} flows, {label_b}: {int((y == 0).sum())} flows")

    aucs = []
    for seed in range(N_REPEATS):
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, stratify=y, random_state=seed
        )
        clf = LogisticRegression(max_iter=1000)
        clf.fit(X_train, y_train)
        proba = clf.predict_proba(X_test)[:, 1]
        aucs.append(roc_auc_score(y_test, proba))

    aucs = np.array(aucs)
    print(f"AUC over {N_REPEATS} stratified splits: {aucs.mean():.4f} +/- {aucs.std():.4f}")
    return aucs


def main():
    print("Loading window metadata and attack_log intervals...")
    window_meta = load_window_meta()
    intervals = load_attack_intervals(window_meta)
    for window_id, ivals in intervals.items():
        print(f"  {window_id}: {len(ivals)} attack commands in-window")

    print("\nLoading features_all_windows.parquet (read-only)...")
    df = pd.read_parquet(FEATURES_PATH)

    attack_df = df[df["is_attack"] == 1].copy()
    print(f"Total attack flows (is_attack == 1): {len(attack_df)}")

    attack_df["attack_type"] = attack_df.apply(
        lambda row: assign_attack_type(row, intervals), axis=1
    )

    print("\nAttack type label distribution among attack flows:")
    print(attack_df["attack_type"].value_counts())

    labeled = attack_df[~attack_df["attack_type"].isin(["unmatched", "ambiguous"])]
    match_rate = len(labeled) / len(attack_df) if len(attack_df) else 0.0
    print(f"\nMatch rate (labeled / total attack flows): {match_rate:.2%}")

    # portscan_test is a one-off manual smoke test row in attack_log.csv, folded into portscan.
    labeled = labeled.copy()
    labeled["attack_type"] = labeled["attack_type"].replace(
        {"portscan_test": "portscan"}
    )

    hypothesis_aucs = run_separability_test(
        labeled,
        label_a="apache_bench",
        label_b="slowloris",
        group_a_types=["apache_bench"],
        group_b_types=["slowloris"],
        name="HYPOTHESIS: apache_bench vs slowloris",
    )

    control_aucs = run_separability_test(
        labeled,
        label_a="portscan",
        label_b="apache_bench+slowloris",
        group_a_types=["portscan"],
        group_b_types=["apache_bench", "slowloris"],
        name="CONTROL: portscan vs (apache_bench + slowloris)",
    )

    print("\n=== Interpretation ===")
    print(
        f"apache_bench vs slowloris:  AUC = {hypothesis_aucs.mean():.4f} +/- {hypothesis_aucs.std():.4f}"
    )
    print(
        f"portscan vs the rest:       AUC = {control_aucs.mean():.4f} +/- {control_aucs.std():.4f}"
    )
    if hypothesis_aucs.mean() < 0.65 < control_aucs.mean():
        print(
            "Hypothesis SUPPORTED: apache_bench and slowloris are close to "
            "indistinguishable (AUC near chance) in the current 18-column "
            "feature set, while portscan separates clearly using the same "
            "method and features — confirming the method is sound and the "
            "flat result for apache_bench/slowloris is a feature-set "
            "limitation, not a testing artifact."
        )
    else:
        print(
            "Hypothesis NOT clearly supported by these numbers — review the "
            "AUC values above before drawing conclusions."
        )


if __name__ == "__main__":
    main()
