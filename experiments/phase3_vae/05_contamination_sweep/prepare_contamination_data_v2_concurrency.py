"""
VAE v2 data prep (Stage 2 of the concurrency_src_1s canonical rollout):
same procedure as prepare_contamination_data.py (identical SEED=42, identical
rng call order -> identical benign_train_pool/val/test and attack_pool/
test_attack_set flow_id membership as v1), extended only with the new
concurrency_src_1s_scaled column (computed via concurrency_v2.py's shared
function -- same formula, same FIXED Dense-v2 scaler as the Dense side and
as window_10's own v2 prep in prepare_window10_v2.py).

Scope: contam_0pct ONLY (this rollout stage only needs the clean-only model
used by the single/pairwise/segmented attack-type evaluations) -- the other
5 contamination levels from the original sweep are out of scope here.

Outputs go to 01_data_v2/ (new folder); the original 01_data/ (v1, 18
features) is untouched.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, WINDOW_10,
    build_dense_conn_all, load_window, refit_dense_scaler_and_encoder,
)
from concurrency_v2 import compute_concurrency_src_1s_scaled  # noqa: E402

HERE = Path(__file__).parent
OUT_DATA = HERE / "01_data_v2"
OUT_TRAIN_SETS = HERE / "02_contaminated_train_sets_v2"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_TRAIN_SETS.mkdir(parents=True, exist_ok=True)

ATTACK_WINDOWS = [
    "window_02_3pct", "window_03_5pct", "window_04_7pct", "window_05_12pct",
    "window_06_15pct", "window_07_17pct", "window_08_22pct",
]

CONTAM_LEVELS_PCT = [0]  # Stage 2 scope: clean-only model only
TEST_CONTAM_TARGET_PCT = 10.0

BENIGN_TRAIN_FRAC = 0.70
BENIGN_VAL_FRAC = 0.15

SEED = 42  # unchanged from v1 -- reproduces the exact same benign/attack split


def flow_id(df: pd.DataFrame) -> pd.Series:
    return df["window_id"] + "::" + df["uid"].astype(str)


def transform(df: pd.DataFrame, scaler, encoder) -> pd.DataFrame:
    """Same as v1's transform(), plus concurrency_src_1s_scaled computed on
    df's OWN window(s) (each window scoped independently, no cross-window
    diffing -- matches the Dense-side and window_10 v2 computations)."""
    scaled = pd.DataFrame(
        scaler.transform(df[NUMERIC_COLS]),
        columns=[f"{c}_scaled" for c in NUMERIC_COLS],
        index=df.index,
    )
    encoded = pd.DataFrame(
        encoder.transform(df[CATEGORICAL_COLS]),
        columns=encoder.get_feature_names_out(CATEGORICAL_COLS),
        index=df.index,
    )
    concurrency = compute_concurrency_src_1s_scaled(
        df.reset_index(drop=True)[["window_id", "id.orig_h", "ts"]])
    out = pd.concat([scaled, encoded], axis=1)
    out["concurrency_src_1s_scaled"] = concurrency
    out["is_attack"] = df["is_attack"].values
    out["window_id"] = df["window_id"].values
    out["ts"] = df["ts"].values
    out["flow_id"] = flow_id(df).values
    return out


def sha256_of_ids(ids) -> str:
    h = hashlib.sha256()
    for i in sorted(ids):
        h.update(i.encode())
    return h.hexdigest()


def main() -> None:
    rng = np.random.default_rng(SEED)

    print("Refitting Dense's scaler/encoder read-only (train_indices.csv only)...")
    dense_conn_all = build_dense_conn_all()
    scaler, encoder = refit_dense_scaler_and_encoder(dense_conn_all)
    feature_cols = ([f"{c}_scaled" for c in NUMERIC_COLS]
                    + list(encoder.get_feature_names_out(CATEGORICAL_COLS))
                    + ["concurrency_src_1s_scaled"])
    print(f"feature_cols ({len(feature_cols)}): {feature_cols}")

    # --- attack pool (window_02..08) -- concurrency computed per-window, same
    # rows/order as v1 so the rng-driven sampling below picks the same flows ---
    print(f"\nLoading attack windows: {ATTACK_WINDOWS}")
    attack_frames = [load_window(w) for w in ATTACK_WINDOWS]
    attack_all = pd.concat(attack_frames, ignore_index=True)
    attack_all_t = transform(attack_all, scaler, encoder)
    attack_flows = attack_all_t[attack_all_t["is_attack"] == 1].reset_index(drop=True)
    print(f"Total attack-labelled flows across window_02-08: {len(attack_flows)}")
    assert attack_flows["flow_id"].is_unique, "duplicate flow_id among attack flows"

    # --- benign pool (window_10) ---
    print(f"\nLoading benign pool: {WINDOW_10}")
    w10 = load_window(WINDOW_10)
    w10_t = transform(w10, scaler, encoder)
    benign_all = w10_t[w10_t["is_attack"] == 0].reset_index(drop=True)
    n_benign_total = len(benign_all)
    print(f"window_10 benign flows: {n_benign_total}")
    assert benign_all["flow_id"].is_unique, "duplicate flow_id among benign flows"

    # --- 3-way benign split (identical rng call to v1 -> identical membership) ---
    benign_idx = rng.permutation(n_benign_total)
    n_train = int(round(n_benign_total * BENIGN_TRAIN_FRAC))
    n_val = int(round(n_benign_total * BENIGN_VAL_FRAC))
    train_idx = benign_idx[:n_train]
    val_idx = benign_idx[n_train:n_train + n_val]
    test_idx = benign_idx[n_train + n_val:]

    benign_train_pool = benign_all.iloc[train_idx].reset_index(drop=True)
    benign_val = benign_all.iloc[val_idx].reset_index(drop=True)
    benign_test = benign_all.iloc[test_idx].reset_index(drop=True)
    print(f"\nbenign split: train_pool={len(benign_train_pool)} "
          f"val(threshold)={len(benign_val)} test={len(benign_test)}")

    sets = [set(benign_train_pool["flow_id"]), set(benign_val["flow_id"]), set(benign_test["flow_id"])]
    for a in range(3):
        for b in range(a + 1, 3):
            assert not (sets[a] & sets[b]), "benign split overlap detected"

    # --- fixed test attack set + attack pool (identical rng call to v1) ---
    n_test_attack = int(round(len(benign_test) * TEST_CONTAM_TARGET_PCT / 100 / (1 - TEST_CONTAM_TARGET_PCT / 100)))
    attack_idx = rng.permutation(len(attack_flows))
    test_attack_idx = attack_idx[:n_test_attack]
    pool_attack_idx = attack_idx[n_test_attack:]

    test_attack_set = attack_flows.iloc[test_attack_idx].reset_index(drop=True)
    attack_pool = attack_flows.iloc[pool_attack_idx].reset_index(drop=True)
    print(f"\nattack split: test_attack_set={len(test_attack_set)} attack_pool={len(attack_pool)}")
    assert not (set(test_attack_set["flow_id"]) & set(attack_pool["flow_id"]))

    test_set = pd.concat([benign_test, test_attack_set], ignore_index=True)
    test_set = test_set.iloc[rng.permutation(len(test_set))].reset_index(drop=True)
    actual_test_contam_pct = 100 * len(test_attack_set) / len(test_set)
    print(f"\nFixed test set: {len(test_set)} flows "
          f"({len(benign_test)} benign, {len(test_attack_set)} attack, "
          f"{actual_test_contam_pct:.2f}% contamination)")

    test_set[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(
        OUT_DATA / "test_set.csv", index=False)
    benign_val[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(
        OUT_DATA / "val_benign.csv", index=False)

    # --- v1 comparison: same flow_id sets? ---
    v1_manifest_path = HERE / "01_data" / "manifest.json"
    v1_check = {}
    if v1_manifest_path.exists():
        v1_manifest = json.loads(v1_manifest_path.read_text())
        v1_check = {
            "benign_train_pool_matches_v1": v1_manifest["flow_id_hashes"]["benign_train_pool"] == sha256_of_ids(benign_train_pool["flow_id"]),
            "benign_val_matches_v1": v1_manifest["flow_id_hashes"]["benign_val"] == sha256_of_ids(benign_val["flow_id"]),
            "benign_test_matches_v1": v1_manifest["flow_id_hashes"]["benign_test"] == sha256_of_ids(benign_test["flow_id"]),
            "attack_pool_matches_v1": v1_manifest["flow_id_hashes"]["attack_pool"] == sha256_of_ids(attack_pool["flow_id"]),
            "test_attack_set_matches_v1": v1_manifest["flow_id_hashes"]["test_attack_set"] == sha256_of_ids(test_attack_set["flow_id"]),
        }
        print(f"\nSame-flow-membership check vs v1: {v1_check}")
        assert all(v1_check.values()), "v2 split does not reproduce v1's flow membership -- STOP, investigate"

    # --- contam_0pct train set (clean-only, no attack) ---
    print("\nBuilding contam_0pct train set...")
    train_set = benign_train_pool.copy()
    out_path = OUT_TRAIN_SETS / "train_contam_0pct.csv"
    train_set[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(out_path, index=False)
    print(f"  0% -> {len(train_set)} total (all benign) -> {out_path.name}")

    manifest = {
        "seed": SEED,
        "attack_windows_used": ATTACK_WINDOWS,
        "feature_cols": feature_cols,
        "contamination_levels_in_scope": CONTAM_LEVELS_PCT,
        "note_scope": "Stage 2 of concurrency_src_1s rollout: contam_0pct only, "
                      "other 5 levels from the original sweep out of scope here.",
        "benign_pool_total": n_benign_total,
        "benign_train_pool_n": len(benign_train_pool),
        "benign_val_n": len(benign_val),
        "benign_test_n": len(benign_test),
        "attack_flows_total": len(attack_flows),
        "attack_pool_n": len(attack_pool),
        "test_attack_set_n": len(test_attack_set),
        "flow_id_hashes": {
            "benign_train_pool": sha256_of_ids(benign_train_pool["flow_id"]),
            "benign_val": sha256_of_ids(benign_val["flow_id"]),
            "benign_test": sha256_of_ids(benign_test["flow_id"]),
            "attack_pool": sha256_of_ids(attack_pool["flow_id"]),
            "test_attack_set": sha256_of_ids(test_attack_set["flow_id"]),
        },
        "matches_v1_flow_membership": v1_check,
    }
    (OUT_DATA / "manifest.json").write_text(json.dumps(manifest, indent=2))

    assert not (set(benign_train_pool["flow_id"]) & set(benign_test["flow_id"]))
    assert not (set(benign_val["flow_id"]) & set(benign_test["flow_id"]))
    assert not (set(attack_pool["flow_id"]) & set(test_attack_set["flow_id"]))
    print("\nAll leakage sanity-checks passed.")
    print(f"\nWrote: {OUT_DATA / 'manifest.json'}, {OUT_DATA / 'test_set.csv'}, "
          f"{OUT_DATA / 'val_benign.csv'}, {out_path}")


if __name__ == "__main__":
    main()
