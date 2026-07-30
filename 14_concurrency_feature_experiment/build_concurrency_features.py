"""
Yan deney 2: pencere-bazli yogunluk/concurrency feature'lari.

13_temporal_feature_experiment/'daki tek-flow inter-arrival-time (kaynak IP
basina onceki flow'a gore) ise yaramamisti (KS=0.375, recall degismedi).
Burada farkli bir hipotez test ediliyor: bir flow'un KENDI zaman damgasinin
etrafindaki bir pencerede (+-1s / +-2s / +-5s) kac flow oldugu -- yani
concurrency/rate, tek bir onceki-flow farkindan degil, yerel yogunluktan.

Onemli fark (O7 confound'unu tekrarlamamak icin): feature ROLE hicbir yerde
sabit bir IP DEGERI (orn. "192.168.10.2") kullanmiyor. Gruplama anahtarlari
(id.orig_h, id.resp_h+id.resp_p) tamamen veri-guduml -- ayni mekanizma
herhangi bir IP dagilimiyla calisir. is_attack/ATTACKER_IP SADECE ham
conn.log'u combined feature tablosuyla hizalamayi dogrulamak icin kullanilir,
feature hesaplamasinin kendisine hic girmez.

Uc feature ailesi, her biri 3 yaricap (r in {1,2,5} saniye), window_id
sinirini asmadan (pencereler ayri capture'lar, sinir otesi diff anlamsiz):
  a) concurrency_src_r   : ayni kaynak IP'den, |ts_i - ts_j| <= r olan flow
                            sayisi (kendisi haric)
  b) concurrency_dst_r   : ayni (hedef IP, hedef port) ciftine giden, ayni
                            pencerede flow sayisi (kendisi haric)
  c) byte_ratio_var_src_r: (a)'daki ayni komsuluk kumesinde byte_ratio'nun
                            (orig_bytes/(resp_bytes+1)) varyansi (kendisi
                            dahil) -- tekduzelik olcusu (dusuk varyans =
                            apache_bench gibi stereotip tekrar)

9 ham feature -> log1p transform (sayim ve varyans feature'lari carpik) ->
StandardScaler, SADECE Dense v1 train split'i (tamamen benign) uzerinde fit.

Vektorize hesaplama: her (window_id, grup_anahtari) icin ts'e gore sirala,
np.searchsorted ile pencere sinirlarini bul, cumsum/cumsum-of-squares ile
O(n log n) toplam/varyans (O(n^2) komsu taramasi yok).

Hizalama: 13 numarali deneydeki gibi, ham Zeek conn.log'lari faz2 ile
BIREBIR ayni filtre+siralamayla okunup TUM 46495 satirda ts+is_attack
assert'i ile combined feature tablosuna hizalanir (seyrek alt kume kullanan
13'un ilk KS artefakti tekrarlanmasin diye).

Ciktilar (bu klasor icinde):
  concurrency_features_all_rows.csv : row_index + 9 ham + 9 log + 9 scaled kolon
  concurrency_features_meta.json    : scaler parametreleri, transform notu
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
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

FEATURES_ALL_WINDOWS = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv")
RESAMPLED_15 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target15.0_actual15.00_features.csv")
RESAMPLED_20 = os.path.join(NIDS_DATA_DIR, "ids-dataset-features", "by_window",
                            "window_resampled_target20.0_actual19.99_features.csv")
DENSE_TRAIN_IDX = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits",
                               "train_indices.csv")

OUT_CSV = os.path.join(HERE, "concurrency_features_all_rows.csv")
OUT_META = os.path.join(HERE, "concurrency_features_meta.json")

RADII = [1.0, 2.0, 5.0]


def load_raw_table():
    frames = []
    for w in WINDOWS:
        conn = pd.read_csv(os.path.join(RAW_ROOT, w, "zeek", "conn.log"),
                           sep="\t", comment="#", names=CONN_COLS, na_values="-")
        conn = conn[conn["id.orig_h"].isin(LAB_IPS) & conn["id.resp_h"].isin(LAB_IPS)].copy()
        conn["is_attack"] = (conn["id.orig_h"] == ATTACKER_IP).astype(int)
        conn["window_id"] = w
        conn["orig_bytes"] = conn["orig_bytes"].fillna(0)
        conn["resp_bytes"] = conn["resp_bytes"].fillna(0)
        frames.append(conn[["ts", "id.orig_h", "id.resp_h", "id.resp_p",
                            "orig_bytes", "resp_bytes", "is_attack", "window_id"]])
    return pd.concat(frames, ignore_index=True)


def load_combined_align_table():
    cols = ["ts", "is_attack", "window_id"]
    base = pd.read_csv(FEATURES_ALL_WINDOWS, usecols=cols)
    r15 = pd.read_csv(RESAMPLED_15, usecols=cols)
    r20 = pd.read_csv(RESAMPLED_20, usecols=cols)
    return pd.concat([base, r15, r20], ignore_index=True)


def windowed_stats(sub, group_cols, r, value_col=None):
    """For each row in `sub` (must be pre-sorted by row_index), compute
    within-group (grouped by group_cols, restricted to `sub`'s own window_id
    since group_cols always includes window_id upstream) count of neighbors
    with |ts_i - ts_j| <= r, and optionally mean/var of value_col over that
    neighborhood. Returns arrays aligned to sub's original row order.
    O(n log n): sort each group by ts, use searchsorted for window bounds,
    cumsum/cumsum-of-squares for O(1) range sum/sumsq per row.
    """
    n = len(sub)
    count_out = np.empty(n, dtype="int64")
    var_out = np.full(n, np.nan) if value_col else None

    for _, idx in sub.groupby(group_cols, sort=False).indices.items():
        idx = np.asarray(idx)
        order = np.argsort(sub["ts"].values[idx], kind="mergesort")
        idx_sorted = idx[order]
        ts_sorted = sub["ts"].values[idx_sorted]

        lo = np.searchsorted(ts_sorted, ts_sorted - r, side="left")
        hi = np.searchsorted(ts_sorted, ts_sorted + r, side="right")
        n_in_window = hi - lo
        count_out[idx_sorted] = n_in_window - 1  # exclude self

        if value_col:
            v = sub[value_col].values[idx_sorted].astype("float64")
            cs = np.concatenate([[0.0], np.cumsum(v)])
            css = np.concatenate([[0.0], np.cumsum(v * v)])
            s = cs[hi] - cs[lo]
            ss = css[hi] - css[lo]
            mean = s / n_in_window
            var = ss / n_in_window - mean * mean
            var_out[idx_sorted] = np.maximum(var, 0.0)  # clip fp noise

    return count_out, var_out


def main():
    raw = load_raw_table()
    combined = load_combined_align_table()
    assert len(raw) == len(combined), f"row mismatch: raw={len(raw)} combined={len(combined)}"
    ts_ok = np.allclose(raw["ts"].values, combined["ts"].values, rtol=0, atol=1e-6)
    atk_ok = (raw["is_attack"].values == combined["is_attack"].values).all()
    assert ts_ok and atk_ok, f"alignment failed: ts_ok={ts_ok} is_attack_ok={atk_ok}"
    print(f"alignment verified on full dataset: {len(raw)} rows (ts + is_attack exact match)")

    df = raw.copy()
    df["row_index"] = np.arange(len(df))
    df["byte_ratio"] = df["orig_bytes"] / (df["resp_bytes"] + 1.0)

    raw_cols = []
    for r in RADII:
        r_tag = str(int(r)) if r == int(r) else str(r)
        print(f"computing radius={r}s ...")

        src_count, byte_var = windowed_stats(
            df[["ts", "id.orig_h", "window_id", "byte_ratio", "row_index"]]
              .assign(window_id=df["window_id"]),
            ["window_id", "id.orig_h"], r, value_col="byte_ratio")
        dst_count, _ = windowed_stats(
            df[["ts", "id.resp_h", "id.resp_p", "window_id", "row_index"]],
            ["window_id", "id.resp_h", "id.resp_p"], r)

        c_src = f"concurrency_src_{r_tag}s"
        c_dst = f"concurrency_dst_{r_tag}s"
        c_var = f"byte_ratio_var_src_{r_tag}s"
        df[c_src] = src_count
        df[c_dst] = dst_count
        df[c_var] = byte_var
        raw_cols += [c_src, c_dst, c_var]

    # log1p transform: all 9 raw features are non-negative counts/variances
    log_cols = [f"{c}_log" for c in raw_cols]
    for c, lc in zip(raw_cols, log_cols):
        df[lc] = np.log1p(df[c])

    # scaler: fit ONLY on Dense v1 train split (all benign)
    train_idx = pd.read_csv(DENSE_TRAIN_IDX)
    assert (train_idx["is_attack"] == 0).all(), "dense train split must be all benign"
    train_rows = train_idx["row_index"].values
    train_mask = df["row_index"].isin(train_rows)

    scaled_cols = [f"{c}_scaled" for c in raw_cols]
    scaler_meta = {}
    for lc, sc in zip(log_cols, scaled_cols):
        mu = float(df.loc[train_mask, lc].mean())
        sigma = float(df.loc[train_mask, lc].std(ddof=0))
        sigma = sigma if sigma > 1e-12 else 1.0
        df[sc] = (df[lc] - mu) / sigma
        scaler_meta[sc] = {"mean": mu, "std": sigma, "source_col": lc}

    out_cols = ["row_index", "window_id", "ts", "is_attack"] + raw_cols + log_cols + scaled_cols
    df[out_cols].to_csv(OUT_CSV, index=False)

    meta = {
        "n_rows": len(df),
        "radii_seconds": RADII,
        "feature_families": {
            "concurrency_src_{r}s": "same source IP, |dt|<=r within window_id, count excl. self",
            "concurrency_dst_{r}s": "same (dest IP, dest port), |dt|<=r within window_id, count excl. self",
            "byte_ratio_var_src_{r}s": "variance of byte_ratio among concurrency_src's neighborhood, incl. self",
        },
        "transform": "log1p(raw)",
        "scaler": {"fit_on": "dense v1 train split (all benign)", "n_fit_rows": int(train_mask.sum()),
                   "per_feature": scaler_meta},
        "note": "no hardcoded attacker/benign IP value used in feature math; "
                "ATTACKER_IP only used to verify alignment against the combined feature table's is_attack column.",
    }
    json.dump(meta, open(OUT_META, "w"), indent=2)
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_META}")


if __name__ == "__main__":
    main()
