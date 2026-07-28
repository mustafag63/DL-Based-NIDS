"""
Attach an attack_type column (portscan / apache_bench / slowloris) to every
attack row in 03_phase3_splits/test_indices.csv, without touching that file
or any other pipeline output.

Reuses load_window_meta() and load_attack_intervals() from
analysis/attack_type_separability.py verbatim (same window_meta_summaries +
ground_truth/attack_log.csv join, same cumulative-log filtering per window).

One deviation from that module's assign_attack_type(), by design (confirmed
against the data before writing this): test_indices.csv includes rows from
window_resampled_15pct/20pct, which are built by build_synthetic_window.py by
copying real flows byte-for-byte from windows 02-08, including their original
`ts`, into a window_id that has no ground_truth/attack_log.csv of its own.
Matching strictly within the row's own window_id (as the base module does)
would leave every one of those flows "unmatched" (~31% of the test set's
attack flows). Since the 8 real windows' capture intervals never overlap in
time, matching is instead done GLOBALLY: all real windows' attack intervals
are flattened into one list and each flow's `ts` is matched against that
whole list regardless of which window_id the row currently carries. For rows
that do belong to one of the 8 real windows this is equivalent to the
original per-window matching (there is nothing else nearby in time for it to
be confused with); it additionally recovers resampled-window rows correctly.

portscan_test (a one-off manual smoke-test command in attack_log.csv) is
folded into portscan, as in attack_type_separability.py.

Read-only with respect to the rest of the project: only writes
06_attack_type_analysis/test_with_attack_type.csv.
"""
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "analysis"))
import attack_type_separability as base  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_INDICES_PATH = os.path.join(PROJECT_ROOT, "03_phase3_splits", "test_indices.csv")
OUT_PATH = os.path.join(HERE, "test_with_attack_type.csv")

MATCH_TOLERANCE_SEC = base.MATCH_TOLERANCE_SEC


def flatten_intervals(intervals_by_window):
    """All (attack_type, start_epoch, end_epoch) tuples from every real window,
    pooled into one list, dropping the window_id key."""
    flat = []
    for ivals in intervals_by_window.values():
        flat.extend(ivals)
    return flat


def assign_attack_type_global(ts, flat_intervals):
    """Same containment-then-nearest-edge-within-tolerance logic as
    attack_type_separability.assign_attack_type, but matched against ts alone
    (no window_id scoping) so resampled-window rows (which keep their source
    flow's original ts under a relabeled window_id) still resolve correctly."""
    if not flat_intervals:
        return "unmatched"

    best_type, best_gap = None, None
    for atype, start, end in flat_intervals:
        if start <= ts <= end:
            gap = 0.0
        elif ts < start:
            gap = start - ts
        else:
            gap = ts - end
        if best_gap is None or gap < best_gap:
            best_gap, best_type = gap, atype

    if best_gap is not None and best_gap <= MATCH_TOLERANCE_SEC:
        return best_type
    return "unmatched"


def main():
    print("Loading window metadata and ground-truth attack intervals...")
    window_meta = base.load_window_meta()
    intervals_by_window = base.load_attack_intervals(window_meta)
    for window_id, ivals in intervals_by_window.items():
        print(f"  {window_id}: {len(ivals)} attack commands in-window")

    flat_intervals = flatten_intervals(intervals_by_window)
    print(f"Pooled {len(flat_intervals)} attack command intervals across all real windows "
          f"(global ts matching, tolerance={MATCH_TOLERANCE_SEC}s).")

    print(f"\nLoading {TEST_INDICES_PATH} (read-only)...")
    test_df = pd.read_csv(TEST_INDICES_PATH)
    print(f"test_indices.csv: {len(test_df)} rows, {int(test_df['is_attack'].sum())} attack flows")
    print("Per-window attack-flow counts (incl. resampled windows):")
    print(test_df[test_df["is_attack"] == 1].groupby("window_id").size())

    attack_type = pd.Series("benign", index=test_df.index, dtype=object)
    attack_mask = test_df["is_attack"] == 1
    attack_type.loc[attack_mask] = test_df.loc[attack_mask, "ts"].apply(
        lambda ts: assign_attack_type_global(ts, flat_intervals)
    )
    attack_type = attack_type.replace({"portscan_test": "portscan"})
    test_df["attack_type"] = attack_type

    print("\nattack_type distribution among attack flows:")
    print(test_df.loc[attack_mask, "attack_type"].value_counts())

    n_attack = int(attack_mask.sum())
    n_unmatched = int((test_df.loc[attack_mask, "attack_type"] == "unmatched").sum())
    match_rate = 1 - n_unmatched / n_attack if n_attack else 0.0
    print(f"\nMatch rate: {match_rate:.2%} ({n_attack - n_unmatched}/{n_attack} attack flows labeled)")

    print("\nattack_type distribution by window_id (attack flows only):")
    print(
        test_df[attack_mask]
        .groupby(["window_id", "attack_type"])
        .size()
        .unstack(fill_value=0)
    )

    test_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {OUT_PATH} ({len(test_df)} rows, columns: {list(test_df.columns)})")


if __name__ == "__main__":
    main()
