"""Pilot feature extraction for window_02_3pct (IDS dataset Faz 2)."""
import json
from pathlib import Path

import pandas as pd

RAW_ROOT = Path.home() / "Desktop" / "ids-dataset-raw-backup"
WINDOW = "window_02_3pct"
ATTACKER_IP = "192.168.10.2"
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}

CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]

win_dir = RAW_ROOT / WINDOW
meta = json.loads((win_dir / "window_meta.json").read_text())
print("=== window_meta.json ===")
print(meta)

# --- conn.log ---
conn = pd.read_csv(
    win_dir / "zeek" / "conn.log",
    sep="\t", comment="#", names=CONN_COLS, na_values="-",
)
print(f"\n[conn.log] raw rows: {len(conn)}")

conn_lab = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)]
print(f"[conn.log] after lab-IP filter (drop mDNS/LLMNR/IPv6 noise): {len(conn_lab)}")

conn_lab = conn_lab.copy()
conn_lab["is_attack"] = (conn_lab["id.orig_h"] == ATTACKER_IP).astype(int)
print(f"[conn.log] attack-labeled flows (src == {ATTACKER_IP}): {conn_lab['is_attack'].sum()}")
print(f"[conn.log] benign-labeled flows: {(conn_lab['is_attack'] == 0).sum()}")

# --- dns.log (diagnostic only, not part of feature matrix yet) ---
DNS_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto",
    "trans_id", "rtt", "query", "qclass", "qclass_name", "qtype", "qtype_name",
    "rcode", "rcode_name", "AA", "TC", "RD", "RA", "Z", "answers", "TTLs",
    "rejected", "opcode", "opcode_name",
]
dns = pd.read_csv(
    win_dir / "zeek" / "dns.log",
    sep="\t", comment="#", names=DNS_COLS, na_values="-",
)
print(f"\n[dns.log] raw rows: {len(dns)}")
dns_lab = dns[dns["query"].astype(str).str.contains("techmarket.lab", na=False)]
print(f"[dns.log] after techmarket.lab filter: {len(dns_lab)}")

# --- attack_log.csv (cumulative -> filter by window start/end) ---
attack_log = pd.read_csv(win_dir / "ground_truth" / "attack_log.csv", encoding="utf-8-sig")
attack_log["start_iso"] = pd.to_datetime(attack_log["start_iso"], utc=True)
win_start = pd.to_datetime(meta["start_iso"], utc=True)
win_end = pd.to_datetime(meta["end_iso"], utc=True)
print(f"\n[attack_log.csv] raw rows (cumulative): {len(attack_log)}")
attack_log_win = attack_log[(attack_log["start_iso"] >= win_start) & (attack_log["start_iso"] <= win_end)]
print(f"[attack_log.csv] rows within window [{win_start} .. {win_end}]: {len(attack_log_win)}")
print(attack_log_win[["attack_type", "start_iso", "end_iso"]])

# --- locust_nav_log.csv (NOT cumulative, per earlier verification -> no time filter needed) ---
locust = pd.read_csv(win_dir / "ground_truth" / "locust_nav_log.csv")
print(f"\n[locust_nav_log.csv] rows (already window-scoped): {len(locust)}")

# ---------------------------------------------------------------------------
# Feature matrix (flow-based, from conn.log)
# ---------------------------------------------------------------------------
feat = conn_lab.copy()
feat["duration"] = feat["duration"].fillna(0.0)
feat["orig_bytes"] = feat["orig_bytes"].fillna(0)
feat["resp_bytes"] = feat["resp_bytes"].fillna(0)
feat["service"] = feat["service"].fillna("none")

numeric_cols = [
    "duration", "orig_bytes", "resp_bytes", "missed_bytes",
    "orig_pkts", "orig_ip_bytes", "resp_pkts", "resp_ip_bytes",
]
categorical_cols = ["proto", "service", "conn_state"]

from sklearn.preprocessing import StandardScaler, OneHotEncoder

scaler = StandardScaler()
scaled = pd.DataFrame(
    scaler.fit_transform(feat[numeric_cols]),
    columns=[f"{c}_scaled" for c in numeric_cols],
    index=feat.index,
)

ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
encoded = pd.DataFrame(
    ohe.fit_transform(feat[categorical_cols]),
    columns=ohe.get_feature_names_out(categorical_cols),
    index=feat.index,
)

final = pd.concat([scaled, encoded], axis=1)
final["is_attack"] = feat["is_attack"].values
final["actual_attack_pct"] = meta["actual_attack_pct"]
final["window_id"] = WINDOW
final["ts"] = feat["ts"].values

print("\n=== final feature matrix: shape ===")
print(final.shape)
print("\n=== final.info() ===")
final.info()
print("\n=== final.describe() ===")
print(final.describe().T)
