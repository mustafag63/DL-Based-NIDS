"""
Validate the flow -> attack_type attribution method used in
attack_type_separability.py.

Motivation: the flow counts produced by that script's 1-second-tolerance
nearest-interval matching (apache_bench=1321, slowloris=1294) are far higher
than the counts recorded in context.md's original EDA table (apache_bench=404,
slowloris=207), a 3-6x increase. This suggests the tolerance matching may be
attributing the wrong flows to apache_bench/slowloris, which would undermine
the AUC=1.0 separability result obtained on the tolerant-matched set.

This script does NOT re-derive context.md's original counts (the exact
padding/method behind that number is not recoverable from attack_log.csv
alone, since attack_orchestrator.py on the unreachable Dell host was the only
other candidate source). Instead it treats attack_type_separability.py's own
two matching regimes as the object of study:

  - STRICT:   ts falls inside the logged command's [start_iso, end_iso]
              (zero tolerance, plain containment).
  - TOLERANT: nearest attack interval by time gap, accepted if the gap is
              <= MATCH_TOLERANCE_SEC (1.0s), as used in
              attack_type_separability.py.

Four checks are run, all read-only:

1. Within each window_id, do the (window-filtered) attack command intervals
   from attack_log.csv overlap each other? (sorted by start, check consecutive
   pairs for end_i > start_{i+1}).
2. Flows that TOLERANT matches to apache_bench/slowloris but STRICT does not
   ("tolerance-only" flows) are isolated and their duration/byte_ratio
   (Mann-Whitney U) and conn_state one-hot distribution (chi-square) are
   compared against the STRICT-matched flows of the same attack_type.
3. The separability test (Logistic Regression, 18 modeling columns, n=20
   stratified splits, mean AUC +/- std) is re-run using ONLY the STRICT-matched
   apache_bench/slowloris flows.
4. The STRICT-only AUC is compared side-by-side with the TOLERANT AUC from
   attack_type_separability.py, with a reasoned recommendation on which is
   more trustworthy.

Read-only: does not modify features_all_windows.*, splits/, or models/.
"""

import sys
import os

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attack_type_separability as base  # noqa: E402

N_REPEATS = base.N_REPEATS
TEST_SIZE = base.TEST_SIZE
MODEL_COLUMNS = base.MODEL_COLUMNS
CONN_STATE_COLUMNS = [c for c in MODEL_COLUMNS if c.startswith("conn_state")]


def check_interval_overlaps(intervals_by_window):
    """For each window, sort the (window-filtered) command intervals by start
    time and report any pair where one command's end time is after the next
    command's start time."""
    print("\n=== Check 1: do command intervals overlap within a window? ===")
    any_overlap = False
    for window_id, intervals in intervals_by_window.items():
        if not intervals:
            continue
        ordered = sorted(intervals, key=lambda t: t[1])
        print(f"\n{window_id}: {len(ordered)} commands")
        for (atype, start, end) in ordered:
            print(
                f"  {atype:14s} {pd.Timestamp(start, unit='s')}  ->  "
                f"{pd.Timestamp(end, unit='s')}  (dur={end - start:.3f}s)"
            )
        for i in range(len(ordered) - 1):
            atype_i, start_i, end_i = ordered[i]
            atype_j, start_j, end_j = ordered[i + 1]
            gap = start_j - end_i
            if gap < 0:
                any_overlap = True
                print(
                    f"  OVERLAP: {atype_i} ends {-gap:.3f}s after {atype_j} starts"
                )
            else:
                print(f"  gap {atype_i} -> {atype_j}: {gap:.3f}s (no overlap)")
    if not any_overlap:
        print(
            "\nNo overlapping command intervals found in any window: all "
            "commands within a window run strictly back-to-back with a "
            "positive gap between them."
        )
    return any_overlap


def assign_strict(row, intervals_by_window):
    """Pure point-in-time containment: ts must fall inside a command's
    [start, end]. No tolerance. Returns 'unmatched' or 'ambiguous' otherwise."""
    candidates = intervals_by_window.get(row["window_id"], [])
    matched = [atype for atype, start, end in candidates if start <= row["ts"] <= end]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        return "ambiguous"
    return "unmatched"


def compare_new_vs_strict(attack_df, attack_type):
    """Compare flows added only by tolerance matching against the strict-matched
    flows of the same attack_type, on duration/byte_ratio/conn_state."""
    strict_mask = attack_df["attack_type_strict"] == attack_type
    tolerant_mask = attack_df["attack_type_tolerant"] == attack_type
    new_mask = tolerant_mask & ~strict_mask

    strict_df = attack_df[strict_mask]
    new_df = attack_df[new_mask]

    print(f"\n--- {attack_type}: strict n={len(strict_df)}, tolerance-only-new n={len(new_df)} ---")
    if len(new_df) == 0:
        print("No tolerance-only flows for this type; nothing to compare.")
        return

    for col in ["duration_scaled", "byte_ratio_scaled"]:
        strict_vals = strict_df[col].values
        new_vals = new_df[col].values
        print(
            f"{col}: strict mean={strict_vals.mean():.4f} median={np.median(strict_vals):.4f} | "
            f"new mean={new_vals.mean():.4f} median={np.median(new_vals):.4f}"
        )
        if len(strict_vals) >= 1 and len(new_vals) >= 1:
            stat, p = mannwhitneyu(strict_vals, new_vals, alternative="two-sided")
            print(f"  Mann-Whitney U p-value: {p:.3e}  {'(significantly different)' if p < 0.05 else '(not significantly different)'}")

    strict_counts = strict_df[CONN_STATE_COLUMNS].sum().values
    new_counts = new_df[CONN_STATE_COLUMNS].sum().values
    print("conn_state distribution (counts):")
    print(f"  strict: {dict(zip(CONN_STATE_COLUMNS, strict_counts))}")
    print(f"  new:    {dict(zip(CONN_STATE_COLUMNS, new_counts))}")
    contingency = np.array([strict_counts, new_counts])
    if contingency.sum() > 0 and (contingency.sum(axis=0) > 0).all():
        try:
            chi2, p, dof, _ = chi2_contingency(contingency)
            print(f"  Chi-square p-value: {p:.3e}  {'(significantly different)' if p < 0.05 else '(not significantly different)'}")
        except ValueError as e:
            print(f"  Chi-square test not computable: {e}")


