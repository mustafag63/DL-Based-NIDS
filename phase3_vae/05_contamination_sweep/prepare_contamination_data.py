"""
Phase 3 (VAE) - contamination sweep, ADIM 1 + 2: attack pool / fixed test set /
held-out threshold-validation benign set, and the six contaminated train sets.

Reuses phase3_vae/prepare_window10.py's scaler/encoder refit pattern (fit ONLY
on Dense's train_indices.csv, never on this experiment's own data) so every
flow here lands on the exact same feature scale as window_10_clean_train.csv
and the final VAE model. Dense's own files stay read-only.

window_09 does not exist in the raw capture backup (only window_01..08 and
window_10_0pct were ever captured) - the attack pool is built from window_02
through window_08, the full set of available attack-labelled windows.

Flow-level uniqueness key: f"{window_id}::{uid}" (Zeek's uid is unique within
a single window's conn.log, verified empirically - see manifest for hash).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, WINDOW_10,
    build_dense_conn_all, load_window, refit_dense_scaler_and_encoder,
)

HERE = Path(__file__).parent
OUT_DATA = HERE / "01_data"
OUT_TRAIN_SETS = HERE / "02_contaminated_train_sets"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_TRAIN_SETS.mkdir(parents=True, exist_ok=True)

ATTACK_WINDOWS = [
    "window_02_3pct", "window_03_5pct", "window_04_7pct", "window_05_12pct",
    "window_06_15pct", "window_07_17pct", "window_08_22pct",
]

CONTAM_LEVELS_PCT = [0, 1, 2, 4, 8, 12]
TEST_CONTAM_TARGET_PCT = 10.0

BENIGN_TRAIN_FRAC = 0.70
BENIGN_VAL_FRAC = 0.15
# benign test frac is the remainder

SEED = 42  # data-prep sampling seed only - independent of step 3's weight-init seeds


def flow_id(df: pd.DataFrame) -> pd.Series:
    return df["window_id"] + "::" + df["uid"].astype(str)


def transform(df: pd.DataFrame, scaler, encoder) -> pd.DataFrame:
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
    out = pd.concat([scaled, encoded], axis=1)
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
    feature_cols = [f"{c}_scaled" for c in NUMERIC_COLS] + list(encoder.get_feature_names_out(CATEGORICAL_COLS))
    print(f"feature_cols ({len(feature_cols)}): {feature_cols}")

    # --- attack pool (window_02..08) ---
    print(f"\nLoading attack windows: {ATTACK_WINDOWS}")
    attack_frames = [load_window(w) for w in ATTACK_WINDOWS]
    attack_all = pd.concat(attack_frames, ignore_index=True)
    attack_all_t = transform(attack_all, scaler, encoder)
    attack_flows = attack_all_t[attack_all_t["is_attack"] == 1].reset_index(drop=True)
    print(f"Total attack-labelled flows across window_02-08: {len(attack_flows)}")
    assert attack_flows["flow_id"].is_unique, "duplicate flow_id among attack flows"

    # --- benign pool (window_10, benign only - excludes its own tiny attack residue) ---
    print(f"\nLoading benign pool: {WINDOW_10}")
    w10 = load_window(WINDOW_10)
    w10_t = transform(w10, scaler, encoder)
    benign_all = w10_t[w10_t["is_attack"] == 0].reset_index(drop=True)
    n_benign_total = len(benign_all)
    print(f"window_10 benign flows: {n_benign_total} "
          f"({int((w10_t['is_attack'] == 1).sum())} attack flows excluded)")
    assert benign_all["flow_id"].is_unique, "duplicate flow_id among benign flows"

    # --- 3-way benign split: train pool / threshold-val / test ---
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

    # sanity: disjoint benign splits
    sets = [set(benign_train_pool["flow_id"]), set(benign_val["flow_id"]), set(benign_test["flow_id"])]
    for a in range(3):
        for b in range(a + 1, 3):
            assert not (sets[a] & sets[b]), "benign split overlap detected"

    # --- fixed test attack set + attack pool (disjoint) ---
    n_test_attack = int(round(len(benign_test) * TEST_CONTAM_TARGET_PCT / 100 / (1 - TEST_CONTAM_TARGET_PCT / 100)))
    attack_idx = rng.permutation(len(attack_flows))
    test_attack_idx = attack_idx[:n_test_attack]
    pool_attack_idx = attack_idx[n_test_attack:]

    test_attack_set = attack_flows.iloc[test_attack_idx].reset_index(drop=True)
    attack_pool = attack_flows.iloc[pool_attack_idx].reset_index(drop=True)
    print(f"\nattack split: test_attack_set={len(test_attack_set)} attack_pool={len(attack_pool)}")

    assert not (set(test_attack_set["flow_id"]) & set(attack_pool["flow_id"])), "attack pool/test overlap"

    # --- fixed test set ---
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

    test_set_manifest = {
        "n_total": len(test_set),
        "n_benign": len(benign_test),
        "n_attack": len(test_attack_set),
        "contamination_pct_actual": actual_test_contam_pct,
        "contamination_pct_target": TEST_CONTAM_TARGET_PCT,
        "flow_id_hash_sha256": sha256_of_ids(test_set["flow_id"]),
        "seed": SEED,
    }
    (OUT_DATA / "test_set_manifest.json").write_text(json.dumps(test_set_manifest, indent=2))

    # --- 6 contaminated train sets ---
    print("\nBuilding contaminated train sets...")
    contam_summary = []
    used_attack_ids_by_level = {}
    for level_pct in CONTAM_LEVELS_PCT:
        n_benign_lvl = len(benign_train_pool)
        if level_pct == 0:
            n_attack_lvl = 0
        else:
            n_attack_lvl = int(round(n_benign_lvl * level_pct / 100 / (1 - level_pct / 100)))
        assert n_attack_lvl <= len(attack_pool), (
            f"attack_pool too small for {level_pct}% "
            f"(need {n_attack_lvl}, have {len(attack_pool)})"
        )
        level_rng = np.random.default_rng(SEED + level_pct)
        sample_idx = level_rng.choice(len(attack_pool), size=n_attack_lvl, replace=False)
        attack_sample = attack_pool.iloc[sample_idx].reset_index(drop=True)

        # sanity: sampled attack flows never touch the fixed test attack set
        assert not (set(attack_sample["flow_id"]) & set(test_attack_set["flow_id"]))

        train_set = pd.concat([benign_train_pool, attack_sample], ignore_index=True)
        train_set = train_set.iloc[level_rng.permutation(len(train_set))].reset_index(drop=True)
        actual_pct = 100 * n_attack_lvl / len(train_set) if len(train_set) else 0.0

        out_path = OUT_TRAIN_SETS / f"train_contam_{level_pct}pct.csv"
        train_set[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(out_path, index=False)

        used_attack_ids_by_level[level_pct] = sorted(attack_sample["flow_id"])
        contam_summary.append({
            "target_pct": level_pct,
            "actual_pct": actual_pct,
            "n_benign": n_benign_lvl,
            "n_attack": n_attack_lvl,
            "n_total": len(train_set),
        })
        print(f"  {level_pct}% target -> {actual_pct:.3f}% actual "
              f"({n_benign_lvl} benign + {n_attack_lvl} attack = {len(train_set)} total) -> {out_path.name}")

    manifest = {
        "seed": SEED,
        "attack_windows_used": ATTACK_WINDOWS,
        "note_window_09": "window_09 does not exist in the raw capture backup; attack pool built from window_02-08.",
        "feature_cols": feature_cols,
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
        "contamination_levels": contam_summary,
    }
    (OUT_DATA / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # global disjointness re-check across everything that touches "test"
    assert not (set(benign_train_pool["flow_id"]) & set(benign_test["flow_id"]))
    assert not (set(benign_val["flow_id"]) & set(benign_test["flow_id"]))
    assert not (set(attack_pool["flow_id"]) & set(test_attack_set["flow_id"]))
    print("\nAll leakage sanity-checks passed (benign train/val/test disjoint, attack pool/test disjoint).")
    print(f"\nWrote: {OUT_DATA / 'manifest.json'}, {OUT_DATA / 'test_set_manifest.json'}, "
          f"{OUT_DATA / 'test_set.csv'}, {OUT_DATA / 'val_benign.csv'}, "
          f"{len(CONTAM_LEVELS_PCT)} files in {OUT_TRAIN_SETS}/")


if __name__ == "__main__":
    main()
