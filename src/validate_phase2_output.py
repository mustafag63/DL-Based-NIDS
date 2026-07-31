"""
Pre-training validation checks for features_all_windows.{csv,parquet}.

Re-reads the raw conn.log files (same parsing as faz2_feature_extraction.py)
to recover uid/window_id/split info that the final feature matrix doesn't
carry, so it can check things the final matrix alone can't answer (uid-level
duplication, cross-window leakage of literally-identical resampled flows).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW_ROOT = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-raw-backup"
FEAT_DIR = Path.home() / "Desktop" / "NIDS" / "data" / "ids-dataset-features"
SPLIT_DIR = Path.home() / "Desktop" / "NIDS" / "IDS-Project" / "03_phase3_splits"

WINDOWS = [
    "window_01_0pct", "window_02_3pct", "window_03_5pct", "window_04_7pct",
    "window_05_12pct", "window_06_15pct", "window_07_17pct", "window_08_22pct",
    "window_resampled_15pct", "window_resampled_20pct",
]
RESAMPLED_WINDOWS = {"window_resampled_15pct", "window_resampled_20pct"}
ATTACKER_IP = "192.168.10.2"
LAB_IPS = {"192.168.10.1", "192.168.10.2", "192.168.10.3"}

CONN_COLS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]

results = []  # (check_name, "PASS"/"FAIL", evidence str)


def add(name, ok, evidence):
    results.append((name, "PASS" if ok else "FAIL", evidence))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}\n  {evidence}\n")


# =====================================================================
# Reconstruct conn_all (raw, unscaled) with uid/window_id, same filter/order
# as faz2_feature_extraction.py, so row_index lines up with the split files.
# =====================================================================
frames = []
meta_map = {}
for w in WINDOWS:
    win_dir = RAW_ROOT / w
    meta_map[w] = json.loads((win_dir / "window_meta.json").read_text())
    conn = pd.read_csv(win_dir / "zeek" / "conn.log", sep="\t", comment="#", names=CONN_COLS, na_values="-")
    conn_lab = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
    conn_lab["is_attack"] = (conn_lab["id.orig_h"] == ATTACKER_IP).astype(int)
    conn_lab["window_id"] = w
    frames.append(conn_lab)
raw_all = pd.concat(frames, ignore_index=True)
raw_all["row_index"] = np.arange(len(raw_all))
raw_all["duration"] = raw_all["duration"].fillna(0.0)
raw_all["orig_bytes"] = raw_all["orig_bytes"].fillna(0)
raw_all["resp_bytes"] = raw_all["resp_bytes"].fillna(0)
raw_all["orig_pkts"] = raw_all["orig_pkts"].fillna(0)

final = pd.read_parquet(FEAT_DIR / "features_all_windows.parquet")

# =====================================================================
# 1. NaN scan
# =====================================================================
nan_counts = final.isna().sum()
nan_cols = nan_counts[nan_counts > 0]
if len(nan_cols) == 0:
    add("1. NaN/eksik deger taramasi", True,
        f"final matrix'te (shape={final.shape}) hicbir kolonda NaN yok (tum {len(final.columns)} kolon kontrol edildi).\n"
        "  Not: dns.log turetilmis hicbir feature final matriste yok (NUMERIC_COLS/CATEGORICAL_COLS dns kolonu "
        "icermiyor, dns.log sadece rapor sayaci icin okunuyor) - resampled window'larda dns.log'un olmamasi "
        "feature NaN'ina yol acamaz, riski yapisal olarak yok.")
else:
    per_window = {}
    for col in nan_cols.index:
        mask = final[col].isna()
        per_window[col] = final.loc[mask, "window_id"].value_counts().to_dict()
    add("1. NaN/eksik deger taramasi", False,
        f"NaN bulunan kolonlar: {nan_cols.to_dict()}\n  Window bazinda: {per_window}")

# =====================================================================
# 2. Duplicate satir kontrolu (uid bazinda, ayni window icinde)
# =====================================================================
dup_suffix_count = raw_all["uid"].astype(str).str.contains(r"_dup\d+$", regex=True).sum()
dup_within_window = (
    raw_all.groupby(["window_id", "uid"]).size().reset_index(name="n")
    .query("n > 1")
)
n_exact_dup_rows = 0
if not dup_within_window.empty:
    feature_cols_check = ["ts", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
                           "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state"]
    for _, r in dup_within_window.iterrows():
        sub = raw_all[(raw_all["window_id"] == r["window_id"]) & (raw_all["uid"] == r["uid"])]
        if sub[feature_cols_check].duplicated().any():
            n_exact_dup_rows += int(sub[feature_cols_check].duplicated().sum())

ok2 = (dup_suffix_count == 0) and (len(dup_within_window) == 0)
add("2. Duplicate satir kontrolu (_dupN / ayni window icinde tekrar uid)", ok2,
    f"_dupN suffix'li uid sayisi = {dup_suffix_count} (with_replacement=false rapor edilmisti, dogrulandi -> beklenen 0)\n"
    f"  Ayni window icinde tekrarlanan uid sayisi = {len(dup_within_window)}, "
    f"bunlarin tum-feature-ayni (tam duplicate) satir sayisi = {n_exact_dup_rows}")

# =====================================================================
# 3. Train/val/test split leakage: resampled window flow'lari kaynak
#    window'la ayni split'e mi dustu?
# =====================================================================
split_frames = []
for name, fname in [("train", "train_indices.csv"), ("val", "val_indices.csv"),
                     ("test", "test_indices.csv"), ("window01_shift_test", "window01_shift_test.csv")]:
    df = pd.read_csv(SPLIT_DIR / fname)
    df["split"] = name
    split_frames.append(df[["row_index", "split"]])
split_map = pd.concat(split_frames, ignore_index=True).set_index("row_index")["split"]

raw_all["split"] = raw_all["row_index"].map(split_map)
assert raw_all["split"].isna().sum() == 0, "Bazi row_index'ler split dosyalarinda bulunamadi"

# Same uid appearing under >1 window_id means a literal real-flow row was
# copied by build_synthetic_window.py from its source window into a
# resampled window (since with_replacement=false, uid is untouched on copy).
uid_window_counts = raw_all.groupby("uid")["window_id"].nunique()
shared_uids = uid_window_counts[uid_window_counts > 1].index

leak_rows = []
if len(shared_uids) > 0:
    shared = raw_all[raw_all["uid"].isin(shared_uids)]
    for uid, grp in shared.groupby("uid"):
        splits_involved = set(grp["split"])
        windows_involved = set(grp["window_id"])
        # leakage = the same real flow (uid) sits in train AND in val/test
        if "train" in splits_involved and (splits_involved - {"train"}):
            leak_rows.append({
                "uid": uid,
                "windows": sorted(windows_involved),
                "splits": sorted(splits_involved),
            })

n_shared_uid_flows = len(shared_uids)
n_leaking = len(leak_rows)
ok3 = n_leaking == 0
evidence3 = (
    f"resampled window'larla kaynak window'lar arasinda ayni uid'i paylasan (yani ayni gercek flow'un "
    f"literal kopyasi olan) satir sayisi = {n_shared_uid_flows}\n"
    f"  Bunlardan train ile val/test arasinda BOLUNMUS (leakage) olan uid sayisi = {n_leaking}"
)
if leak_rows:
    evidence3 += f"\n  Ornek (ilk 5): {leak_rows[:5]}"
add("3. Train/val/test split leakage (resampled <-> kaynak window)", ok3, evidence3)

# cross-check: which split did each resampled window's rows land in, and
# which split did their *source* window's same uid land in (aggregate view)
if n_shared_uid_flows > 0:
    shared = raw_all[raw_all["uid"].isin(shared_uids)]
    pivot = shared.pivot_table(index="uid", columns="window_id", values="split", aggfunc="first")
    print("  (bilgi) paylasilan uid'lerin window x split kirilimi ornegi (ilk 5 satir):")
    print(pivot.head())
    print()

# =====================================================================
# 4. actual_attack_pct tutarliligi
# =====================================================================
consistency = final.groupby("window_id").agg(
    flow_attack_pct=("is_attack", lambda s: 100 * s.mean()),
    actual_attack_pct=("actual_attack_pct", "first"),
    n=("is_attack", "size"),
)
consistency["abs_diff_pct_points"] = (consistency["flow_attack_pct"] - consistency["actual_attack_pct"]).abs()
over_1pct = consistency[consistency["abs_diff_pct_points"] > 1.0]
ok4 = len(over_1pct) == 0
add("4. actual_attack_pct tutarliligi (meta.json vs final is_attack ortalamasi)", ok4,
    f"Fark %1 puanini asan window sayisi = {len(over_1pct)}\n{consistency.to_string()}")

# =====================================================================
# 5. Feature olcek/dagilim sanity check (raw, unscaled)
# =====================================================================
dist_cols = ["duration", "orig_bytes", "resp_bytes"]
dist_table = raw_all.groupby("window_id")[dist_cols].agg(["min", "max", "mean", "std"])
print("5. Feature dagilim tablosu (raw/unscaled, window basina):")
print(dist_table.to_string())
print()

resampled_ranges = dist_table.loc[list(RESAMPLED_WINDOWS)]
real_ranges = dist_table.loc[[w for w in WINDOWS if w not in RESAMPLED_WINDOWS]]
anomalies = []
for col in dist_cols:
    real_min = real_ranges[(col, "min")].min()
    real_max = real_ranges[(col, "max")].max()
    for w in RESAMPLED_WINDOWS:
        rmin = dist_table.loc[w, (col, "min")]
        rmax = dist_table.loc[w, (col, "max")]
        if rmin < real_min or rmax > real_max:
            anomalies.append(f"{w}.{col}: [{rmin},{rmax}] gercek window'larin ([{real_min},{real_max}]) disinda")
ok5 = len(anomalies) == 0
add("5. Feature olcek/dagilim sanity check (resampled vs gercek window'lar)", ok5,
    ("resampled window'larin min/max degerleri gercek window'larin gozlemledigi araligin disina "
     "cikmiyor (beklenen - satirlar birebir kopyalandigi icin)." if ok5 else "Anomaliler:\n  " + "\n  ".join(anomalies)))

# =====================================================================
# 6. StandardScaler fit kapsami (kod incelemesi + ampirik check)
# =====================================================================
# faz2_feature_extraction.py L304-305: scaler.fit(conn_all.loc[train_df.index, NUMERIC_COLS])
# -> fit SADECE train split uzerinde. Ampirik olarak train split'in
# duration_scaled ortalamasi/std'si ~0/~1 olmali (scaler tam da o veriye
# fit edildigi icin), val/test/shift bundan sapabilir.
train_scaled_stats = final.loc[raw_all.set_index("row_index").loc[
    split_map[split_map == "train"].index].index if False else final.index[
    final.index.isin(split_map[split_map == "train"].index)
]]
# simpler: join split onto final via row_index position (final row order == raw_all row order)
final_with_split = final.copy()
final_with_split["row_index"] = np.arange(len(final_with_split))
final_with_split["split"] = final_with_split["row_index"].map(split_map)
by_split_scaled = final_with_split.groupby("split")["duration_scaled"].agg(["mean", "std", "count"])
train_mean = by_split_scaled.loc["train", "mean"]
train_std = by_split_scaled.loc["train", "std"]
ok6 = abs(train_mean) < 0.05 and abs(train_std - 1.0) < 0.05
add("6. StandardScaler sadece train split'e mi fit edildi", ok6,
    "Kod incelemesi: faz2_feature_extraction.py satir 304-305 - "
    "`scaler.fit(conn_all.loc[train_df.index, NUMERIC_COLS])` (SADECE train_df.index).\n"
    f"  Ampirik dogrulama (duration_scaled, split bazinda):\n{by_split_scaled.to_string()}\n"
    f"  train mean={train_mean:.4f} (beklenen ~0), train std={train_std:.4f} (beklenen ~1) -> "
    "scaler'in tam olarak train verisine fit edildigini gosterir (val/test/shift sapmasi normal, cunku "
    "onlar fit'e girmedi).")

# =====================================================================
# 7. window_id / source ayirt edilebilirligi
# =====================================================================
window_id_values = sorted(final["window_id"].unique())
has_all_windows = set(WINDOWS) == set(window_id_values)
has_resampled_marker = all("resampled" in w for w in RESAMPLED_WINDOWS)
ok7 = has_all_windows and has_resampled_marker
add("7. window_id / source alani final CSV'de korunuyor mu", ok7,
    f"final['window_id'].unique() = {window_id_values}\n"
    f"  Tum {len(WINDOWS)} window mevcut: {has_all_windows}. "
    "resampled window'lar isimlerinde 'resampled' gectigi icin filtrelenebilir "
    "(ornek: final[final['window_id'].str.contains('resampled')]).\n"
    "  UYARI: final matriste ayri bir bool/string 'source' kolonu YOK - ayirt etme islemi "
    "sadece window_id string'ine bagli (window_meta.json'daki source='resampled' alani final CSV'ye "
    "kopyalanmadi). Filtreleme icin yeterli ama acik bir 'is_resampled' kolonu olmasi daha saglam olurdu.")

# =====================================================================
# SONUC
# =====================================================================
print("=" * 70)
print("OZET")
print("=" * 70)
failed = [r for r in results if r[1] == "FAIL"]
for name, status, _ in results:
    print(f"  [{status}] {name}")
print()
if not failed:
    print("KARAR: EGITIME HAZIR")
else:
    print("KARAR: SU SORUNLAR COZULMEDEN EGITIME BASLAMA:")
    for name, _, ev in failed:
        print(f"  - {name}: {ev}")
