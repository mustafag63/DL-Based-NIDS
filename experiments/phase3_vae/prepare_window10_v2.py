"""
Completes Stage-1 feature extraction for the VAE side: adds
concurrency_src_1s_scaled to window_10_0pct's clean benign train table.

window_10 is its own capture (never part of Dense's WINDOWS list), so the
feature must be computed fresh here -- there's no existing row_index into
features_v2_all_rows.csv for it. Uses the exact same formula as the Dense
side (05_contamination_sweep/concurrency_v2.py: per-source-IP, |dt|<=1s,
scoped to window_10 only since it's a single window_id) and the SAME FIXED
Dense-v2 scaler (mean_log=2.0864962884954803, std_log=0.6023503882972578) --
asserted in concurrency_v2.py's module-level check; if that assertion fails
this script fails too, before any VAE training happens.

Everything else (window_10 load, Dense-train-refit scaler/encoder for the
original 8 numeric + 3 categorical columns) is prepare_window10.py's
existing logic, untouched and re-imported, not reimplemented.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "05_contamination_sweep"))
from prepare_window10 import (  # noqa: E402
    NUMERIC_COLS, CATEGORICAL_COLS, WINDOW_10,
    build_dense_conn_all, load_window, refit_dense_scaler_and_encoder,
)
from concurrency_v2 import compute_concurrency_src_1s_scaled  # noqa: E402

OUT_PATH = Path(__file__).parent / "window10_clean_train_v2.csv"


def main() -> None:
    print("Refitting Dense's scaler/encoder read-only (train_indices.csv only)...")
    dense_conn_all = build_dense_conn_all()
    scaler, encoder = refit_dense_scaler_and_encoder(dense_conn_all)

    print(f"\nLoading {WINDOW_10}...")
    w10 = load_window(WINDOW_10)
    n_raw = len(w10)
    n_attack = int(w10["is_attack"].sum())
    w10_benign = w10[w10["is_attack"] == 0].copy()
    n_benign = len(w10_benign)
    print(f"{WINDOW_10}: {n_raw} total lab-IP flows, {n_attack} attacker-IP flows excluded, "
          f"{n_benign} benign flows kept.")

    print("\nComputing concurrency_src_1s on window_10's own raw conn.log "
          "(single window_id, so no cross-window scoping needed)...")
    # Computed over ALL of window_10 (benign + attack) so each flow's
    # concurrency count reflects its true neighborhood, then subset to
    # benign rows afterward -- matches how the Dense-side feature was
    # computed over the full dataset before any train/val/test split.
    w10_all_concurrency = compute_concurrency_src_1s_scaled(
        w10.reset_index(drop=True)[["window_id", "id.orig_h", "ts"]])
    w10 = w10.reset_index(drop=True)
    w10["concurrency_src_1s_scaled"] = w10_all_concurrency
    w10_benign = w10[w10["is_attack"] == 0].copy()

    scaled = pd.DataFrame(
        scaler.transform(w10_benign[NUMERIC_COLS]),
        columns=[f"{c}_scaled" for c in NUMERIC_COLS],
        index=w10_benign.index,
    )
    encoded = pd.DataFrame(
        encoder.transform(w10_benign[CATEGORICAL_COLS]),
        columns=encoder.get_feature_names_out(CATEGORICAL_COLS),
        index=w10_benign.index,
    )

    final = pd.concat([scaled, encoded], axis=1)
    final["concurrency_src_1s_scaled"] = w10_benign["concurrency_src_1s_scaled"].values
    final["is_attack"] = w10_benign["is_attack"].values
    final["actual_attack_pct"] = w10_benign["actual_attack_pct"].values
    final["window_id"] = w10_benign["window_id"].values
    final["ts"] = w10_benign["ts"].values

    final.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH} ({final.shape[0]} rows, {final.shape[1]} cols)")
    print("\n=== window_10 concurrency_src_1s_scaled: mean/std/min/max ===")
    print(final["concurrency_src_1s_scaled"].agg(["mean", "std", "min", "max"]))

    # Cross-check against the original (v1, no concurrency) window10_clean_train.csv:
    # same benign row count/order expected, since is_attack filtering is identical.
    v1_path = Path(__file__).parent / "window10_clean_train.csv"
    if v1_path.exists():
        v1 = pd.read_csv(v1_path)
        assert len(v1) == len(final), f"row count mismatch vs v1: {len(v1)} vs {len(final)}"
        assert (v1["ts"].values == final["ts"].values).all(), "ts order mismatch vs v1"
        print(f"\nCross-check vs window10_clean_train.csv (v1): {len(v1)} rows, "
              f"identical ts order -- OK.")


if __name__ == "__main__":
    main()
