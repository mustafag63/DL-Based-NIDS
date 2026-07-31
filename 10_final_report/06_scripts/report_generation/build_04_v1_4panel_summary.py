"""
User showed a 2x2-panel figure (PR-AUC / F1 / Benign FPR / Attack Recall,
mean +/- std) from the VAE contamination sweep and asked for dense_v1 and
vae_v1's model_notebooks_results to get a similar 4-panel summary. Neither
v1 notebook has a contamination-style sweep, so the agreed x-axis is
attack_type (portscan / apache_bench / slowloris) instead of train
contamination % -- values come straight from the already-computed v1
canonical tables (Dense: 5-seed, VAE: 20-seed, V1_ARCHIVE 18-feature
weights), not recomputed here. Bars (not a connected line) since attack_type
is categorical/unordered, unlike the screenshot's continuous contamination
axis.

Writes 06_attack_type_summary_4panel.png into each of
04_model_notebooks_results/{dense_v1,vae_v1}/ and links it from results.md.
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = "/Users/mustafa/Desktop/NIDS/IDS-Project"
OUT_ROOT = os.path.join(PROJECT_ROOT, "10_final_report", "04_model_notebooks_results")

sys.path.insert(0, HERE)
import report_style as sty  # noqa: E402
sty.apply()

ATTACK_TYPES = ["apache_bench", "portscan", "slowloris"]

# Straight from V1_ARCHIVE/10_final_report/01_single_attack_type/{dense_v1,vae}/results.md
# (Dense: 5-seed, VAE: 20-seed, both 18-feature v1 canonical threshold_95 tables).
DENSE_V1 = {
    "n_seeds": 5,
    "pr_auc":       {"apache_bench": (0.2704, 0.0406), "portscan": (0.9912, 0.0032), "slowloris": (1.0000, 0.0000)},
    "f1":           {"apache_bench": (0.0401, 0.0003), "portscan": (0.7645, 0.0135), "slowloris": (0.8157, 0.0055)},
    "benign_fpr":   {"apache_bench": (0.0615, 0.0023), "portscan": (0.0615, 0.0023), "slowloris": (0.0615, 0.0023)},
    "attack_recall":{"apache_bench": (0.0262, 0.0000), "portscan": (0.9931, 0.0155), "slowloris": (1.0000, 0.0000)},
}
VAE_V1 = {
    "n_seeds": 20,
    "pr_auc":       {"apache_bench": (0.2244, 0.0349), "portscan": (0.9921, 0.0023), "slowloris": (1.0000, 0.0000)},
    "f1":           {"apache_bench": (0.0410, 0.0011), "portscan": (0.7689, 0.0195), "slowloris": (0.7986, 0.0169)},
    "benign_fpr":   {"apache_bench": (0.0577, 0.0058), "portscan": (0.0577, 0.0058), "slowloris": (0.0577, 0.0058)},
    "attack_recall":{"apache_bench": (0.0262, 0.0000), "portscan": (0.9983, 0.0077), "slowloris": (1.0000, 0.0000)},
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
    marker = f"![Attack-type 4-panel summary]"
    if marker in content:
        return
    content = content.rstrip("\n") + f"\n\n## Attack-type 4-panel summary\n\n{marker}({png_name})\n"
    with open(md_path, "w") as f:
        f.write(content)
    print(f"linked into {md_path}")


make_figure("Dense autoencoder v1 (full_features, 18 feature)", DENSE_V1, sty.COLOR_DENSE,
            os.path.join(OUT_ROOT, "dense_v1", "06_attack_type_summary_4panel.png"))
append_ref(os.path.join(OUT_ROOT, "dense_v1"), "06_attack_type_summary_4panel.png")

make_figure("VAE v1 (contam_0pct, 18 feature, deterministic z_mean)", VAE_V1, sty.COLOR_VAE,
            os.path.join(OUT_ROOT, "vae_v1", "06_attack_type_summary_4panel.png"))
append_ref(os.path.join(OUT_ROOT, "vae_v1"), "06_attack_type_summary_4panel.png")

print("done")
