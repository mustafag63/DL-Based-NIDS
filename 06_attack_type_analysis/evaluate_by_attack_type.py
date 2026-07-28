"""
Break down the clean-only (0% train contamination) VAE's test-set detection
performance by attack_type (portscan / apache_bench / slowloris), using the
attack_type labels derived in derive_attack_type_labels.py
(06_attack_type_analysis/test_with_attack_type.csv).

Inference only -- no retraining. Loads the 20 already-trained contam_0pct
seed models (phase3_vae/05_contamination_sweep/04_models/contam_0pct/seed_*/)
and reuses the exact reconstruction-error / threshold_95 evaluation logic
from evaluate_contamination_sweep_extended.py (imported directly, not
reimplemented) so results stay consistent with the rest of the contamination
sweep.

For each attack_type, the evaluation set is: all test-split benign flows +
only that attack_type's attack flows (other attack types and "unmatched"
flows are excluded from that run, so each per-type AUC/PR-AUC/F1 reflects
that attack type against benign only, not against the other attack types).

Feature reconstruction: test_with_attack_type.csv only carries row_index/
window_id/ts/attack_type (no feature columns). The 18 modeling columns are
looked up by row_index against the same combined feature table the
03_phase3_splits/*_indices.csv row_index values were generated against:
    features_all_windows.csv (rows 0..36704, windows 01-08)
    + window_resampled_target15.0_actual15.00_features.csv (rows 36705..41603)
    + window_resampled_target20.0_actual19.99_features.csv (rows 41604..46494)
(verified by spot-checking window_id/ts/is_attack at several row_index values
before writing this script).

Read-only: does not modify test_with_attack_type.csv, splits/, or models/.
Writes 06_attack_type_analysis/results_single_attack_type.csv and .md.
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, fbeta_score, roc_auc_score

import keras.src.utils.python_utils as _keras_python_utils  # noqa: E402
_keras_python_utils.tf = tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
SWEEP_DIR = os.path.join(PROJECT_ROOT, "phase3_vae", "05_contamination_sweep")
NIDS_DATA_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "data")

LABELED_TEST_PATH = os.path.join(HERE, "test_with_attack_type.csv")
FEATURES_ALL_WINDOWS_PATH = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv"
)
RESAMPLED_15_PATH = os.path.join(
    NIDS_DATA_DIR, "ids-dataset-features", "by_window",
    "window_resampled_target15.0_actual15.00_features.csv",
)
RESAMPLED_20_PATH = os.path.join(
    NIDS_DATA_DIR, "ids-dataset-features", "by_window",
    "window_resampled_target20.0_actual19.99_features.csv",
)

MODEL_DIR = os.path.join(SWEEP_DIR, "04_models", "contam_0pct")
MANIFEST_PATH = os.path.join(SWEEP_DIR, "01_data", "manifest.json")

RESULTS_CSV = os.path.join(HERE, "results_single_attack_type.csv")
RESULTS_MD = os.path.join(HERE, "results_single_attack_type.md")

ATTACK_TYPES = ["portscan", "apache_bench", "slowloris"]
SEEDS = list(range(20))  # contam_0pct has 20 seeds, per the seed-extension commit

# Reuse the exact reconstruction-error function used throughout the
# contamination sweep, instead of reimplementing it.
_spec = importlib.util.spec_from_file_location(
    "evaluate_contamination_sweep_extended",
    os.path.join(SWEEP_DIR, "evaluate_contamination_sweep_extended.py"),
)
_sweep_eval = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _sweep_eval
_spec.loader.exec_module(_sweep_eval)
reconstruction_error = _sweep_eval.reconstruction_error


class VAEBackend:
    """Model backend for the clean-only (0% contamination) VAE, contam_0pct.

    evaluate_group() only relies on this interface (seeds, load, errors,
    threshold) -- it does not know or care that this backend happens to be a
    VAE. A model-agnostic evaluate_group() is what lets 08_dense_v1_comparison/
    reuse it unchanged for a plain Dense autoencoder, by swapping in a
    different backend object with the same 4 methods.
    """
    name = "vae_clean_contam0pct"

    def __init__(self, model_dir=MODEL_DIR, seeds=SEEDS, eval_seed_offset=900_000):
        self.model_dir = model_dir
        self.seeds = seeds
        self.eval_seed_offset = eval_seed_offset

    def load(self, seed):
        seed_dir = os.path.join(self.model_dir, f"seed_{seed}")
        encoder = tf.keras.models.load_model(os.path.join(seed_dir, "encoder.keras"), safe_mode=False)
        decoder = tf.keras.models.load_model(os.path.join(seed_dir, "decoder.keras"), safe_mode=False)
        threshold_info = json.loads(open(os.path.join(seed_dir, "threshold.json")).read())
        return {"encoder": encoder, "decoder": decoder, "threshold_95": threshold_info["threshold_95"]}

    def errors(self, model, X, seed):
        eval_seed = self.eval_seed_offset + seed
        return reconstruction_error(model["encoder"], model["decoder"], X, eval_seed)

    def threshold(self, model, seed):
        return model["threshold_95"]


DEFAULT_BACKEND = VAEBackend()


def build_combined_features():
    """Reconstruct the exact row_index -> features table the splits were cut
    from: features_all_windows.csv followed by the two resampled-window
    feature files, concatenated in that order with a fresh 0..N-1 index."""
    base = pd.read_csv(FEATURES_ALL_WINDOWS_PATH)
    resampled_15 = pd.read_csv(RESAMPLED_15_PATH)
    resampled_20 = pd.read_csv(RESAMPLED_20_PATH)
    combined = pd.concat([base, resampled_15, resampled_20], ignore_index=True)
    return combined


def load_feature_cols():
    manifest = json.loads(open(MANIFEST_PATH).read())
    return manifest["feature_cols"]


def assemble_labeled_features_df(feature_cols):
    """Load test_with_attack_type.csv and attach its 18 modeling feature
    columns via row_index, with the same row_index/window_id/ts/is_attack
    agreement check used in this module's own main()."""
    print("Loading test_with_attack_type.csv (row_index/window_id/is_attack/attack_type)...")
    labeled = pd.read_csv(LABELED_TEST_PATH)

    print("Reconstructing feature columns via row_index against the combined "
          "features_all_windows.csv + resampled-window feature tables...")
    combined = build_combined_features()
    features = combined.loc[labeled["row_index"].values, feature_cols].reset_index(drop=True)

    check_cols = combined.loc[labeled["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check_cols["window_id"].values == labeled["window_id"].values).all()
    assert np.allclose(check_cols["ts"].values, labeled["ts"].values)
    assert (check_cols["is_attack"].values == labeled["is_attack"].values).all()

    df = pd.concat([labeled.reset_index(drop=True), features], axis=1)
    print(f"Assembled eval frame: {len(df)} rows, {len(feature_cols)} feature columns.")
    return df


def evaluate_group(subset, feature_cols, group_name, backend=None):
    """Run every seed of `backend`'s model over one benign+attack subset.

    `subset` must already be filtered to exactly the flows this group's
    evaluation should include (is_attack==0 rows plus whichever attack_type(s)
    are being tested). Returns a list of per-seed metric dicts, identical
    columns regardless of which backend is used, so single-type/pairwise/
    segmented results for different models can be concatenated/compared
    directly.

    `backend` must implement: .seeds (iterable), .load(seed) -> model,
    .errors(model, X, seed) -> np.ndarray, .threshold(model, seed) -> float.
    Defaults to DEFAULT_BACKEND (the clean-only VAE) so existing callers that
    don't pass one keep their original behavior.
    """
    backend = backend or DEFAULT_BACKEND
    X = subset[feature_cols].values.astype("float32")
    y = subset["is_attack"].values
    n_benign = int((y == 0).sum())
    n_attack = int((y == 1).sum())
    print(f"\n=== {group_name}: n_benign={n_benign}, n_attack={n_attack} ===")

    rows = []
    for seed in backend.seeds:
        model = backend.load(seed)
        thr95 = backend.threshold(model, seed)
        errors = backend.errors(model, X, seed)

        pred95 = (errors > thr95).astype(int)
        pr_auc = average_precision_score(y, errors)
        roc_auc = roc_auc_score(y, errors)
        f1 = fbeta_score(y, pred95, beta=1.0, zero_division=0)

        benign_mask = y == 0
        attack_mask = y == 1
        benign_fpr = float(pred95[benign_mask].mean()) if benign_mask.any() else float("nan")
        attack_recall = float(pred95[attack_mask].mean()) if attack_mask.any() else float("nan")

        row = {
            "attack_type": group_name,
            "seed": seed,
            "n_benign": n_benign,
            "n_attack": n_attack,
            "threshold_95": thr95,
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "f1": f1,
            "benign_fpr": benign_fpr,
            "attack_recall": attack_recall,
        }
        # Per-constituent-type recall decomposition: at a fixed model/threshold,
        # a flow's flag decision (errors > thr95) does not depend on which
        # other flows share the evaluation set, so this is the honest way to
        # show whether a specific attack type's OWN detections changed under
        # pairing, as opposed to the pooled `attack_recall` above (which is
        # just an n-weighted average across whichever types are in `subset`
        # and moves mechanically when the mix changes, even if no individual
        # flow's outcome does).
        attack_types_present = subset.loc[attack_mask, "attack_type"].unique()
        for atype in sorted(attack_types_present):
            m = attack_mask & (subset["attack_type"].values == atype)
            row[f"recall__{atype}"] = float(pred95[m].mean()) if m.any() else float("nan")
        rows.append(row)

    print(
        f"  mean over {len(rows)} seeds: "
        f"ROC-AUC={np.mean([r['roc_auc'] for r in rows]):.4f} "
        f"PR-AUC={np.mean([r['pr_auc'] for r in rows]):.4f} "
        f"F1={np.mean([r['f1'] for r in rows]):.4f} "
        f"benign_FPR={np.mean([r['benign_fpr'] for r in rows]):.4f} "
        f"attack_recall={np.mean([r['attack_recall'] for r in rows]):.4f}"
    )
    return rows


def compute_error_matrix(X, backend=None):
    """Run every seed of `backend`'s model over the same (already
    feature-extracted) X, in whatever row order X is in.

    Returns (error_matrix, thresholds): error_matrix has shape
    (n_seeds, len(X)), thresholds is a list of each seed's threshold_95, in
    the same seed order. Shared by any script that needs a per-flow error
    trajectory (e.g. segmented-injection stream plots) rather than
    evaluate_group()'s per-group aggregate metrics -- both 07_segmented_injection
    and 08_dense_v1_comparison's segmented script call this directly instead
    of reimplementing the seed loop.
    """
    backend = backend or DEFAULT_BACKEND
    seeds = list(backend.seeds)
    error_matrix = np.zeros((len(seeds), len(X)), dtype="float64")
    thresholds = []
    for i, seed in enumerate(seeds):
        model = backend.load(seed)
        thresholds.append(backend.threshold(model, seed))
        error_matrix[i] = backend.errors(model, X, seed)
    return error_matrix, thresholds


def main():
    feature_cols = load_feature_cols()
    df = assemble_labeled_features_df(feature_cols)

    all_rows = []
    for attack_type in ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        all_rows.extend(evaluate_group(subset, feature_cols, attack_type))

    per_seed_df = pd.DataFrame(all_rows)

    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.reset_index()
    summary.to_csv(RESULTS_CSV, index=False)
    print(f"\nWrote {RESULTS_CSV}")

    lines = [
        "# Clean-only (0% contamination) VAE, evaluated per attack type",
        "",
        f"Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` "
        f"({len(SEEDS)} seeds, threshold_95 per seed, inference only, no retraining).",
        "",
        "Each row = that attack type's flows vs. the full test-split benign set "
        "only (other attack types excluded from that run). Mean +/- std across "
        f"{len(SEEDS)} seeds.",
        "",
        "| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['attack_type']} | {int(r['n_benign'])} | {int(r['n_attack'])} | "
            f"{r['roc_auc_mean']:.4f} +/- {r['roc_auc_std']:.4f} | "
            f"{r['pr_auc_mean']:.4f} +/- {r['pr_auc_std']:.4f} | "
            f"{r['f1_mean']:.4f} +/- {r['f1_std']:.4f} | "
            f"{r['benign_fpr_mean']:.4f} +/- {r['benign_fpr_std']:.4f} | "
            f"{r['attack_recall_mean']:.4f} +/- {r['attack_recall_std']:.4f} |"
        )
    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {RESULTS_MD}")


if __name__ == "__main__":
    main()
