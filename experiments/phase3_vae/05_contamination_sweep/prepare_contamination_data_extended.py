"""
Phase 3 (VAE) - contamination sweep EXTENSION: add ~15/20/22% (all
without-replacement, "clean") contamination levels on top of the existing
0/1/2/4/8/12% sweep, without touching any of the original 01_data/ or
02_contaminated_train_sets/ files for those six levels.

Train sets for these three new levels come directly from the resampled
windows (window_resampled_15pct / window_resampled_20pct /
window_resampled_22pct_clean, built by build_synthetic_window.py /
build_window_22pct_clean.py to stand in for the Pi/Zeek capture outage) -
their whole conn.log (benign + attack flows together) IS the train set for
that level, unlike the original six levels where a fixed benign_train_pool
had attack flows injected on top of it.

window_resampled_22pct_clean (NOT the same as the earlier
window_resampled_22pct) was built with-explicit exclusion of every uid
already used by 15pct/20pct, so all three of these levels are mutually
disjoint from each other in addition to being disjoint from the fixed test
set (see build_window_22pct_clean.py's disjointness assertion and its
window_meta.json's "disjoint_from" block).

The earlier with-replacement window_resampled_{22,25,28,30}pct build (25/28/30
have no without-replacement budget left in the 3279-flow attack pool once
15/20pct's 1738 flows are excluded) is intentionally NOT included here -
its train sets/models/results were moved to exploratory_with_replacement/
because with-replacement duplication is a plausible confound for the
"contamination recovery at high %" pattern seen there (see README's
"Exploratory / with-replacement" section for the full writeup and caveats).

Leakage risk this script exists to close (test-set leakage, independent of
the disjointness-between-levels point above): build_synthetic_window.py
pools benign/attack rows from window_01..08 (excluding window_06), which
overlaps window_02-08 - the exact windows the fixed sweep test set's
test_attack_set was drawn from. load_window() stamps every row's flow_id as
"<window_id_arg>::<uid>", so for a resampled window that's
"window_resampled_15pct::<uid>" - this NEVER string-matches the original
"window_02_3pct::<uid>" flow_ids used to build the fixed test set, so the
original prepare_contamination_data.py-style flow_id disjointness assert
would silently miss this leak. The real signal is the raw Zeek `uid` value
itself (byte-for-byte copied from the source row by build_synthetic_window.py).
This script strips any "_dupN" suffix (none expected here, all three levels
are without-replacement) and checks the bare uid against every uid appearing
in the fixed test_set.csv, dropping any resampled-window row whose bare uid
collides.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, load_window, build_dense_conn_all,
    refit_dense_scaler_and_encoder,
)

HERE = Path(__file__).parent
DATA_DIR = HERE / "01_data"
TRAIN_DIR = HERE / "02_contaminated_train_sets"

RESAMPLED_WINDOWS = {
    15: "window_resampled_15pct",
    20: "window_resampled_20pct",
    22: "window_resampled_22pct_clean",
}

DUP_SUFFIX_RE = re.compile(r"_dup\d+$")


def bare_uid(uid: str) -> str:
    return DUP_SUFFIX_RE.sub("", str(uid))


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
    out["uid"] = df["uid"].values
    out["flow_id"] = flow_id(df).values
    out["bare_uid"] = df["uid"].astype(str).map(bare_uid).values
    return out


def main() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    feature_cols = manifest["feature_cols"]

    print("Refitting Dense's scaler/encoder read-only (train_indices.csv only, "
          "identical to prepare_contamination_data.py)...")
    dense_conn_all = build_dense_conn_all()
    scaler, encoder = refit_dense_scaler_and_encoder(dense_conn_all)

    test_df = pd.read_csv(DATA_DIR / "test_set.csv")
    test_uids = set(test_df["flow_id"].str.split("::").str[-1].map(bare_uid))
    test_attack_uids = set(
        test_df.loc[test_df["is_attack"] == 1, "flow_id"].str.split("::").str[-1].map(bare_uid)
    )
    print(f"\nFixed test set: {len(test_df)} flows, {len(test_uids)} unique bare uids "
          f"({len(test_attack_uids)} of them attack)")

    level_summaries = []
    for level_pct, window_id in RESAMPLED_WINDOWS.items():
        print(f"\n=== {level_pct}% target <- {window_id} ===")
        raw = load_window(window_id)
        t = transform(raw, scaler, encoder)
        n_before = len(t)
        n_attack_before = int((t["is_attack"] == 1).sum())

        leak_mask = t["bare_uid"].isin(test_uids)
        n_leak = int(leak_mask.sum())
        n_leak_attack = int((leak_mask & (t["is_attack"] == 1)).sum())
        n_leak_benign = n_leak - n_leak_attack
        if n_leak:
            leaked_uids = sorted(t.loc[leak_mask, "bare_uid"].unique())
            print(f"  LEAK CHECK: {n_leak} row(s) share a bare uid with the fixed test set "
                  f"({n_leak_attack} attack, {n_leak_benign} benign) - dropping from train "
                  f"(test set left untouched). Sample uids: {leaked_uids[:5]}")
        else:
            print(f"  LEAK CHECK: 0 rows overlap with the fixed test set's uids - clean.")

        clean = t.loc[~leak_mask].reset_index(drop=True)
        n_after = len(clean)
        n_attack_after = int((clean["is_attack"] == 1).sum())
        actual_pct_after = 100 * n_attack_after / n_after if n_after else 0.0

        assert not (set(clean["bare_uid"]) & test_uids), "post-filter leak still present"

        out_path = TRAIN_DIR / f"train_contam_{level_pct}pct.csv"
        clean[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(out_path, index=False)

        print(f"  {window_id}: n_before={n_before} (attack={n_attack_before}) -> "
              f"n_after_leak_removal={n_after} (attack={n_attack_after}), "
              f"actual contamination {actual_pct_after:.3f}% -> {out_path.name}")

        level_summaries.append({
            "target_pct": level_pct,
            "source_window": window_id,
            "n_before_leak_filter": n_before,
            "n_attack_before_leak_filter": n_attack_before,
            "n_leaked_rows_dropped": n_leak,
            "n_leaked_attack_rows_dropped": n_leak_attack,
            "n_leaked_benign_rows_dropped": n_leak_benign,
            "n_total": n_after,
            "n_attack": n_attack_after,
            "n_benign": n_after - n_attack_after,
            "actual_pct": actual_pct_after,
        })

    extended_manifest = {
        "note": (
            "Extension of manifest.json's 0/1/2/4/8/12% sweep with "
            "~15/20/22% levels, all fully without-replacement and mutually "
            "disjoint, built directly from window_resampled_15pct / "
            "window_resampled_20pct / window_resampled_22pct_clean conn.log "
            "(build_synthetic_window.py / build_window_22pct_clean.py "
            "output). Train sets for these levels are the resampled "
            "window's own benign+attack flows (after uid-based leak "
            "filtering against the fixed test set), NOT benign_train_pool + "
            "injected attack sample like the original six. The earlier "
            "with-replacement window_resampled_{22,25,28,30}pct build is "
            "deliberately excluded from this manifest - see "
            "exploratory_with_replacement/ and README.md."
        ),
        "test_set_bare_uid_count": len(test_uids),
        "levels": level_summaries,
    }
    (DATA_DIR / "manifest_extended.json").write_text(json.dumps(extended_manifest, indent=2))
    print(f"\nWrote {DATA_DIR / 'manifest_extended.json'} and "
          f"{len(RESAMPLED_WINDOWS)} files in {TRAIN_DIR}/")


if __name__ == "__main__":
    main()
