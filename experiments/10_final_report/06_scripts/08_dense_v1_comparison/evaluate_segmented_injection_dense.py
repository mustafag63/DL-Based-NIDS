"""
Repeat 07_segmented_injection's contiguous-block (segmented) injection
evaluation on the Dense autoencoder v1 (full_features, 5 seeds) instead of
the clean-only VAE -- inference only, no retraining.

Reuses the exact same segmented_sequence.csv built once in
07_segmented_injection/ (the flows and their order don't depend on which
model evaluates them) and calls
07_segmented_injection/evaluate_segmented_injection.run_segmented_evaluation()
directly with dense_backend.DEFAULT_DENSE_BACKEND -- none of the per-segment
metric computation or plotting logic is reimplemented here.

Writes:
  results_segmented_dense.md
  results_segmented_dense_per_seed.csv
  segmented_injection_error_plot_dense.png
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
SEGMENTED_DIR = os.path.join(PROJECT_ROOT, "07_segmented_injection")

sys.path.insert(0, SEGMENTED_DIR)
sys.path.insert(0, HERE)
import evaluate_segmented_injection as seg  # noqa: E402
from dense_backend import DEFAULT_DENSE_BACKEND, MODEL_LABEL, MODEL_DIR_DESC  # noqa: E402

SEQUENCE_PATH = os.path.join(SEGMENTED_DIR, "segmented_sequence.csv")
RESULTS_MD = os.path.join(HERE, "results_segmented_dense.md")
RESULTS_CSV = os.path.join(HERE, "results_segmented_dense_per_seed.csv")
PLOT_PATH = os.path.join(HERE, "segmented_injection_error_plot_dense.png")
COMPARISON_RECALL_CSV = os.path.join(HERE, "results_single_attack_type_dense.csv")


def main():
    seg.run_segmented_evaluation(
        backend=DEFAULT_DENSE_BACKEND,
        model_label=MODEL_LABEL,
        model_dir_desc=MODEL_DIR_DESC,
        sequence_path=SEQUENCE_PATH,
        results_md=RESULTS_MD,
        results_csv=RESULTS_CSV,
        plot_path=PLOT_PATH,
        comparison_recall_csv=COMPARISON_RECALL_CSV,
    )


if __name__ == "__main__":
    main()
