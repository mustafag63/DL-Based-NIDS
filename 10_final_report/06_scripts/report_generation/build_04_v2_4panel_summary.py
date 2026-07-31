"""
Same 4-panel (PR-AUC / F1 / Benign FPR / Attack Recall, mean +/- std) attack-type
summary as build_04_v1_4panel_summary.py, but for v2 (19-feature, +concurrency_src_1s,
5-seed) Dense and VAE, using the numbers already in
10_final_report/01_single_attack_type/{dense,vae}/results.md.

Writes 06_attack_type_summary_4panel.png into each of
04_model_notebooks_results/{dense_v2,vae_v2}/ and links it from results.md.
"""
import os
import sys

import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "04_model_notebooks_results")

sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

ATTACK_TYPES = ["apache_bench", "portscan", "slowloris"]

# From 10_final_report/01_single_attack_type/{dense,vae}/results.md (5-seed, 19-feature v2).
DENSE_V2 = {
    "n_seeds": 5,
    "pr_auc":       {"apache_bench": (0.8930, 0.0511), "portscan": (0.9973, 0.0013), "slowloris": (1.0000, 0.0000)},
    "f1":           {"apache_bench": (0.8218, 0.0188), "portscan": (0.7551, 0.0100), "slowloris": (0.8050, 0.0085)},
    "benign_fpr":   {"apache_bench": (0.0660, 0.0036), "portscan": (0.0660, 0.0036), "slowloris": (0.0660, 0.0036)},
    "attack_recall":{"apache_bench": (0.9092, 0.0382), "portscan": (1.0000, 0.0000), "slowloris": (1.0000, 0.0000)},
}
VAE_V2 = {
    "n_seeds": 5,
    "pr_auc":       {"apache_bench": (0.9035, 0.0805), "portscan": (0.9983, 0.0006), "slowloris": (1.0000, 0.0000)},
    "f1":           {"apache_bench": (0.8428, 0.0337), "portscan": (0.7551, 0.0309), "slowloris": (0.8048, 0.0262)},
    "benign_fpr":   {"apache_bench": (0.0664, 0.0110), "portscan": (0.0664, 0.0110), "slowloris": (0.0664, 0.0110)},
    "attack_recall":{"apache_bench": (0.9500, 0.0453), "portscan": (1.0000, 0.0000), "slowloris": (1.0000, 0.0000)},
}

PANELS = [
    ("pr_auc", "PR-AUC"),
    ("f1", "F1 (threshold_95)"),
    ("benign_fpr", "Benign FPR (threshold_95)"),
    ("attack_recall", "Attack Recall (threshold_95)"),
]


def make_figure(model_name, data, color, out_path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    for ax, (key, title) in zip(axes.flat, PANELS):
        means = [data[key][t][0] for t in ATTACK_TYPES]
        stds = [data[key][t][1] for t in ATTACK_TYPES]
        bars = ax.bar(ATTACK_TYPES, means, yerr=stds, capsize=6, color=color, width=0.55)
        for b, m in zip(bars, means):
            ax.text(b.get_x() + b.get_width() / 2, m + max(means) * 0.03, f"{m:.3f}",
                    ha="center", fontsize=10)
        ax.set_title(title)
        ax.set_ylim(0, max(means) * 1.25 if max(means) > 0 else 1)
        plt.setp(ax.get_xticklabels(), rotation=10)
    fig.suptitle(f"{model_name} — per attack-type, {data['n_seeds']}-seed mean +/- std\n"
                 "(threshold_95 = val-benign 95th percentile; benign FPR is one number per model, same across columns)",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def append_ref(out_dir, png_name):
    md_path = os.path.join(out_dir, "results.md")
    with open(md_path) as f:
        content = f.read()
    marker = "![Attack-type 4-panel summary]"
    if marker in content:
        return
    content = content.rstrip("\n") + f"\n\n## Attack-type 4-panel summary\n\n{marker}({png_name})\n"
    with open(md_path, "w") as f:
        f.write(content)
    print(f"linked into {md_path}")


make_figure("Dense autoencoder v2 (full_features + concurrency_src_1s, 19 feature)", DENSE_V2, sty.COLOR_DENSE,
            os.path.join(OUT_ROOT, "dense_v2", "06_attack_type_summary_4panel.png"))
append_ref(os.path.join(OUT_ROOT, "dense_v2"), "06_attack_type_summary_4panel.png")

make_figure("VAE v2 (contam_0pct, 19 feature: +concurrency_src_1s, deterministic z_mean)", VAE_V2, sty.COLOR_VAE,
            os.path.join(OUT_ROOT, "vae_v2", "06_attack_type_summary_4panel.png"))
append_ref(os.path.join(OUT_ROOT, "vae_v2"), "06_attack_type_summary_4panel.png")

print("done")
