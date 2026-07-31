"""
Regenerate the VAE-score-dependent parts of 04_apache_bench_diagnostics/ with
the DETERMINISTIC z_mean score (audit O2), replacing the stochastic-score
originals (which are moved to _stochastic_legacy/ first, not deleted).

Regenerated (score-dependent):
  vae_reconstruction_error_hist.png   -- benign / apache_bench /
      portscan+slowloris histogram, mean error over the 20 contam_0pct seeds,
      deterministic z_mean; threshold line = mean of the per-seed
      deterministic threshold_95 values (recomputed on val-benign, same
      convention as every other deterministic result in 10_final_report/)
  vae_reconstruction_error_summary.csv -- per-group n / mean / std /
      %-above-mean-threshold

NOT regenerated (score-independent, still valid as-is):
  feature_diagnostics_*.csv, top_features_apache_bench_boxplots.png
      (raw scaled-feature distributions + KS tests -- no VAE involved)
  temporal_iat_summary.csv, iat_apache_bench_vs_benign_hist.png
      (pure ts-difference analysis -- no VAE involved)

Reuses, not reimplements: plot_error_histogram() from
diagnose_apache_bench.py, and assemble_labeled_features_df() /
compute_error_matrix() / VAEBackend(deterministic=True) from
06_attack_type_analysis/evaluate_by_attack_type.py.
"""
import os
import shutil
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
DIAG_SCRIPT_DIR = os.path.join(REPORT_DIR, "06_scripts", "apache_bench_diagnostics")
OUT_DIR = os.path.join(REPORT_DIR, "04_apache_bench_diagnostics")
LEGACY_DIR = os.path.join(OUT_DIR, "_stochastic_legacy")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DIAG_SCRIPT_DIR)
import evaluate_by_attack_type as single  # noqa: E402
import diagnose_apache_bench as diag  # noqa: E402

HIST_PNG = os.path.join(OUT_DIR, "vae_reconstruction_error_hist.png")
SUMMARY_CSV = os.path.join(OUT_DIR, "vae_reconstruction_error_summary.csv")
ATTACK_TYPES = diag.ATTACK_TYPES


def move_to_legacy():
    os.makedirs(LEGACY_DIR, exist_ok=True)
    for path in (HIST_PNG, SUMMARY_CSV):
        if os.path.exists(path):
            dest = os.path.join(LEGACY_DIR, os.path.basename(path))
            if os.path.exists(dest):
                print(f"  legacy copy already exists, leaving both: {dest}")
                continue
            shutil.move(path, dest)
            print(f"  moved {os.path.basename(path)} -> _stochastic_legacy/")


def main():
    move_to_legacy()

    feature_cols = single.load_feature_cols()
    df = single.assemble_labeled_features_df(feature_cols)
    benign_df = df[df["is_attack"] == 0]
    group_dfs = {a: df[df["attack_type"] == a] for a in ATTACK_TYPES}

    combined = pd.concat([benign_df] + [group_dfs[a] for a in ATTACK_TYPES], ignore_index=True)
    X = combined[feature_cols].values.astype("float32")
    backend = single.VAEBackend(deterministic=True)
    error_matrix, thresholds = single.compute_error_matrix(X, backend=backend)
    mean_errors = error_matrix.mean(axis=0)
    mean_threshold = float(np.mean(thresholds))
    print(f"Deterministic mean threshold_95 over 20 seeds: {mean_threshold:.5f}")

    n_benign = len(benign_df)
    offsets = {"benign": (0, n_benign)}
    cursor = n_benign
    for a in ATTACK_TYPES:
        offsets[a] = (cursor, cursor + len(group_dfs[a]))
        cursor += len(group_dfs[a])

    errors_by_group = {
        "benign": mean_errors[slice(*offsets["benign"])],
        "apache_bench": mean_errors[slice(*offsets["apache_bench"])],
        "portscan+slowloris": np.concatenate([
            mean_errors[slice(*offsets["portscan"])],
            mean_errors[slice(*offsets["slowloris"])],
        ]),
    }
    diag.plot_error_histogram(errors_by_group, mean_threshold, HIST_PNG)
    print(f"Wrote {HIST_PNG}")

    summary = pd.DataFrame([
        {"group": name, "n": len(errs),
         "mean_error": float(np.mean(errs)), "std_error": float(np.std(errs)),
         "median_error": float(np.median(errs)),
         "pct_above_mean_threshold95": float((errs > mean_threshold).mean())}
        for name, errs in errors_by_group.items()
    ])
    summary.to_csv(SUMMARY_CSV, index=False)
    print(f"Wrote {SUMMARY_CSV}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
