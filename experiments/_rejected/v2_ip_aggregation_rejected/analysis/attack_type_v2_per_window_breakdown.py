"""
Break down the v2 autoencoders' (04_phase3_models_v2/, 22/18 columns with the
4 rolling 60s source-IP features) apache_bench recall PER WINDOW, split into
low-N (window_02-05, N=21-92) and high-N (window_06-08, N=119-190) groups.

Motivation: attack_type_breakdown_v1_vs_v2_comparison.py found apache_bench
recall jumped from 0.00% to 100.00% (std=0 across all 5 seeds) after adding
the rolling features. A perfect, zero-variance result right after a previous
round where an earlier "apache_bench/slowloris AUC=1.0" finding turned out to
be an attribution artifact warrants a second look before trusting it. This
script checks whether the 100% recall is genuinely present across the full
N range, or whether it is an artifact of the test split's attack_type
composition (which windows actually contributed apache_bench flows to the
test split, and how many).

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
MODEL_DIR = PROJECT_ROOT / "04_phase3_models_v2"
RAW_DATA_DIR = Path(base.RAW_DATA_DIR)

META_COLS = ["is_attack", "actual_attack_pct", "window_id", "ts"]
CONN_STATE_COLS = ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"]
SEEDS = (0, 1, 2, 3, 4)
VARIANTS = ("full_features", "no_conn_state")
ATTACK_TYPES = ("portscan", "apache_bench", "slowloris")

LOW_N_WINDOWS = ["window_02_3pct", "window_03_5pct", "window_04_7pct", "window_05_12pct"]
HIGH_N_WINDOWS = ["window_06_15pct", "window_07_17pct", "window_08_22pct"]

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

    raw_cache = {}
    attack_test_df["attack_type"] = [
        classify_attack_type(w, t, raw_cache)
        for w, t in zip(attack_test_df["window_id"], attack_test_df["ts"])
    ]

    print("\n=== Test-split attack_type counts per window (this determines what CAN be measured) ===")
    counts = attack_test_df.groupby(["window_id", "attack_type"]).size().unstack(fill_value=0)
    print(counts.reindex(LOW_N_WINDOWS + HIGH_N_WINDOWS))

    ab_test = attack_test_df[attack_test_df["attack_type"] == "apache_bench"]
    windows_with_ab = sorted(ab_test["window_id"].unique())
    print(f"\nWindows that actually contribute apache_bench flows to the TEST split: {windows_with_ab}")
    for w in windows_with_ab:
        print(f"  {w}: n={int((ab_test['window_id'] == w).sum())}")
    missing = [w for w in LOW_N_WINDOWS + HIGH_N_WINDOWS if w not in windows_with_ab]
    if missing:
        print(
            f"  NOTE: windows {missing} contribute ZERO apache_bench flows to the test split "
            f"(their apache_bench signature groups were assigned to val by the GroupShuffleSplit, "
            f"since all flows within one apache_bench occurrence collapse into very few near-identical "
            f"signatures). Recall for apache_bench can only be measured on the windows listed above."
        )

    full_cols = [c for c in features.columns if c not in META_COLS]
    no_cs_cols = [c for c in full_cols if c not in CONN_STATE_COLS]
    cols_by_variant = {"full_features": full_cols, "no_conn_state": no_cs_cols}

    all_rows = []
    for variant in VARIANTS:
        cols = cols_by_variant[variant]
        X_val_benign = val_df.loc[val_df["is_attack"] == 0, cols].values.astype("float32")

        print(f"\n{'=' * 100}\nVariant: {variant}\n{'=' * 100}")
        for seed in SEEDS:
            model_path = MODEL_DIR / variant / f"autoencoder_seed{seed}.keras"
            model = tf.keras.models.load_model(model_path)
            threshold = float(np.percentile(reconstruction_error(model, X_val_benign), 95))

            for atype in ATTACK_TYPES:
                sub = attack_test_df[attack_test_df["attack_type"] == atype]
                for w in sorted(sub["window_id"].unique()):
                    X_w = sub.loc[sub["window_id"] == w, cols].values.astype("float32")
                    errors = reconstruction_error(model, X_w)
                    recall = 100.0 * (errors > threshold).mean()
                    all_rows.append({
                        "variant": variant, "seed": seed, "attack_type": atype,
                        "window_id": w, "n": len(X_w), "recall": recall,
                        "n_group": "low_N" if w in LOW_N_WINDOWS else "high_N",
                    })

    summary = pd.DataFrame(all_rows)

    print(f"\n{'=' * 100}\napache_bench recall per window (5-seed mean +/- std)\n{'=' * 100}")
    for variant in VARIANTS:
        print(f"\n--- variant: {variant} ---")
        v = summary[(summary.variant == variant) & (summary.attack_type == "apache_bench")]
        for w in windows_with_ab:
            sub = v[v.window_id == w]
            n = int(sub["n"].iloc[0])
            print(f"  {w} (n={n}, {sub['n_group'].iloc[0]}): recall = {sub['recall'].mean():.2f}% +/- {sub['recall'].std():.2f}%")

    print(f"\n{'=' * 100}\napache_bench recall: low-N vs high-N group (n-weighted, 5-seed mean +/- std)\n{'=' * 100}")
    for variant in VARIANTS:
        v = summary[(summary.variant == variant) & (summary.attack_type == "apache_bench")]
        for group in ("low_N", "high_N"):
            g = v[v.n_group == group]
            if g.empty:
                print(f"  {variant} / {group}: NO apache_bench flows in test split for this group -- cannot measure.")
                continue
            per_seed = g.groupby("seed").apply(
                lambda gg: 100.0 * (gg["recall"] / 100.0 * gg["n"]).sum() / gg["n"].sum(), include_groups=False
            )
            windows_in_group = sorted(g["window_id"].unique())
            print(f"  {variant} / {group} (windows: {windows_in_group}): recall = {per_seed.mean():.2f}% +/- {per_seed.std():.2f}%")

    print(f"\n{'=' * 100}\nportscan / slowloris recall per window, for context (5-seed mean +/- std)\n{'=' * 100}")
    for atype in ("portscan", "slowloris"):
        print(f"\n--- {atype} ---")
        for variant in VARIANTS:
            v = summary[(summary.variant == variant) & (summary.attack_type == atype)]
            for group in ("low_N", "high_N"):
                g = v[v.n_group == group]
                if g.empty:
                    continue
                per_seed = g.groupby("seed").apply(
                    lambda gg: 100.0 * (gg["recall"] / 100.0 * gg["n"]).sum() / gg["n"].sum(), include_groups=False
                )
                print(f"  {variant} / {group}: recall = {per_seed.mean():.2f}% +/- {per_seed.std():.2f}%")


if __name__ == "__main__":
    main()
