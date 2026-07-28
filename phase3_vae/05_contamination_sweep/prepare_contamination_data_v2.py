"""
Contamination-sweep data prep V2 -- deconfounded verification arm for audit
findings K1 + K2 (11_fable_review/independent_audit.md). Derivative copy of
prepare_contamination_data.py; the original file and its 01_data/ outputs are
NOT touched. All V2 outputs go to 11_deconfounded_check/01_data/.

K2 fix (signature grouping): window_10's 4356 benign flows are split
70/15/15 with GroupShuffleSplit(groups=signature_id) -- the exact signature
formula from faz2_feature_extraction.py
(window_id|proto|service|conn_state|dur=round(duration,1)|obytes=10*(orig_bytes//10))
-- instead of v1's flat rng.permutation. Near-duplicate flows (same tool,
same parameters) can no longer straddle train/val/test.

K1 fix (mixed-benign test set): v1's test benign came ONLY from window_10,
so "benign vs attack" was aliased with "window_10 capture vs window_02-08
captures". V2's test benign is ~70% window_10 (its own held-out group-split
share) + ~30% window_02-08 benign flows, the 30% distributed in EQUAL shares
across the 7 windows -- deliberately not proportional to window size, so the
high-FPR windows found in the O6 analysis (window_06/07) cannot dominate the
mix and create a new composition artifact. The window_02-08 benign flows are
used NOWHERE else in the VAE pipeline (train and val benign stay pure
window_10, so threshold calibration is unchanged in kind); they only enter
this test set.

Train sets built: contamination 0% (clean-only) and 4% (small contaminated
point, for the "is clean still best?" check). Attack pool logic is v1's:
all window_02-08 attack flows, test-attack sample drawn first (10% target
contamination of the final mixed test set), train-contamination samples
drawn from the disjoint remainder.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).parent.parent))
from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, WINDOW_10,
    build_dense_conn_all, load_window, refit_dense_scaler_and_encoder,
)

HERE = Path(__file__).parent
OUT_ROOT = HERE / "11_deconfounded_check"
OUT_DATA = OUT_ROOT / "01_data"
OUT_DATA.mkdir(parents=True, exist_ok=True)

ATTACK_WINDOWS = [
    "window_02_3pct", "window_03_5pct", "window_04_7pct", "window_05_12pct",
    "window_06_15pct", "window_07_17pct", "window_08_22pct",
]

CONTAM_LEVELS_PCT = [0, 4]
TEST_CONTAM_TARGET_PCT = 10.0

BENIGN_TRAIN_FRAC = 0.70   # group-based, so realized fractions are approximate
MIXED_BENIGN_W10_FRAC = 0.70  # test benign: ~70% window_10, ~30% window_02-08

SEED = 42  # data-prep seed only (sampling + GroupShuffleSplit random_state)


def flow_id(df: pd.DataFrame) -> pd.Series:
    return df["window_id"] + "::" + df["uid"].astype(str)


def signature_id(df: pd.DataFrame) -> pd.Series:
    """Verbatim signature formula from faz2_feature_extraction.py (applied to
    window_10 rows here; window_id prefix kept for formula parity even though
    all rows share it)."""
    key = (
        df["window_id"] + "|" + df["proto"].astype(str) + "|" +
        df["service"].astype(str) + "|" + df["conn_state"].astype(str) +
        "|dur=" + df["duration"].round(1).astype(str) +
        "|obytes=" + (10 * (df["orig_bytes"] // 10)).astype(int).astype(str)
    )
    return pd.Series(pd.factorize(key)[0], index=df.index)


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

    # ------------------------------------------------------------------
    # window_10 benign: K2 -- signature-grouped 70/15/15 split
    # ------------------------------------------------------------------
    print(f"\nLoading benign pool: {WINDOW_10}")
    w10_raw = load_window(WINDOW_10)
    w10_benign_raw = w10_raw[w10_raw["is_attack"] == 0].copy()
    w10_benign_raw["signature_id"] = signature_id(w10_benign_raw)
    n_sigs = w10_benign_raw["signature_id"].nunique()
    print(f"window_10 benign: {len(w10_benign_raw)} flows, {n_sigs} unique signatures")

    gss1 = GroupShuffleSplit(n_splits=1, train_size=BENIGN_TRAIN_FRAC, random_state=SEED)
    tr_idx, rem_idx = next(gss1.split(w10_benign_raw, groups=w10_benign_raw["signature_id"]))
    w10_train_raw = w10_benign_raw.iloc[tr_idx]
    w10_rem_raw = w10_benign_raw.iloc[rem_idx]
    gss2 = GroupShuffleSplit(n_splits=1, train_size=0.5, random_state=SEED)
    val_idx, test_idx = next(gss2.split(w10_rem_raw, groups=w10_rem_raw["signature_id"]))
    w10_val_raw, w10_test_raw = w10_rem_raw.iloc[val_idx], w10_rem_raw.iloc[test_idx]

    sig_sets = {
        "train": set(w10_train_raw["signature_id"]),
        "val": set(w10_val_raw["signature_id"]),
        "test": set(w10_test_raw["signature_id"]),
    }
    names = list(sig_sets)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            inter = sig_sets[names[i]] & sig_sets[names[j]]
            assert not inter, f"signature leakage between {names[i]}/{names[j]}: {len(inter)} shared"
    print(f"K2 split (group-based): train={len(w10_train_raw)} val={len(w10_val_raw)} "
          f"test_w10={len(w10_test_raw)} (realized fracs "
          f"{len(w10_train_raw)/len(w10_benign_raw):.3f}/{len(w10_val_raw)/len(w10_benign_raw):.3f}/"
          f"{len(w10_test_raw)/len(w10_benign_raw):.3f}); signature sets pairwise disjoint.")

    benign_train_pool = transform(w10_train_raw, scaler, encoder)
    benign_val = transform(w10_val_raw, scaler, encoder)
    benign_test_w10 = transform(w10_test_raw, scaler, encoder)
    for part in (benign_train_pool, benign_val, benign_test_w10):
        part.reset_index(drop=True, inplace=True)

    # ------------------------------------------------------------------
    # window_02-08: attack pool + K1 mixed-benign sample
    # ------------------------------------------------------------------
    print(f"\nLoading attack windows: {ATTACK_WINDOWS}")
    frames_raw = {w: load_window(w) for w in ATTACK_WINDOWS}
    attack_all = pd.concat([f[f["is_attack"] == 1] for f in frames_raw.values()], ignore_index=True)
    attack_flows = transform(attack_all, scaler, encoder).reset_index(drop=True)
    assert attack_flows["flow_id"].is_unique
    print(f"Attack pool candidates (window_02-08): {len(attack_flows)} flows")

    # K1: equal-share benign sample across the 7 windows, sized so the final
    # test benign is ~70% window_10 / ~30% window_02-08.
    n_w10_test = len(benign_test_w10)
    n_0208_total = int(round(n_w10_test * (1 - MIXED_BENIGN_W10_FRAC) / MIXED_BENIGN_W10_FRAC))
    base, extra = divmod(n_0208_total, len(ATTACK_WINDOWS))
    per_window_n = {w: base + (1 if i < extra else 0) for i, w in enumerate(ATTACK_WINDOWS)}

    mixed_parts = []
    for w in ATTACK_WINDOWS:
        wb_raw = frames_raw[w][frames_raw[w]["is_attack"] == 0]
        n_take = per_window_n[w]
        assert n_take <= len(wb_raw), f"{w} has only {len(wb_raw)} benign flows, need {n_take}"
        take_idx = rng.choice(len(wb_raw), size=n_take, replace=False)
        mixed_parts.append(transform(wb_raw.iloc[take_idx], scaler, encoder))
    benign_test_0208 = pd.concat(mixed_parts, ignore_index=True)
    print(f"K1 mixed-benign sample: {len(benign_test_0208)} window_02-08 benign flows, "
          f"equal shares: { {w: per_window_n[w] for w in ATTACK_WINDOWS} }")

    benign_test_w10["benign_source"] = "window_10"
    benign_test_0208["benign_source"] = "window_02_08"
    benign_test = pd.concat([benign_test_w10, benign_test_0208], ignore_index=True)
    w10_share = (benign_test["benign_source"] == "window_10").mean()
    print(f"Final test benign: {len(benign_test)} flows ({100*w10_share:.1f}% window_10, "
          f"{100*(1-w10_share):.1f}% window_02-08)")

    # ------------------------------------------------------------------
    # test attack sample (10% target of final test set) + train contamination
    # ------------------------------------------------------------------
    n_test_attack = int(round(len(benign_test) * TEST_CONTAM_TARGET_PCT / 100 / (1 - TEST_CONTAM_TARGET_PCT / 100)))
    attack_idx = rng.permutation(len(attack_flows))
    test_attack_set = attack_flows.iloc[attack_idx[:n_test_attack]].reset_index(drop=True)
    attack_pool = attack_flows.iloc[attack_idx[n_test_attack:]].reset_index(drop=True)
    test_attack_set["benign_source"] = ""  # attack rows: column present, empty

    test_set = pd.concat([benign_test, test_attack_set], ignore_index=True)
    test_set = test_set.iloc[rng.permutation(len(test_set))].reset_index(drop=True)
    actual_contam = 100 * len(test_attack_set) / len(test_set)
    print(f"\nFixed V2 test set: {len(test_set)} flows ({len(benign_test)} benign, "
          f"{len(test_attack_set)} attack, {actual_contam:.2f}% contamination)")

    out_cols = ["flow_id", "window_id", "benign_source", "ts", "is_attack"] + feature_cols
    test_set[out_cols].to_csv(OUT_DATA / "test_set_v2.csv", index=False)
    benign_val[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(
        OUT_DATA / "val_benign_v2.csv", index=False)

    contam_summary = []
    for level_pct in CONTAM_LEVELS_PCT:
        n_benign_lvl = len(benign_train_pool)
        n_attack_lvl = 0 if level_pct == 0 else int(round(n_benign_lvl * level_pct / 100 / (1 - level_pct / 100)))
        assert n_attack_lvl <= len(attack_pool)
        level_rng = np.random.default_rng(SEED + level_pct)
        sample = attack_pool.iloc[level_rng.choice(len(attack_pool), size=n_attack_lvl, replace=False)] \
            if n_attack_lvl else attack_pool.iloc[[]]
        assert not (set(sample["flow_id"]) & set(test_attack_set["flow_id"]))
        train_set = pd.concat([benign_train_pool, sample], ignore_index=True)
        train_set = train_set.iloc[level_rng.permutation(len(train_set))].reset_index(drop=True)
        out_path = OUT_DATA / f"train_contam_{level_pct}pct_v2.csv"
        train_set[["flow_id", "window_id", "ts", "is_attack"] + feature_cols].to_csv(out_path, index=False)
        actual_pct = 100 * n_attack_lvl / len(train_set) if len(train_set) else 0.0
        contam_summary.append({"target_pct": level_pct, "actual_pct": actual_pct,
                               "n_benign": n_benign_lvl, "n_attack": n_attack_lvl, "n_total": len(train_set)})
        print(f"  train {level_pct}% -> {actual_pct:.3f}% actual ({len(train_set)} rows) -> {out_path.name}")

    # global disjointness: every benign/attack piece that must not overlap
    pieces = {
        "benign_train_pool": set(benign_train_pool["flow_id"]),
        "benign_val": set(benign_val["flow_id"]),
        "benign_test_w10": set(benign_test_w10["flow_id"]),
        "benign_test_0208": set(benign_test_0208["flow_id"]),
        "test_attack_set": set(test_attack_set["flow_id"]),
        "attack_pool": set(attack_pool["flow_id"]),
    }
    keys = list(pieces)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            assert not (pieces[keys[i]] & pieces[keys[j]]), f"overlap {keys[i]}/{keys[j]}"
    print("All disjointness checks passed.")

    manifest = {
        "seed": SEED,
        "k2_fix": "window_10 benign split via GroupShuffleSplit(groups=signature_id), faz2 formula",
        "k1_fix": f"test benign = {100*w10_share:.1f}% window_10 + {100*(1-w10_share):.1f}% window_02-08, "
                  "equal per-window shares (guards against window_06/07 over-representation)",
        "feature_cols": feature_cols,
        "n_w10_benign": len(w10_benign_raw),
        "n_signatures": int(n_sigs),
        "split_sizes": {"train_pool": len(benign_train_pool), "val": len(benign_val),
                        "test_benign_w10": len(benign_test_w10), "test_benign_0208": len(benign_test_0208)},
        "per_window_0208_sample": per_window_n,
        "test_set": {"n_total": len(test_set), "n_benign": len(benign_test),
                     "n_attack": len(test_attack_set), "contamination_pct_actual": actual_contam},
        "contamination_levels": contam_summary,
        "flow_id_hashes": {k: sha256_of_ids(v) for k, v in pieces.items()},
    }
    (OUT_DATA / "manifest_v2.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {OUT_DATA / 'manifest_v2.json'} + test_set_v2.csv + val_benign_v2.csv + "
          f"{len(CONTAM_LEVELS_PCT)} train files.")


if __name__ == "__main__":
    main()
