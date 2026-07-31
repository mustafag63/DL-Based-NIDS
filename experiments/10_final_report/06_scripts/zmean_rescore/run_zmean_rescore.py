"""
Deterministic z_mean rescoring of ALL clean-only VAE (contam_0pct) results
(single attack type, pairwise, segmented injection), addressing finding O2 of
11_fable_review/independent_audit.md: the original scoring drew ONE stochastic
z sample per flow (tf.random.normal under an arbitrary fixed eval seed), so
every reported number carried single-sample Monte Carlo noise and depended on
the arbitrary 900_000/950_000 seed offsets.

This run scores with z = z_mean (reparameterization skipped at inference, see
reconstruction_error_zmean() / VAEBackend(deterministic=True) in
06_attack_type_analysis/evaluate_by_attack_type.py). Same 20 trained models,
same weights, no retraining -- only the inference-time score changes. The 20
seeds now capture ONLY weight-init/training variance, with zero scoring noise
on top.

threshold_95 note: the stored threshold.json values were calibrated on
STOCHASTIC val errors during training, so they do not transfer to the
deterministic score (z_mean errors are systematically smaller -- no sampling
noise inflating them). VAEBackend(deterministic=True) therefore recomputes
threshold_95 per seed as the 95th percentile of the deterministic error on the
SAME held-out val-benign set (05_contamination_sweep/01_data/val_benign.csv) --
the same "threshold computed fresh from val" convention DenseBackend already
uses. The threshold RULE (95th pctl of val-benign error) is unchanged.

Outputs land NEXT TO the existing stochastic results in 10_final_report/
(suffix _zmean), never overwriting them:
  01_single_attack_type/vae/results_zmean.{csv,md}
  02_pairwise_attack_type/vae/results_zmean.{csv,md} + results_combined_zmean.md
  03_segmented_injection/vae/block_recall_f1_zmean.md,
      block_recall_f1_per_seed_zmean.csv, error_plot_zmean.png
The original 06_attack_type_analysis/ and 07_segmented_injection/ result files
are not touched either.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))          # 10_final_report/
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
SEGMENTED_DIR = os.path.join(PROJECT_ROOT, "07_segmented_injection")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, SEGMENTED_DIR)
import evaluate_by_attack_type as single  # noqa: E402
import evaluate_pairwise_attack_type as pairwise  # noqa: E402
import evaluate_segmented_injection as segmented  # noqa: E402

SINGLE_DIR = os.path.join(REPORT_DIR, "01_single_attack_type", "vae")
PAIRWISE_DIR = os.path.join(REPORT_DIR, "02_pairwise_attack_type", "vae")
SEGMENTED_OUT_DIR = os.path.join(REPORT_DIR, "03_segmented_injection", "vae")

SINGLE_CSV = os.path.join(SINGLE_DIR, "results_zmean.csv")
SINGLE_MD = os.path.join(SINGLE_DIR, "results_zmean.md")
PAIRWISE_CSV = os.path.join(PAIRWISE_DIR, "results_zmean.csv")
PAIRWISE_MD = os.path.join(PAIRWISE_DIR, "results_zmean.md")
COMBINED_MD = os.path.join(PAIRWISE_DIR, "results_combined_zmean.md")
SEG_MD = os.path.join(SEGMENTED_OUT_DIR, "block_recall_f1_zmean.md")
SEG_CSV = os.path.join(SEGMENTED_OUT_DIR, "block_recall_f1_per_seed_zmean.csv")
SEG_PLOT = os.path.join(SEGMENTED_OUT_DIR, "error_plot_zmean.png")

SCORE_NOTE = (
    "**Scoring: deterministic z_mean** (reparameterization skipped at inference, "
    "z = z_mean -- no eps sample, no eval seed; audit finding O2). threshold_95 "
    "recomputed per seed as the 95th percentile of the deterministic error on the "
    "same held-out val-benign set (`05_contamination_sweep/01_data/val_benign.csv`), "
    "because the stored `threshold.json` values were calibrated on stochastic val "
    "errors and do not transfer. Companion to the original stochastic-scoring "
    "`results.csv`/`.md` next to this file; model weights identical, no retraining."
)


def main():
    backend = single.VAEBackend(deterministic=True)

    print("=" * 70)
    print("1/3 single attack type (deterministic z_mean)")
    print("=" * 70)
    single.main(backend=backend, results_csv=SINGLE_CSV, results_md=SINGLE_MD,
                score_note=SCORE_NOTE)

    print("\n" + "=" * 70)
    print("2/3 pairwise attack type (deterministic z_mean)")
    print("=" * 70)
    pairwise.main(backend=backend, results_csv=PAIRWISE_CSV, results_md=PAIRWISE_MD,
                  combined_md=COMBINED_MD, single_results_csv=SINGLE_CSV,
                  score_note=SCORE_NOTE)

    print("\n" + "=" * 70)
    print("3/3 segmented injection (deterministic z_mean)")
    print("=" * 70)
    segmented.run_segmented_evaluation(
        backend=backend,
        model_label="Clean-only VAE (contam_0pct), deterministic z_mean scoring",
        model_dir_desc="phase3_vae/05_contamination_sweep/04_models/contam_0pct "
                       "(z_mean scoring, threshold_95 recomputed on val-benign)",
        results_md=SEG_MD,
        results_csv=SEG_CSV,
        plot_path=SEG_PLOT,
        comparison_recall_csv=SINGLE_CSV,
    )

    print("\nAll _zmean outputs written; original stochastic result files untouched.")


if __name__ == "__main__":
    main()