def run_auc(subset, group_a_types, group_b_types, name):
    mask_a = subset["attack_type_strict"].isin(group_a_types)
    mask_b = subset["attack_type_strict"].isin(group_b_types)
    df_ab = subset[mask_a | mask_b].copy()
    y = mask_a[mask_a | mask_b].astype(int).values
    n_a, n_b = int((y == 1).sum()), int((y == 0).sum())

    print(f"\n--- {name} (STRICT match only) ---")
    print(f"n({'/'.join(group_a_types)})={n_a}, n({'/'.join(group_b_types)})={n_b}")

    if n_a == 0 or n_b == 0:
        print("Cannot run: one class has zero flows under strict matching.")
        return None

    X = df_ab[MODEL_COLUMNS].values
    aucs = []
    for seed in range(N_REPEATS):
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=TEST_SIZE, stratify=y, random_state=seed
            )
        except ValueError as e:
            print(f"Split failed at seed {seed}: {e}")
            return None
        clf = LogisticRegression(max_iter=1000)
        clf.fit(X_train, y_train)
        proba = clf.predict_proba(X_test)[:, 1]
        aucs.append(roc_auc_score(y_test, proba))

    aucs = np.array(aucs)
    print(f"AUC over {N_REPEATS} stratified splits: {aucs.mean():.4f} +/- {aucs.std():.4f}")
    return aucs


def main():
    print("Loading window metadata and window-filtered attack_log intervals...")
    window_meta = base.load_window_meta()
    intervals = base.load_attack_intervals(window_meta)

    check_interval_overlaps(intervals)

    print("\nLoading features_all_windows.parquet (read-only)...")
    df = pd.read_parquet(base.FEATURES_PATH)
    attack_df = df[df["is_attack"] == 1].copy()

    attack_df["attack_type_strict"] = attack_df.apply(
        lambda row: assign_strict(row, intervals), axis=1
    )
    attack_df["attack_type_tolerant"] = attack_df.apply(
        lambda row: base.assign_attack_type(row, intervals), axis=1
    )
    for col in ["attack_type_strict", "attack_type_tolerant"]:
        attack_df[col] = attack_df[col].replace({"portscan_test": "portscan"})

    print("\nSTRICT match distribution (point-in-time containment, no tolerance):")
    print(attack_df["attack_type_strict"].value_counts())
    print("\nTOLERANT match distribution (nearest interval, <=1s gap):")
    print(attack_df["attack_type_tolerant"].value_counts())

    print("\n=== Check 2: tolerance-only-added flows vs strict-matched flows ===")
    for atype in ["apache_bench", "slowloris", "portscan"]:
        compare_new_vs_strict(attack_df, atype)

    print("\n=== Check 3: separability AUC on STRICT-matched flows only ===")
    hyp_aucs = run_auc(
        attack_df,
        group_a_types=["apache_bench"],
        group_b_types=["slowloris"],
        name="HYPOTHESIS: apache_bench vs slowloris",
    )
    ctrl_aucs = run_auc(
        attack_df,
        group_a_types=["portscan"],
        group_b_types=["apache_bench", "slowloris"],
        name="CONTROL: portscan vs (apache_bench + slowloris)",
    )

    print("\n=== Check 4: STRICT vs TOLERANT side-by-side ===")
    n_strict_ab = int((attack_df["attack_type_strict"] == "apache_bench").sum())
    n_strict_sl = int((attack_df["attack_type_strict"] == "slowloris").sum())
    n_strict_ps = int((attack_df["attack_type_strict"] == "portscan").sum())
    n_tol_ab = int((attack_df["attack_type_tolerant"] == "apache_bench").sum())
    n_tol_sl = int((attack_df["attack_type_tolerant"] == "slowloris").sum())
    n_tol_ps = int((attack_df["attack_type_tolerant"] == "portscan").sum())

    print(
        f"apache_bench: strict n={n_strict_ab}, tolerant n={n_tol_ab} "
        f"({'+' if n_tol_ab >= n_strict_ab else ''}{n_tol_ab - n_strict_ab})"
    )
    print(
        f"slowloris:    strict n={n_strict_sl}, tolerant n={n_tol_sl} "
        f"({'+' if n_tol_sl >= n_strict_sl else ''}{n_tol_sl - n_strict_sl})"
    )
    print(
        f"portscan:     strict n={n_strict_ps}, tolerant n={n_tol_ps} "
        f"({'+' if n_tol_ps >= n_strict_ps else ''}{n_tol_ps - n_strict_ps})"
    )

    if hyp_aucs is not None:
        print(f"\napache_bench vs slowloris — STRICT AUC:   {hyp_aucs.mean():.4f} +/- {hyp_aucs.std():.4f}")
    print("apache_bench vs slowloris — TOLERANT AUC: 1.0000 +/- 0.0000 (from attack_type_separability.py)")
    if ctrl_aucs is not None:
        print(f"portscan vs rest — STRICT AUC:            {ctrl_aucs.mean():.4f} +/- {ctrl_aucs.std():.4f}")
    print("portscan vs rest — TOLERANT AUC:          0.9967 +/- 0.0011 (from attack_type_separability.py)")


if __name__ == "__main__":
    main()
