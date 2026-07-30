"""
STAGE 3: segmented (contiguous-block) injection evaluation for the v2
(19-feature, +concurrency_src_1s) models. Reuses the SAME
07_segmented_injection/segmented_sequence.csv (the flow order --
benign -> apache_bench -> benign -> slowloris -> benign -> portscan ->
benign -- doesn't depend on which model or feature set evaluates it) and
06_attack_type_analysis/evaluate_by_attack_type.py's compute_error_matrix()
(model-agnostic, unchanged); only the feature lookup is v2-specific
(build_combined_features_v2 instead of the 18-feature build_combined_features).
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
DENSE_V2_DIR = os.path.join(PROJECT_ROOT, "09_dense_v2_comparison")
SEGMENTED_DIR = os.path.join(PROJECT_ROOT, "07_segmented_injection")
sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, DENSE_V2_DIR)
import evaluate_by_attack_type as single  # noqa: E402
from dense_backend_v2 import load_feature_cols_v2, build_combined_features_v2  # noqa: E402

SEQUENCE_PATH = os.path.join(SEGMENTED_DIR, "segmented_sequence.csv")


def load_ordered_features_v2(sequence_path, feature_cols):
    sequence = pd.read_csv(sequence_path)
    combined = build_combined_features_v2()
    features = combined.loc[sequence["row_index"].values, feature_cols].reset_index(drop=True)
    check_cols = combined.loc[sequence["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check_cols["window_id"].values == sequence["window_id"].values).all()
    assert np.allclose(check_cols["ts"].values, sequence["ts"].values)
    assert (check_cols["is_attack"].values == sequence["is_attack"].values).all()
    df = pd.concat([sequence, features], axis=1)
    return df


def run_segmented_evaluation_v2(backend, model_label, model_dir_desc, out_dir, comparison_recall_csv):
    os.makedirs(out_dir, exist_ok=True)
    feature_cols = load_feature_cols_v2()
    results_md = os.path.join(out_dir, "block_recall_f1.md")
    results_csv = os.path.join(out_dir, "block_recall_f1_per_seed.csv")
    plot_path = os.path.join(out_dir, "error_plot.png")

    print(f"Loading {SEQUENCE_PATH} and reconstructing its {len(feature_cols)} v2 feature columns...")
    df = load_ordered_features_v2(SEQUENCE_PATH, feature_cols)
    X = df[feature_cols].values.astype("float32")
    y = df["is_attack"].values
    print(f"Sequence: {len(df)} flows, {df['segment_id'].nunique()} segments.")

    error_matrix, thresholds_95 = single.compute_error_matrix(X, backend=backend)
    n_seeds = error_matrix.shape[0]
    mean_error = error_matrix.mean(axis=0)
    std_error = error_matrix.std(axis=0)
    mean_thr95 = float(np.mean(thresholds_95))
    print(f"Mean threshold_95 across {n_seeds} seeds: {mean_thr95:.5f}")

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
                fpr, recall, f1 = float(seg_pred.mean()), float("nan"), float("nan")
            else:
                fpr = float("nan")
                recall = float(seg_pred.mean())
                f1 = fbeta_score(seg_y, seg_pred, beta=1.0, zero_division=0)
            per_seed_rows.append({"seed": i, "segment_id": seg_id, "segment_label": seg_label,
                                  "n": n, "fpr": fpr, "recall": recall, "f1": f1})

    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(results_csv, index=False)
    print(f"Wrote {results_csv}")

    summary = per_seed_df.groupby(["segment_id", "segment_label", "n"])[["fpr", "recall", "f1"]].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    summary = summary.reset_index().sort_values("segment_id")

    single_ref = pd.read_csv(comparison_recall_csv).set_index("attack_type") if comparison_recall_csv else None

    lines = [
        f"# Segmented (contiguous-block) injection: {model_label}, per-segment results",
        "",
        f"Sequence: `segmented_sequence.csv` ({len(df)} flows, block order from "
        f"`segmented_sequence_config.json`, unchanged from v1). Model: `{model_dir_desc}` "
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

    lines += ["", "## Interpretation", ""]
    ab_rows = summary[summary["segment_label"] == "apache_bench"]
    if not ab_rows.empty:
        ab_recall = ab_rows.iloc[0]["recall_mean"]
        lines.append(
            f"apache_bench block recall = {ab_recall:.4f} -- "
            + ("still near-zero" if ab_recall < 0.1 else "notably higher, consistent with the "
               "shuffled-test-set single_attack_type/pairwise v2 results")
            + ". Static per-flow threshold decision, no sequence memory: contiguous placement is "
            "not expected to change per-flow outcomes; confirmed empirically here."
        )
    benign_rows = summary[summary["segment_label"] == "benign"]
    if len(benign_rows) > 1:
        fpr_vals = benign_rows["fpr_mean"].values
        lines.append(
            f"\nBenign-segment FPR ranges {fpr_vals.min():.4f}-{fpr_vals.max():.4f} across the "
            f"{len(benign_rows)} benign gaps (vs. a single {benign_rows['fpr_mean'].mean():.4f} "
            "average if measured as one block)."
        )

    with open(results_md, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {results_md}")

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
                fontsize=9, color="#2c3e50" if seg_labels[seg_id] == "benign" else "#c0392b")

    ax.set_yscale("log")
    ax.set_xlabel("Stream position (segmented, contiguous attack blocks)")
    ax.set_ylabel(f"Reconstruction error (log scale, mean of {n_seeds} seeds)")
    ax.set_title(f"{model_label} reconstruction error over a segmented-injection stream\n"
                 "benign -> apache_bench -> benign -> slowloris -> benign -> portscan -> benign")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, markerscale=2, borderaxespad=0)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {plot_path}")
    return summary


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "10_vae_v2_comparison"))
    from dense_backend_v2 import DEFAULT_DENSE_V2_BACKEND, MODEL_LABEL as DENSE_LABEL, MODEL_DIR_DESC as DENSE_DESC  # noqa: E402
    from vae_backend_v2 import DEFAULT_VAE_V2_BACKEND, MODEL_LABEL as VAE_LABEL, MODEL_DIR_DESC as VAE_DESC  # noqa: E402

    print("=== Dense v2 (5 seeds) ===")
    run_segmented_evaluation_v2(
        DEFAULT_DENSE_V2_BACKEND, DENSE_LABEL, DENSE_DESC,
        os.path.join(HERE, "dense_v2"),
        os.path.join(DENSE_V2_DIR, "results_single_attack_type_dense_v2.csv"),
    )
    print("\n=== VAE v2 (5 seeds, deterministic z_mean) ===")
    run_segmented_evaluation_v2(
        DEFAULT_VAE_V2_BACKEND, VAE_LABEL, VAE_DESC,
        os.path.join(HERE, "vae"),
        os.path.join(PROJECT_ROOT, "10_vae_v2_comparison", "results_single_attack_type_vae_v2.csv"),
    )
    print("done")
