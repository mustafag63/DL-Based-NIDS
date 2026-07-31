"""
Full deconfounded sweep, step 1: build the remaining V2 train sets so all 9
original contamination points exist under the K1+K2-fixed pipeline.

- Injection levels 1/2/8/12% (0% and 4% already exist from
  prepare_contamination_data_v2.py): same construction as v1 -- the fixed V2
  benign train pool (window_10, signature-grouped) + an attack sample from
  window_02-08 drawn disjointly from the V2 test attack set, sized
  n_benign * p / (100 - p). Per-level rng = default_rng(42 + level), matching
  the v1/v2 convention.
- Resampled levels (~15/20/22% targets): same construction as v1's
  prepare_contamination_data_extended.py -- the resampled window's own
  benign+attack flows ARE the train set (window_resampled_15pct /
  window_resampled_20pct / window_resampled_22pct_clean; all
  without-replacement, no new synthesis), after a bare-uid leak filter,
  here against the V2 test set (test_set_v2.csv). The uid check matters
  doubly in V2: the test set now also contains window_02-08 BENIGN rows
  (K1 mix), which the resampled windows pool from, so benign-side uid
  collisions are possible too and are dropped from train.

Outputs: ../01_data/train_contam_{1,2,8,12,15,20,22}pct_v2.csv and
full_sweep/manifest_full.json (actual contamination pct per level -- the
resampled levels' actuals become the curve's x values, as in v1).
Original v1 files untouched.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CHECK_DIR = HERE.parent
SWEEP_DIR = CHECK_DIR.parent
PHASE3_VAE_DIR = SWEEP_DIR.parent
sys.path.insert(0, str(PHASE3_VAE_DIR))
sys.path.insert(0, str(SWEEP_DIR))

from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, load_window,
    build_dense_conn_all, refit_dense_scaler_and_encoder,
)
from prepare_contamination_data_v2 import transform, ATTACK_WINDOWS  # noqa: E402

DATA_DIR = CHECK_DIR / "01_data"
SEED = 42

INJECTION_LEVELS = [1, 2, 8, 12]
RESAMPLED_WINDOWS = {
    15: "window_resampled_15pct",
    20: "window_resampled_20pct",
    22: "window_resampled_22pct_clean",
}
DUP_SUFFIX_RE = re.compile(r"_dup\d+$")


def bare_uid(uid: str) -> str:
    return DUP_SUFFIX_RE.sub("", str(uid))


def main():
    manifest_v2 = json.loads((DATA_DIR / "manifest_v2.json").read_text())
    feature_cols = manifest_v2["feature_cols"]

    test = pd.read_csv(DATA_DIR / "test_set_v2.csv")
    test_flow_ids = set(test["flow_id"])
    test_bare_uids = set(test["flow_id"].str.split("::").str[-1].map(bare_uid))
    print(f"V2 test set: {len(test)} flows, {len(test_bare_uids)} unique bare uids")

    train0 = pd.read_csv(DATA_DIR / "train_contam_0pct_v2.csv")
    assert (train0["is_attack"] == 0).all()
    n_benign = len(train0)
    print(f"V2 benign train pool (signature-grouped window_10): {n_benign} flows")

    print("\nRefitting Dense's scaler/encoder read-only...")
    dense_conn_all = build_dense_conn_all()
    scaler, encoder = refit_dense_scaler_and_encoder(dense_conn_all)

    print(f"Loading attack windows: {ATTACK_WINDOWS}")
    attack_all = pd.concat(
        [load_window(w).query("is_attack == 1") for w in ATTACK_WINDOWS], ignore_index=True)
    attack_flows = transform(attack_all, scaler, encoder).reset_index(drop=True)
    attack_pool = attack_flows[~attack_flows["flow_id"].isin(test_flow_ids)]
    attack_pool = attack_pool.sort_values("flow_id").reset_index(drop=True)  # deterministic order
    print(f"Attack pool (minus {len(attack_flows) - len(attack_pool)} V2 test attack flows): "
          f"{len(attack_pool)}")

    level_summaries = []

    # --- injection levels ---
    for level in INJECTION_LEVELS:
        n_attack = int(round(n_benign * level / 100 / (1 - level / 100)))
        assert n_attack <= len(attack_pool)
        rng = np.random.default_rng(SEED + level)
        sample = attack_pool.iloc[rng.choice(len(attack_pool), size=n_attack, replace=False)]
        assert not (set(sample["flow_id"]) & test_flow_ids)
        train_set = pd.concat([train0, sample[train0.columns]], ignore_index=True)
        train_set = train_set.iloc[rng.permutation(len(train_set))].reset_index(drop=True)
        out = DATA_DIR / f"train_contam_{level}pct_v2.csv"
        train_set.to_csv(out, index=False)
        actual = 100 * n_attack / len(train_set)
        level_summaries.append({"target_pct": level, "kind": "injection",
                                "curve_pct": level, "actual_pct": actual,
                                "n_total": len(train_set), "n_attack": n_attack})
        print(f"  injection {level}% -> {actual:.3f}% actual ({len(train_set)} rows) -> {out.name}")

    # --- resampled levels ---
    for level, window_id in RESAMPLED_WINDOWS.items():
        raw = load_window(window_id)
        t = transform(raw, scaler, encoder)
        t["bare_uid"] = t["flow_id"].str.split("::").str[-1].map(bare_uid)
        leak = t["bare_uid"].isin(test_bare_uids)
        n_leak_attack = int((leak & (t["is_attack"] == 1)).sum())
        n_leak_benign = int(leak.sum()) - n_leak_attack
        clean = t.loc[~leak].reset_index(drop=True)
        assert not (set(clean["bare_uid"]) & test_bare_uids)
        actual = 100 * clean["is_attack"].mean()
        out = DATA_DIR / f"train_contam_{level}pct_v2.csv"
        clean[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(out, index=False)
        level_summaries.append({"target_pct": level, "kind": "resampled",
                                "source_window": window_id,
                                "curve_pct": round(actual, 2), "actual_pct": actual,
                                "n_leak_dropped_attack": n_leak_attack,
                                "n_leak_dropped_benign": n_leak_benign,
                                "n_total": len(clean), "n_attack": int(clean["is_attack"].sum())})
        print(f"  resampled {level}% <- {window_id}: dropped {n_leak_attack} attack + "
              f"{n_leak_benign} benign uid-leak rows; {len(clean)} rows, "
              f"{actual:.3f}% actual -> {out.name}")

    # existing 0/4 for completeness
    for lvl, actual in ((0, 0.0), (4, next(l["actual_pct"] for l in manifest_v2["contamination_levels"]
                                           if l["target_pct"] == 4))):
        level_summaries.append({"target_pct": lvl, "kind": "injection", "curve_pct": lvl,
                                "actual_pct": actual, "pre_existing": True})

    HERE.mkdir(exist_ok=True)
    (HERE / "manifest_full.json").write_text(json.dumps({
        "seed": SEED,
        "note": "Full 9-point deconfounded sweep train sets; K1/K2/O2 conventions from "
                "prepare_contamination_data_v2.py. Resampled levels uid-leak-filtered "
                "against test_set_v2.csv (benign AND attack side).",
        "levels": sorted(level_summaries, key=lambda r: r["curve_pct"]),
    }, indent=2))
    print(f"\nWrote {HERE / 'manifest_full.json'}")


if __name__ == "__main__":
    main()
