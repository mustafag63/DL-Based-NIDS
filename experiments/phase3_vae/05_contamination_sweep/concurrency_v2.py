"""
Shared helper: compute concurrency_src_1s_scaled for an arbitrary raw-flow
DataFrame (any window(s), any source), using the EXACT SAME formula as
02_phase2_feature_extraction/features_with_concurrency/build_features_v2_dense.py
and 14_concurrency_feature_experiment/ Config A:

  log1p(count of same-source-IP (id.orig_h) flows within |dt|<=1s, scoped to
  each row's own window_id, excluding itself), then standardized with the
  FIXED scaler fit on the Dense v2 train split (mean_log/std_log below,
  loaded from features_v2_meta.json and asserted, never refit here).

Using this shared function for window_10 (VAE-only) and for windows 02-08
(VAE's attack pool, but also already covered by features_v2_all_rows.csv)
guarantees the VAE side and the Dense side compute this feature identically.
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
FEATURES_V2_META = os.path.join(PROJECT_ROOT, "02_phase2_feature_extraction",
                                "features_with_concurrency", "features_v2_meta.json")

_meta = json.loads(open(FEATURES_V2_META).read())
MEAN_LOG = _meta["scaler"]["mean_log"]
STD_LOG = _meta["scaler"]["std_log"]

# Pinned expected values (Dense v2's fit) -- compute_concurrency_src_1s_scaled()
# asserts against these on every call so any drift (raw data changed, scaler
# refit differently) fails loudly instead of silently producing a
# differently-scaled feature than the Dense v2 model was trained on.
EXPECTED_MEAN_LOG = 2.0864962884954803
EXPECTED_STD_LOG = 0.6023503882972578
assert abs(MEAN_LOG - EXPECTED_MEAN_LOG) < 1e-9, (
    f"features_v2_meta.json mean_log={MEAN_LOG} != expected {EXPECTED_MEAN_LOG} "
    "-- Dense v2 scaler appears to have changed; stop and investigate before training VAE v2.")
assert abs(STD_LOG - EXPECTED_STD_LOG) < 1e-9, (
    f"features_v2_meta.json std_log={STD_LOG} != expected {EXPECTED_STD_LOG} "
    "-- Dense v2 scaler appears to have changed; stop and investigate before training VAE v2.")

RADIUS = 1.0


def compute_concurrency_src_1s_scaled(df: pd.DataFrame) -> np.ndarray:
    """df must have columns: window_id, id.orig_h, ts. Returns an array
    aligned to df's row order (NOT df.index -- caller should reset_index
    first if it relies on positional alignment elsewhere)."""
    n = len(df)
    raw_count = np.empty(n, dtype="int64")
    ts = df["ts"].values
    for _, idx in df.groupby(["window_id", "id.orig_h"], sort=False).indices.items():
        idx = np.asarray(idx)
        order = np.argsort(ts[idx], kind="mergesort")
        idx_sorted = idx[order]
        ts_sorted = ts[idx_sorted]
        lo = np.searchsorted(ts_sorted, ts_sorted - RADIUS, side="left")
        hi = np.searchsorted(ts_sorted, ts_sorted + RADIUS, side="right")
        raw_count[idx_sorted] = (hi - lo) - 1  # exclude self

    log_count = np.log1p(raw_count)
    return (log_count - MEAN_LOG) / STD_LOG
