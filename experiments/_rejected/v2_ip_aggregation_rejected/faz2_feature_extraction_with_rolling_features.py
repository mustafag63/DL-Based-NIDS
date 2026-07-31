"""
Phase 2: Zeek conn.log -> Autoencoder feature matrix + Phase 3 train/val/test
split. Single pipeline: split MUST happen before StandardScaler is fit,
otherwise the scaler sees val/test benign flows during fit (leakage). An
earlier two-script version (fit scaler on ALL 8 windows' benign data, THEN
split train/val/test in a separate script) had exactly this bug.

Windows processed: window_01_0pct .. window_08_22pct (all 8 windows).

window_01_0pct was re-captured after a mid-window Zeek restart was found
and fixed (continuous PID monitoring + reporter.log post-hoc check added):
567 flows, no OTH state, actual_attack_pct=0.0, clean baseline. The old
broken capture (329K flows, 96.8% OTH) is archived separately and never
enters this pipeline.

Input:
  ~/Desktop/NIDS/data/ids-dataset-raw-backup/window_NN_XXpct/
    zeek/conn.log, zeek/dns.log, window_meta.json, ground_truth/attack_log.csv

Output:
  ~/Desktop/NIDS/data/ids-dataset-features/features_all_windows.csv
  ~/Desktop/NIDS/data/ids-dataset-features/features_all_windows.parquet
  ~/Desktop/NIDS/data/ids-dataset-features/feature_extraction_report.md
  03_phase3_splits/{train,val,test}_indices.csv
  03_phase3_splits/window01_shift_test.csv

Pipeline order (correct, leakage-free):
  1. conn.log -> conn_all (raw + derived features: bytes_per_sec,
     pkts_per_sec, byte_ratio). dns.log filtered to techmarket.lab
     (reporting only). attack_log.csv is cumulative, filtered by
     window_meta.json start/end.
  2. signature_id: window_id|proto|service|conn_state|round(duration,1)|
     round(orig_bytes,-1) - groups near-duplicate flows (top-5 signatures
     cover 72-97% of attack flows per window, since the same attack tool
     is re-run with the same parameters). GroupShuffleSplit on
     signature_id so no signature leaks across train/val/test.
  3. Split: window_01 (pure benign, a distribution outlier) is carved out
     separately, 50% into train / 50% into a standalone
     window01_shift_test set. Remaining benign (window_02-08): 70% train,
     15% val, 15% test (group-based). Attack flows never enter train
     (anomaly-detection standard): 50% val (threshold calibration) / 50%
     test (final eval), group-based.
  4. Multi-seed check: the split (step 2-3) is repeated for random_state
     0-4, sizes/attack-ratios/per-window counts compared; the most
     balanced seed (min variance in per-window train-fraction across
     windows) is picked as the "official" split.
  5. StandardScaler fit ONLY on the train split (which is 100% benign by
     construction) - NOT on all 8 windows' benign data. transform()
     applied to all rows (train+val+test+window01_shift_test).
  6. OneHotEncoder: still global fit on all rows (categorical vocabulary
     must cover every conn_state/service/proto seen in benign+attack) -
     this is a deliberate exception, not a leakage bug (numeric scaling
     and categorical vocabulary are treated differently on purpose).

missed_bytes dropped: constant 0 across all 8 windows, zero signal.
orig_ip_bytes/resp_ip_bytes dropped: r=0.996/0.99996 with
orig_bytes/resp_bytes, redundant.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler, OneHotEncoder

RAW_ROOT = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-raw-backup"
OUT_DIR = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features"
OUT_DIR.mkdir(exist_ok=True)
SPLIT_DIR = Path(__file__).parent / "03_phase3_splits"
SPLIT_DIR.mkdir(exist_ok=True)

WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
]

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
    "conn_count_60s", "unique_dst_ports_60s", "unique_dst_ips_60s", "failed_conn_ratio_60s",
]  # missed_bytes dropped: constant 0 across all 8 windows, zero signal
# orig_ip_bytes/resp_ip_bytes dropped: r=0.996/0.99996 with orig_bytes/resp_bytes
# - redundant, ip_bytes ~= bytes + header overhead
CATEGORICAL_COLS = ["proto", "service", "conn_state"]

# conn_state values counted as "failed" for failed_conn_ratio_60s: anything
# other than SF (clean completion). Only 4 conn_state values are ever
# observed in this dataset (SF, REJ, RSTO, S1 - see the one-hot columns
# below), so "failed" = REJ/RSTO/S1 - rejected, reset, or left half-open
# without a normal close, exactly the pattern a portscan probe or an
# aborted/DoS-style connection produces.
FAILED_CONN_STATES = {"REJ", "RSTO", "S1"}

DNS_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto",
    "trans_id", "rtt", "query", "qclass", "qclass_name", "qtype", "qtype_name",
    "rcode", "rcode_name", "AA", "TC", "RD", "RA", "Z", "answers", "TTLs",
    "rejected", "opcode", "opcode_name",
]

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15
assert abs(TRAIN_FRAC + VAL_FRAC + TEST_FRAC - 1.0) < 1e-9
CANDIDATE_SEEDS = [0, 1, 2, 3, 4]

report_lines = [
    "# Phase 2 - Feature Extraction Report\n",
    "\nAll 8 windows (window_01-08) included. window_01_0pct was re-captured "
    "after a Zeek restart bug was found and fixed; the old broken capture "
    "is archived separately and never enters this pipeline.\n",
    "\n## Filtering counts per window\n",
    "\n| window | raw conn.log | after lab-IP filter | attack flows | benign flows | raw dns.log | dns.log techmarket.lab | raw attack_log.csv | attack_log.csv in window |",
    "|---|---|---|---|---|---|---|---|---|",
]

# =====================================================================
# 1. conn_all: raw flows + derived features
# =====================================================================
all_conn_frames = []
window_meta_map = {}

for w in WINDOWS:
    win_dir = RAW_ROOT / w
    meta = json.loads((win_dir / "window_meta.json").read_text())
    window_meta_map[w] = meta

    conn = pd.read_csv(win_dir / "zeek" / "conn.log", sep="\t", comment="#", names=CONN_COLS, na_values="-")
    n_raw = len(conn)
    conn_lab = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
    n_lab = len(conn_lab)
    conn_lab["is_attack"] = (conn_lab["id.orig_h"] == ATTACKER_IP).astype(int)
    n_attack = int(conn_lab["is_attack"].sum())
    n_benign = n_lab - n_attack
    conn_lab["window_id"] = w
    conn_lab["actual_attack_pct"] = meta["actual_attack_pct"]
    all_conn_frames.append(conn_lab)

    dns = pd.read_csv(win_dir / "zeek" / "dns.log", sep="\t", comment="#", names=DNS_COLS, na_values="-")
    n_dns_raw = len(dns)
    n_dns_lab = int(dns["query"].astype(str).str.contains("techmarket.lab", na=False).sum())

    attack_log = pd.read_csv(win_dir / "ground_truth" / "attack_log.csv", encoding="utf-8-sig")
    attack_log["start_iso"] = pd.to_datetime(attack_log["start_iso"], utc=True)
    win_start = pd.to_datetime(meta["start_iso"], utc=True)
    win_end = pd.to_datetime(meta["end_iso"], utc=True)
    n_attacklog_raw = len(attack_log)
    n_attacklog_win = int(((attack_log["start_iso"] >= win_start) & (attack_log["start_iso"] <= win_end)).sum())

    report_lines.append(
        f"| {w} | {n_raw} | {n_lab} | {n_attack} | {n_benign} | {n_dns_raw} | {n_dns_lab} | {n_attacklog_raw} | {n_attacklog_win} |"
    )
    print(f"{w}: conn_raw={n_raw} conn_lab={n_lab} attack={n_attack} benign={n_benign} "
          f"actual_attack_pct={meta['actual_attack_pct']:.4f} flow_attack_ratio={100*n_attack/n_lab:.4f}%")

conn_all = pd.concat(all_conn_frames, ignore_index=True)
conn_all["duration"] = conn_all["duration"].fillna(0.0)
conn_all["orig_bytes"] = conn_all["orig_bytes"].fillna(0)
conn_all["resp_bytes"] = conn_all["resp_bytes"].fillna(0)
conn_all["orig_pkts"] = conn_all["orig_pkts"].fillna(0)
conn_all["service"] = conn_all["service"].fillna("none")

print(f"\nTotal combined flows (windows 01-08): {len(conn_all)}")

zero_duration = conn_all["duration"] == 0
print(f"\nFlows with duration == 0 (never-established, e.g. S0/OTH): {int(zero_duration.sum())}")
print(conn_all.loc[zero_duration, "conn_state"].value_counts())

conn_all["bytes_per_sec"] = 0.0
conn_all["pkts_per_sec"] = 0.0
conn_all.loc[~zero_duration, "bytes_per_sec"] = (
    conn_all.loc[~zero_duration, "orig_bytes"] / conn_all.loc[~zero_duration, "duration"]
)
conn_all.loc[~zero_duration, "pkts_per_sec"] = (
    conn_all.loc[~zero_duration, "orig_pkts"] / conn_all.loc[~zero_duration, "duration"]
)
print(f"bytes_per_sec/pkts_per_sec set to 0 for {int(zero_duration.sum())} zero-duration flows")

conn_all["byte_ratio"] = conn_all["orig_bytes"] / (conn_all["resp_bytes"] + 1)


# =====================================================================
# 1b. Rolling 60s source-IP time-window features (IP-based aggregation,
#     see context.md TODO): for each flow, looking BACKWARD 60 seconds from
#     its own ts, over all OTHER flows from the same source IP (id.orig_h)
#     WITHIN THE SAME window_id ONLY (a window boundary must never leak into
#     the rolling calculation of the next window - windows are collected
#     hours apart, so mixing them would produce meaningless jumps).
# =====================================================================
def add_rolling_source_ip_features(conn_all: pd.DataFrame) -> pd.DataFrame:
    df = conn_all.sort_values(["window_id", "id.orig_h", "ts"]).copy()
    df["_dt"] = pd.to_datetime(df["ts"], unit="s")
    df["_resp_ip_code"] = pd.factorize(df["id.resp_h"])[0]
    df["_is_failed_conn"] = df["conn_state"].isin(FAILED_CONN_STATES).astype(float)

    pieces = []
    for (window_id, src_ip), group in df.groupby(["window_id", "id.orig_h"], sort=False):
        g = group.set_index("_dt")
        conn_count = g["ts"].rolling("60s").count()
        unique_ports = g["id.resp_p"].rolling("60s").apply(lambda x: np.unique(x).size, raw=True)
        unique_ips = g["_resp_ip_code"].rolling("60s").apply(lambda x: np.unique(x).size, raw=True)
        failed_ratio = g["_is_failed_conn"].rolling("60s").mean()
        pieces.append(pd.DataFrame({
            "conn_count_60s": conn_count.values,
            "unique_dst_ports_60s": unique_ports.values,
            "unique_dst_ips_60s": unique_ips.values,
            "failed_conn_ratio_60s": failed_ratio.values,
        }, index=group.index))

    rolling_feats = pd.concat(pieces).sort_index()
    return conn_all.join(rolling_feats)


conn_all = add_rolling_source_ip_features(conn_all)
print("\n=== Rolling 60s source-IP features: benign vs attack (raw, unscaled) ===")
print(conn_all.groupby("is_attack")[
    ["conn_count_60s", "unique_dst_ports_60s", "unique_dst_ips_60s", "failed_conn_ratio_60s"]
].agg(["mean", "median"]))

conn_all["row_index"] = np.arange(len(conn_all))

conn_all["signature_key"] = (
    conn_all["window_id"] + "|" + conn_all["proto"].astype(str) + "|" +
    conn_all["service"].astype(str) + "|" + conn_all["conn_state"].astype(str) +
    "|dur=" + conn_all["duration"].round(1).astype(str) +
    "|obytes=" + (10 * (conn_all["orig_bytes"] // 10)).astype(int).astype(str)
)
conn_all["signature_id"] = pd.factorize(conn_all["signature_key"])[0]
print(f"\nTotal unique signature_id: {conn_all['signature_id'].nunique()} (total flows: {len(conn_all)})")


# =====================================================================
# 2. split_once(): signature-based GroupShuffleSplit, for a single seed
# =====================================================================
def split_once(conn_all: pd.DataFrame, seed: int):
    w01_mask = conn_all["window_id"] == "window_01_0pct"
    w01 = conn_all[w01_mask]
    assert (w01["is_attack"] == 0).all(), "window_01 must not contain attack flows"

    gss_w01 = GroupShuffleSplit(n_splits=1, train_size=0.5, random_state=seed)
    w01_tr_idx, w01_shift_idx = next(gss_w01.split(w01, groups=w01["signature_id"]))
    w01_train, w01_shift = w01.iloc[w01_tr_idx], w01.iloc[w01_shift_idx]

    rest = conn_all[~w01_mask]
    benign_rest = rest[rest["is_attack"] == 0]
    attack_rest = rest[rest["is_attack"] == 1]

    overlap = set(benign_rest["signature_id"]) & set(attack_rest["signature_id"])
    if overlap:
        attack_rest = attack_rest[~attack_rest["signature_id"].isin(overlap)]

    gss1 = GroupShuffleSplit(n_splits=1, train_size=TRAIN_FRAC, random_state=seed)
    tr_idx, rem_idx = next(gss1.split(benign_rest, groups=benign_rest["signature_id"]))
    benign_train, benign_rem = benign_rest.iloc[tr_idx], benign_rest.iloc[rem_idx]

    gss2 = GroupShuffleSplit(n_splits=1, train_size=0.5, random_state=seed)
    val_idx, test_idx = next(gss2.split(benign_rem, groups=benign_rem["signature_id"]))
    benign_val, benign_test = benign_rem.iloc[val_idx], benign_rem.iloc[test_idx]

    gss3 = GroupShuffleSplit(n_splits=1, train_size=0.5, random_state=seed)
    aval_idx, atest_idx = next(gss3.split(attack_rest, groups=attack_rest["signature_id"]))
    attack_val, attack_test = attack_rest.iloc[aval_idx], attack_rest.iloc[atest_idx]

    train_df = pd.concat([benign_train, w01_train], ignore_index=False)
    val_df = pd.concat([benign_val, attack_val], ignore_index=False)
    test_df = pd.concat([benign_test, attack_test], ignore_index=False)
    shift_df = w01_shift

    sets = {"train": set(train_df["signature_id"]), "val": set(val_df["signature_id"]),
            "test": set(test_df["signature_id"]), "shift_test": set(shift_df["signature_id"])}
    names = list(sets.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            inter = sets[names[i]] & sets[names[j]]
            assert not inter, f"LEAKAGE (seed={seed}): {len(inter)} shared signature_id between {names[i]}/{names[j]}"

    return {"train": train_df, "val": val_df, "test": test_df, "window01_shift_test": shift_df}


# =====================================================================
# 3. Multi-seed variance test - the seed with the most balanced
#    per-window distribution is picked as the "official" split
# =====================================================================
print("\n" + "=" * 70)
print("MULTI-SEED VARIANCE TEST (seed=0..4)")
print("=" * 70)

seed_stats = []
seed_splits = {}
for seed in CANDIDATE_SEEDS:
    splits = split_once(conn_all, seed)
    seed_splits[seed] = splits
    row = {"seed": seed}
    for name, df in splits.items():
        row[f"{name}_n"] = len(df)
        row[f"{name}_attack_pct"] = 100 * (df["is_attack"] == 1).mean()
    # balance score: sum of squared deviations of each window's train
    # fraction from the global train fraction (smaller = more balanced)
    win_train_frac = []
    global_train_frac = len(splits["train"]) / len(conn_all)
    for w in WINDOWS:
        win_total = (conn_all["window_id"] == w).sum()
        win_train = (splits["train"]["window_id"] == w).sum()
        win_train_frac.append(win_train / win_total if win_total else 0)
    balance_score = float(np.sum((np.array(win_train_frac) - global_train_frac) ** 2))
    row["balance_score"] = balance_score
    seed_stats.append(row)

seed_stats_df = pd.DataFrame(seed_stats).set_index("seed")
print(seed_stats_df.to_string())

print("\n-- min/max/std across seeds --")
summary = seed_stats_df.agg(["min", "max", "std"])
print(summary.to_string())

OFFICIAL_SEED = int(seed_stats_df["balance_score"].idxmin())
print(f"\nOfficial seed selected (most balanced per-window distribution, min balance_score): {OFFICIAL_SEED}")

splits = seed_splits[OFFICIAL_SEED]
train_df, val_df, test_df, shift_df = splits["train"], splits["val"], splits["test"], splits["window01_shift_test"]

# =====================================================================
# 4. Per-window representation check
# =====================================================================
print("\n" + "=" * 70)
print(f"WINDOW x SPLIT BREAKDOWN (seed={OFFICIAL_SEED})")
print("=" * 70)
conn_all["split"] = "UNASSIGNED"
conn_all.loc[train_df.index, "split"] = "train"
conn_all.loc[val_df.index, "split"] = "val"
conn_all.loc[test_df.index, "split"] = "test"
conn_all.loc[shift_df.index, "split"] = "window01_shift_test"
assert (conn_all["split"] != "UNASSIGNED").all(), "Found unassigned rows!"

window_split_table = conn_all.groupby(["window_id", "split", "is_attack"]).size().unstack(fill_value=0)
print(window_split_table.reindex(WINDOWS, level=0))

# =====================================================================
# 5. StandardScaler: fit ONLY on the train split (leakage-free)
# =====================================================================
scaler = StandardScaler()
scaler.fit(conn_all.loc[train_df.index, NUMERIC_COLS])
scaled = pd.DataFrame(
    scaler.transform(conn_all[NUMERIC_COLS]),
    columns=[f"{c}_scaled" for c in NUMERIC_COLS],
    index=conn_all.index,
)

# OneHotEncoder: global fit (categorical vocabulary, deliberate - not a leak)
ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
encoded = pd.DataFrame(
    ohe.fit_transform(conn_all[CATEGORICAL_COLS]),
    columns=ohe.get_feature_names_out(CATEGORICAL_COLS),
    index=conn_all.index,
)

final = pd.concat([scaled, encoded], axis=1)
final["is_attack"] = conn_all["is_attack"].values
final["actual_attack_pct"] = conn_all["actual_attack_pct"].values
final["window_id"] = conn_all["window_id"].values
final["ts"] = conn_all["ts"].values

out_csv = OUT_DIR / "features_all_windows.csv"
out_parquet = OUT_DIR / "features_all_windows.parquet"
final.to_csv(out_csv, index=False)
final.to_parquet(out_parquet, index=False)
print(f"\nSaved: {out_csv}")
print(f"Saved: {out_parquet}")

print("\n=== final.shape ===")
print(final.shape)
print("\n=== final.describe() (numeric scaled cols) ===")
print(final[[c for c in final.columns if c.endswith("_scaled")]].describe().T)

print("\n=== duration_scaled mean/std, by split (leakage-free scaler check) ===")
print(final.assign(split=conn_all["split"].values).groupby("split")["duration_scaled"].agg(["mean", "std", "count"]))

print("\n=== is_attack ratio per window vs actual_attack_pct ===")
check = final.groupby("window_id").agg(
    flow_attack_pct=("is_attack", lambda s: 100 * s.mean()),
    actual_attack_pct=("actual_attack_pct", "first"),
    n_flows=("is_attack", "size"),
)
print(check)

print("\n=== bytes_per_sec / pkts_per_sec / byte_ratio: is_attack=0 vs is_attack=1 (raw, unscaled) ===")
raw_compare = conn_all.groupby("is_attack")[["bytes_per_sec", "pkts_per_sec", "byte_ratio"]].agg(["mean", "std", "median"])
print(raw_compare)

report_lines.append("\n## Flow-attack ratio vs actual_attack_pct (validation)\n")
report_lines.append(check.to_markdown())
report_lines.append(f"\n\n## Final feature matrix\n\nShape: {final.shape}\n\nSaved files:\n- `{out_csv}`\n- `{out_parquet}`\n")
report_lines.append(
    "\n## Features used\n\n"
    f"Numeric (StandardScaler, **fit only on the train split - leakage-free**, transform applied to all rows): {NUMERIC_COLS}\n\n"
    f"Categorical (OneHotEncoder, global fit): {CATEGORICAL_COLS}\n\n"
    "`missed_bytes` dropped: constant 0 across all 8 windows (zero variance, no signal).\n\n"
    "`orig_ip_bytes`/`resp_ip_bytes` dropped: r=0.996/0.99996 with orig_bytes/resp_bytes.\n\n"
    "`bytes_per_sec`, `pkts_per_sec`: set to 0 for flows with duration==0 (mostly S0/OTH, "
    f"never-established connections, {int(zero_duration.sum())} rows total) - no division by zero.\n\n"
    "`byte_ratio` = orig_bytes/(resp_bytes+1): expected to help distinguish Slowloris-style "
    "'send little data, keep the connection open' attacks.\n\n"
    f"Train/val/test split done with signature-based GroupShuffleSplit (official seed={OFFICIAL_SEED}), "
    "see the `03_phase3_splits/` folder.\n"
)
report_lines.append("\n## bytes_per_sec / pkts_per_sec / byte_ratio: benign vs attack (raw, unscaled)\n")
report_lines.append(raw_compare.to_markdown())

(OUT_DIR / "feature_extraction_report.md").write_text("\n".join(report_lines))
print(f"\nSaved report: {OUT_DIR / 'feature_extraction_report.md'}")

# --- by_window/: same post-split fit output, filtered per window ---
by_window_dir = OUT_DIR / "by_window"
by_window_dir.mkdir(exist_ok=True)
for old_file in by_window_dir.glob("*_features.csv"):
    old_file.unlink()

total_by_window = 0
for w in WINDOWS:
    meta = window_meta_map[w]
    target = meta["target_pct"]
    actual = meta["actual_attack_pct"]
    num = w.split("_")[1]
    out_name = f"window_{num}_target{target}_actual{actual:.2f}_features.csv"
    sub = final[final["window_id"] == w]
    sub.to_csv(by_window_dir / out_name, index=False)
    total_by_window += len(sub)
    print(f"by_window: {w} -> {out_name} shape={sub.shape}")

print(f"\nby_window total rows: {total_by_window} (final: {len(final)}, matches: {total_by_window == len(final)})")

# =====================================================================
# 6. Save split files (official seed)
# =====================================================================
cols_out = ["row_index", "window_id", "is_attack", "signature_id", "ts"]
for name, df, fname in [
    ("train", train_df, "train_indices.csv"),
    ("val", val_df, "val_indices.csv"),
    ("test", test_df, "test_indices.csv"),
    ("window01_shift_test", shift_df, "window01_shift_test.csv"),
]:
    out_path = SPLIT_DIR / fname
    df[cols_out].sort_values("row_index").to_csv(out_path, index=False)
    print(f"Saved: {out_path} ({len(df)} rows)")

print("\n" + "=" * 70)
print("SPLIT SUMMARY REPORT (official seed)")
print("=" * 70)
total = len(conn_all)
for name, df in splits.items():
    n = len(df)
    n_benign = int((df["is_attack"] == 0).sum())
    n_attack = int((df["is_attack"] == 1).sum())
    n_sig_set = df["signature_id"].nunique()
    print(f"{name:22s}: n={n:6d} ({100*n/total:5.2f}% of total) | benign={n_benign:6d} "
          f"attack={n_attack:5d} | unique_signatures={n_sig_set}")
