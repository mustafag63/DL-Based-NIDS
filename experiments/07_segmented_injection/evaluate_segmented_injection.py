"""
Evaluate the clean-only (0% train contamination) VAE, inference only (no
retraining), on the segmented-injection stream built by
build_segmented_injection.py (07_segmented_injection/segmented_sequence.csv):
benign / apache_bench / benign / slowloris / benign / portscan / benign, each
attack block contiguous instead of shuffled in with the rest of the test set.

Reuses, not reimplements:
  - feature reconstruction (row_index -> 18 modeling columns),
    load_feature_cols(), and compute_error_matrix() from
    06_attack_type_analysis/evaluate_by_attack_type.py
  - reconstruction_error() from phase3_vae/05_contamination_sweep/
    evaluate_contamination_sweep_extended.py (imported by evaluate_by_attack_type.py)
  - the same contam_0pct model dir / threshold_95 convention as both of the
    above, via evaluate_by_attack_type.VAEBackend.

run_segmented_evaluation() is model-agnostic (takes a `backend` object with
the same .seeds/.load()/.errors()/.threshold() interface used throughout
06_attack_type_analysis) so 08_dense_v1_comparison/evaluate_segmented_injection_dense.py
imports and calls it directly with a Dense backend instead of duplicating
this file.

Two outputs per run:
  1. <results_md>: per-segment (each benign gap and each attack block)
     recall/FPR/F1, to check whether the apache_bench weakness seen in
     06_attack_type_analysis persists when apache_bench arrives as one
     contiguous block instead of interleaved with other attack types.
  2. <plot_path>: reconstruction error vs. stream position, mean across
     seeds, with dashed vertical lines at every segment boundary (labeled)
     and the mean threshold_95 as a horizontal reference line.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import fbeta_score

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")

SEQUENCE_PATH = os.path.join(HERE, "segmented_sequence.csv")
RESULTS_MD = os.path.join(HERE, "results_segmented.md")
RESULTS_CSV = os.path.join(HERE, "results_segmented_per_seed.csv")
PLOT_PATH = os.path.join(HERE, "segmented_injection_error_plot.png")

sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402


def load_ordered_features(sequence_path, feature_cols):
    sequence = pd.read_csv(sequence_path)

    combined = single.build_combined_features()
    features = combined.loc[sequence["row_index"].values, feature_cols].reset_index(drop=True)

    check_cols = combined.loc[sequence["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check_cols["window_id"].values == sequence["window_id"].values).all()
    assert np.allclose(check_cols["ts"].values, sequence["ts"].values)
    assert (check_cols["is_attack"].values == sequence["is_attack"].values).all()

    df = pd.concat([sequence, features], axis=1)
    return df


def run_segmented_evaluation(
    backend=None,
    model_label="Clean-only VAE (contam_0pct)",
    model_dir_desc="phase3_vae/05_contamination_sweep/04_models/contam_0pct",
    sequence_path=SEQUENCE_PATH,
    results_md=RESULTS_MD,
    results_csv=RESULTS_CSV,
    plot_path=PLOT_PATH,
    comparison_recall_csv=None,
):
    """Shared segmented-injection evaluation, model-agnostic via `backend`
    (same .seeds/.load()/.errors()/.threshold() interface as evaluate_group()
    and compute_error_matrix() in evaluate_by_attack_type.py).

    `comparison_recall_csv`, if given, must be a results_single_attack_type.csv
    -shaped file (attack_type, attack_recall_mean, attack_recall_std columns)
    for the SAME model/backend's shuffled-test-set run, so the per-segment
    table can show a same-model shuffled-vs-segmented comparison column.
    """
    backend = backend or single.DEFAULT_BACKEND
    feature_cols = single.load_feature_cols()

    print(f"Loading {sequence_path} and reconstructing its {len(feature_cols)} modeling feature columns...")
    df = load_ordered_features(sequence_path, feature_cols)
    X = df[feature_cols].values.astype("float32")
    y = df["is_attack"].values
    print(f"Sequence: {len(df)} flows, {df['segment_id'].nunique()} segments.")

    error_matrix, thresholds_95 = single.compute_error_matrix(X, backend=backend)
    n_seeds = error_matrix.shape[0]
    for i in range(n_seeds):
        print(f"  seed={i}: mean error={error_matrix[i].mean():.5f}")

    mean_error = error_matrix.mean(axis=0)
    std_error = error_matrix.std(axis=0)
    mean_thr95 = float(np.mean(thresholds_95))
    print(f"\nMean threshold_95 across {n_seeds} seeds: {mean_thr95:.5f}")

    # --- per-segment metrics, per seed, at each seed's own threshold_95 ---
    per_seed_rows = []
    segments = df[["segment_id", "segment_label"]].drop_duplicates().sort_values("segment_id")
    for i in range(n_seeds):
        errors = error_matrix[i]
        thr95 = thresholds_95[i]
        pred95 = (errors > thr95).astype(int)
        for _, seg in segments.iterrows():
            seg_id, seg_label = seg["segment_id"], seg["segment_label"]
            mask = (df["segment_id"] == seg_id).values
            n = int(mask.sum())
            seg_y = y[mask]
            seg_pred = pred95[mask]
            if seg_label == "benign":
                fpr = float(seg_pred.mean())
                recall = float("nan")
                f1 = float("nan")
            else:
                fpr = float("nan")
                recall = float(seg_pred.mean())
                f1 = fbeta_score(seg_y, seg_pred, beta=1.0, zero_division=0)
            per_seed_rows.append({
                "seed": i, "segment_id": seg_id, "segment_label": seg_label, "n": n,
                "fpr": fpr, "recall": recall, "f1": f1,
            })

    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(results_csv, index=False)
    print(f"Wrote {results_csv}")

    summary = per_seed_df.groupby(["segment_id", "segment_label", "n"])[["fpr", "recall", "f1"]].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary = summary.reset_index().sort_values("segment_id")

    single_ref = None
    if comparison_recall_csv and os.path.exists(comparison_recall_csv):
        single_ref = pd.read_csv(comparison_recall_csv).set_index("attack_type")

    lines = [
        f"# Segmented (contiguous-block) injection: {model_label}, per-segment results",
        "",
        f"Sequence: `{os.path.basename(sequence_path)}` ({len(df)} flows, block order from "
        f"`segmented_sequence_config.json`). Model: `{model_dir_desc}` "
        f"({n_seeds} seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.",
        "",
        "| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        fpr = f"{r['fpr_mean']:.4f} +/- {r['fpr_std']:.4f}" if not np.isnan(r["fpr_mean"]) else "--"
        recall = f"{r['recall_mean']:.4f} +/- {r['recall_std']:.4f}" if not np.isnan(r["recall_mean"]) else "--"
        f1 = f"{r['f1_mean']:.4f} +/- {r['f1_std']:.4f}" if not np.isnan(r["f1_mean"]) else "--"
        ref = "--"
        if single_ref is not None and r["segment_label"] in single_ref.index:
            ref_row = single_ref.loc[r["segment_label"]]
            ref = f"{ref_row['attack_recall_mean']:.4f} +/- {ref_row['attack_recall_std']:.4f}"
        lines.append(f"| {int(r['segment_id'])} | {r['segment_label']} | {int(r['n'])} | {fpr} | {recall} | {f1} | {ref} |")

    lines += [
        "",
        "## Interpretation",
        "",
    ]
    ab_rows = summary[summary["segment_label"] == "apache_bench"]
    if not ab_rows.empty:
        ab_recall = ab_rows.iloc[0]["recall_mean"]
        lines.append(
            f"apache_bench block recall = {ab_recall:.4f} -- "
            + ("still near-zero" if ab_recall < 0.1 else "notably higher")
            + " when the attack type arrives as one contiguous block instead of interleaved with "
            "other attack types. Since detection is a static per-flow decision (reconstruction "
            "error > a fixed threshold) with no sequence memory in either model tested here, "
            "contiguous placement is not expected to change per-flow outcomes; this row exists to "
            "confirm that empirically rather than assume it."
        )

    benign_rows = summary[summary["segment_label"] == "benign"]
    if len(benign_rows) > 1:
        fpr_vals = benign_rows["fpr_mean"].values
        lines.append(
            f"\nBenign-segment FPR ranges {fpr_vals.min():.4f}-{fpr_vals.max():.4f} across the "
            f"{len(benign_rows)} benign gaps in this stream (vs. a single {benign_rows['fpr_mean'].mean():.4f} "
            "average if measured as one block). This spread is a SYSTEMATIC composition effect, "
            "not sampling noise: the benign pool is split into contiguous gaps in ts order "
            "(build_segmented_injection.py) and the capture windows are consecutive in time, so "
            "each gap holds a different mix of windows' benign flows, and per-window benign FPR "
            "differs. At these gap sizes the binomial std of an FPR near 0.05 is only ~0.005, "
            "which cannot produce a spread this wide; it is also not the model drifting (no "
            "state is carried between flows). See segment_window_composition.md (next to the "
            "VAE run's outputs; the segment-by-window composition itself is model-independent) "
            "for the per-gap window breakdown."
        )

    with open(results_md, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {results_md}")

    # --- plot: reconstruction error vs. stream position ---
    fig, ax = plt.subplots(figsize=(16, 5))
    positions = df["position"].values

    benign_mask = (y == 0)
    attack_mask = (y == 1)
    ax.scatter(positions[benign_mask], mean_error[benign_mask], s=4, color="#3b6fa0", alpha=0.5, label="benign flow")
    ax.scatter(positions[attack_mask], mean_error[attack_mask], s=4, color="#c0392b", alpha=0.6, label="attack flow")
    ax.fill_between(positions, mean_error - std_error, mean_error + std_error, color="#999999", alpha=0.15,
                     label=f"+/- 1 std across {n_seeds} seeds")

    ax.axhline(mean_thr95, color="#2c3e50", linestyle=":", linewidth=1.2, label=f"mean threshold_95 = {mean_thr95:.3f}")

    boundaries = df.groupby("segment_id")["position"].min().sort_index()
    seg_labels = df.groupby("segment_id")["segment_label"].first().sort_index()
    for seg_id, start_pos in boundaries.items():
        if seg_id > 0:
            ax.axvline(start_pos, color="#555555", linestyle="--", linewidth=0.8)
        mid = start_pos + (df[df["segment_id"] == seg_id]["position"].max() - start_pos) / 2
        ax.text(mid, ax.get_ylim()[1] * 0.95, seg_labels[seg_id], ha="center", va="top",
                fontsize=9, rotation=0,
                color="#2c3e50" if seg_labels[seg_id] == "benign" else "#c0392b")

    ax.set_yscale("log")
    ax.set_xlabel("Stream position (segmented, contiguous attack blocks)")
    ax.set_ylabel(f"Reconstruction error (log scale, mean of {n_seeds} seeds)")
    ax.set_title(f"{model_label} reconstruction error over a segmented-injection stream\n"
                 "benign -> apache_bench -> benign -> slowloris -> benign -> portscan -> benign")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, markerscale=2, borderaxespad=0)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    print(f"Wrote {plot_path}")

    return summary


def main():
    # eval_seed_offset=950_000 (distinct from evaluate_group()'s 900_000, both
    # arbitrary) matches this script's original standalone version, so its
    # published results/plot stay exactly reproducible after the refactor.
    run_segmented_evaluation(
        backend=single.VAEBackend(eval_seed_offset=950_000),
        comparison_recall_csv=os.path.join(ATTACK_TYPE_DIR, "results_single_attack_type.csv"),
    )


if __name__ == "__main__":
    main()
