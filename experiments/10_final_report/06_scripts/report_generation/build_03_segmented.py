import os, sys
sys.path.insert(0, "/private/tmp/claude-501/-Users-mustafa-Desktop-NIDS-IDS-Project/27367645-50b6-4f4c-ad67-446d3fe33e07/scratchpad")
import report_style as sty
sty.apply()

PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
SEGMENTED_DIR = os.path.join(PROJECT_ROOT, "07_segmented_injection")
DENSE_DIR = os.path.join(PROJECT_ROOT, "08_dense_v1_comparison")
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "03_segmented_injection")

sys.path.insert(0, ATTACK_TYPE_DIR)
sys.path.insert(0, SEGMENTED_DIR)
sys.path.insert(0, DENSE_DIR)
import evaluate_by_attack_type as single
import evaluate_segmented_injection as seg
from dense_backend import DEFAULT_DENSE_BACKEND, MODEL_LABEL as DENSE_LABEL, MODEL_DIR_DESC as DENSE_DIR_DESC

os.makedirs(os.path.join(OUT_ROOT, "vae"), exist_ok=True)
os.makedirs(os.path.join(OUT_ROOT, "dense_v1"), exist_ok=True)

print("=== VAE (20 seeds) ===")
seg.run_segmented_evaluation(
    backend=single.VAEBackend(eval_seed_offset=950_000),
    model_label="VAE (clean-only, contam_0pct)",
    model_dir_desc="phase3_vae/05_contamination_sweep/04_models/contam_0pct",
    results_md=os.path.join(OUT_ROOT, "vae", "block_recall_f1.md"),
    results_csv=os.path.join(OUT_ROOT, "vae", "block_recall_f1_per_seed.csv"),
    plot_path=os.path.join(OUT_ROOT, "vae", "error_plot.png"),
    comparison_recall_csv=os.path.join(ATTACK_TYPE_DIR, "results_single_attack_type.csv"),
)

print("=== Dense v1 (5 seeds) ===")
seg.run_segmented_evaluation(
    backend=DEFAULT_DENSE_BACKEND,
    model_label=DENSE_LABEL,
    model_dir_desc=DENSE_DIR_DESC,
    results_md=os.path.join(OUT_ROOT, "dense_v1", "block_recall_f1.md"),
    results_csv=os.path.join(OUT_ROOT, "dense_v1", "block_recall_f1_per_seed.csv"),
    plot_path=os.path.join(OUT_ROOT, "dense_v1", "error_plot.png"),
    comparison_recall_csv=os.path.join(DENSE_DIR, "results_single_attack_type_dense.csv"),
)
print("done")
