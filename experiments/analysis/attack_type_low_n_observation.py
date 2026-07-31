"""
Observation-only (no attribution, no tolerance) look at what actually happens
around the apache_bench command in the low-N windows (window_02-05, N=21-92),
where strict (tolerance=0) point-in-time matching found zero apache_bench
flows in attack_type_strict_boundary_check.py.

Two competing explanations were proposed for that zero:
  (a) Clock skew / timestamp precision: the true apache_bench flows exist,
      but their logged ts sits a few hundred ms outside the command's
      [start_iso, end_iso] window (same mechanism documented for portscan in
      attack_type_separability.py's docstring, where the median gap to the
      nearest true interval was ~0.07-0.22s).
  (b) Behavioral: at low N (few, fast HTTP requests under high concurrency
      -c), ab.exe's requests genuinely collapse into a different flow
      pattern (e.g. reused/keep-alive connections) than at high N, so there
      may be very few or zero genuinely distinct SF/short flows to find at
      all, regardless of window width.

This script does NOT attribute or classify any flow. It only OBSERVES: for
each apache_bench occurrence in windows 02-05, list every port-80 flow to
the target host in a wide +/-2s bracket around the command's own
[start_iso, end_iso], with its duration and conn_state, and separately marks
which of those look like slowloris's own signature (RSTO, duration > 10s,
count matching that window's -s N parameter) so the remainder can be
inspected for an apache_bench candidate signature (SF, short duration).

Read-only: does not modify features_all_windows.*, splits/, or models/, and
does not write any classification back into it either.
"""

import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attack_type_separability as base  # noqa: E402

RAW_DATA_DIR = base.RAW_DATA_DIR
CONN_LOG_COLUMNS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes", "conn_state",
    "local_orig", "local_resp", "missed_bytes", "history", "orig_pkts",
    "orig_ip_bytes", "resp_pkts", "resp_ip_bytes", "tunnel_parents", "ip_proto",
]

LOW_N_WINDOWS = ["window_02_3pct", "window_03_5pct", "window_04_7pct", "window_05_12pct"]
OBSERVATION_MARGIN_SEC = 2.0
SLOWLORIS_LONG_DURATION_THRESHOLD = 10.0


def load_raw_conn_log(window_id):
    path = glob.glob(os.path.join(RAW_DATA_DIR, window_id, "zeek", "conn.log"))[0]
    raw = pd.read_csv(path, sep="\t", comment="#", header=None, names=CONN_LOG_COLUMNS)
    raw["duration"] = pd.to_numeric(raw["duration"], errors="coerce")
    return raw


def observe_window(window_id, intervals_by_window):
    ivals = sorted(intervals_by_window.get(window_id, []), key=lambda t: t[1])
    ab_occurrences = [
        (i, atype, start, end) for i, (atype, start, end) in enumerate(ivals) if atype == "apache_bench"
    ]
    if not ab_occurrences:
        print(f"{window_id}: no apache_bench commands found in-window.")
        return []

    raw = load_raw_conn_log(window_id)
    rows = []
    for occ_num, (i, atype, ab_start, ab_end) in enumerate(ab_occurrences, start=1):
        lo = ab_start - OBSERVATION_MARGIN_SEC
        hi = ab_end + OBSERVATION_MARGIN_SEC
        bracket = raw[(raw["ts"] >= lo) & (raw["ts"] <= hi) & (raw["id.resp_p"] == 80)].copy()
        bracket = bracket.sort_values("ts")

        n_total = len(bracket)
        n_long_rsto = int(
            ((bracket["conn_state"] == "RSTO") & (bracket["duration"] > SLOWLORIS_LONG_DURATION_THRESHOLD)).sum()
        )
        remainder = bracket[
            ~((bracket["conn_state"] == "RSTO") & (bracket["duration"] > SLOWLORIS_LONG_DURATION_THRESHOLD))
        ]
        n_remainder = len(remainder)
        n_remainder_sf_short = int(
            ((remainder["conn_state"] == "SF") & (remainder["duration"] < 1.0)).sum()
        )

        print(
            f"\n{window_id} occurrence #{occ_num} "
            f"(ab command [{pd.Timestamp(ab_start, unit='s').time()} - "
            f"{pd.Timestamp(ab_end, unit='s').time()}], "
            f"observation bracket = command +/- {OBSERVATION_MARGIN_SEC}s):"
        )
        print(f"  total port-80 flows in bracket: {n_total}")
        print(f"  of which slowloris-like (RSTO, duration > {SLOWLORIS_LONG_DURATION_THRESHOLD}s): {n_long_rsto}")
        print(f"  remainder (apache_bench candidates): {n_remainder}")
        if n_remainder:
            print(f"  remainder conn_state distribution: {remainder['conn_state'].value_counts().to_dict()}")
            print(
                f"  remainder duration stats: min={remainder['duration'].min():.4f}s "
                f"median={remainder['duration'].median():.4f}s max={remainder['duration'].max():.4f}s"
            )
            print(f"  remainder that is SF and < 1s (matches high-N apache_bench signature): {n_remainder_sf_short}")
            with pd.option_context("display.max_rows", None, "display.width", 140):
                print(remainder[["ts", "duration", "conn_state", "orig_bytes", "resp_bytes"]].to_string(index=False))
        else:
            print("  remainder is EMPTY -- no non-slowloris-like port-80 flow found in this bracket at all.")

        rows.append(
            {
                "window_id": window_id,
                "occurrence": occ_num,
                "n_total_port80": n_total,
                "n_slowloris_like": n_long_rsto,
                "n_remainder": n_remainder,
                "n_remainder_sf_short": n_remainder_sf_short,
            }
        )
    return rows


def main():
    print("Loading window metadata and window-filtered attack_log intervals...")
    window_meta = base.load_window_meta()
    intervals = base.load_attack_intervals(window_meta)

    print(
        f"\nObserving port-80 flows within +/-{OBSERVATION_MARGIN_SEC}s of each "
        f"apache_bench command's own [start_iso, end_iso] in the low-N windows "
        f"(window_02-05). This is OBSERVATION ONLY -- no flow is being "
        f"assigned/attributed here, just listed and described."
    )

    all_rows = []
    for window_id in LOW_N_WINDOWS:
        all_rows.extend(observe_window(window_id, intervals))

    summary = pd.DataFrame(all_rows)
    print("\n=== Summary across window_02-05 ===")
    print(summary.to_string(index=False))

    if (summary["n_remainder"] == 0).all():
        print(
            "\nFINDING (b): in every low-N occurrence, ALL port-80 flows in the "
            "+/-2s bracket around the apache_bench command are slowloris-like "
            "(RSTO, >10s). There is no remainder to inspect for an apache_bench "
            "candidate signature -- this points to a BEHAVIORAL explanation: at "
            "low N, apache_bench's HTTP requests are not producing separately "
            "observable SF/short flows within a reasonable window around the "
            "command at all (e.g. collapsed into keep-alive reuse of a "
            "connection opened outside this narrow bracket, or otherwise not "
            "distinctly logged), not merely a clock-skew/timestamp-precision "
            "issue that a wider window would fix."
        )
    elif (summary["n_remainder_sf_short"] > 0).all():
        print(
            "\nFINDING (a): every low-N occurrence DOES have a remainder of "
            "SF/short (<1s) port-80 flows once the observation bracket is "
            "widened to +/-2s -- consistent with the same apache_bench "
            "signature (SF, ~0.04-0.05s) found in the high-N windows. This "
            "points to a TIMESTAMP/WINDOW-WIDTH explanation: the true "
            "apache_bench flows exist at low N too, the strict [start,end] "
            "window from attack_log.csv was simply too narrow to contain them, "
            "not because the flows don't exist."
        )
    else:
        print(
            "\nMIXED RESULT: some low-N occurrences have an SF/short remainder "
            "and some do not -- inspect the per-occurrence detail above before "
            "drawing a single conclusion."
        )


if __name__ == "__main__":
    main()
