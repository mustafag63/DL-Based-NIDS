"""
Evidence table for audit finding O6 (11_fable_review/independent_audit.md):
the benign-gap FPR differences in the segmented-injection stream
(0.032 / 0.036 / 0.093 / 0.069) were previously interpreted as small-sample
noise. That cannot be right: at n ~= 1705 per gap the binomial std of an
FPR around 0.05 is ~0.005, and the pattern survived unchanged when the
deterministic z_mean score removed all scoring noise.

The actual mechanism sits in build_segmented_injection.py: the benign pool
is split into contiguous, near-equal gaps IN ts ORDER, and the capture
windows are consecutive in time -- so each gap holds a different mix of
windows' benign flows. This script makes that visible:

  1. segment x window composition of every segment in
     segmented_sequence.csv (counts + row %),
  2. per-window benign FPR (deterministic z_mean, mean +/- std over the 20
     contam_0pct seeds, each seed at its own recomputed threshold_95 -- the
     same convention as the segmented evaluation itself),
  3. a check column: each benign gap's FPR reconstructed as the
     composition-weighted average of the per-window FPRs, next to the FPR
     measured directly on the gap. The reconstruction is approximate, not
     exact: window FPRs are computed over each window's FULL benign set,
     while a gap holds a contiguous ts-slice of a window, so within-window
     temporal variation leaves small residuals (<= ~0.008 here). The
     gap-to-gap ordering and magnitude are reproduced, which is the point:
     the spread tracks which windows each gap contains.

Outputs (03_segmented_injection/vae/):
  segment_window_composition.csv  -- long-format segment x window rows
  segment_window_composition.md   -- the three tables + interpretation
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.dirname(os.path.dirname(HERE))
PROJECT_ROOT = os.path.dirname(REPORT_DIR)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
SEGMENTED_DIR = os.path.join(PROJECT_ROOT, "07_segmented_injection")

sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402

SEQUENCE_PATH = os.path.join(SEGMENTED_DIR, "segmented_sequence.csv")
OUT_DIR = os.path.join(REPORT_DIR, "03_segmented_injection", "vae")
OUT_CSV = os.path.join(OUT_DIR, "segment_window_composition.csv")
OUT_MD = os.path.join(OUT_DIR, "segment_window_composition.md")


def main():
    feature_cols = single.load_feature_cols()
    seq = pd.read_csv(SEQUENCE_PATH)
    combined = single.build_combined_features()
    features = combined.loc[seq["row_index"].values, feature_cols].reset_index(drop=True)
    check = combined.loc[seq["row_index"].values, ["window_id", "ts", "is_attack"]].reset_index(drop=True)
    assert (check["window_id"].values == seq["window_id"].values).all()
    assert (check["is_attack"].values == seq["is_attack"].values).all()
    df = pd.concat([seq, features], axis=1)

    # --- per-flow flag rate across the 20 deterministic seeds ---
    backend = single.VAEBackend(deterministic=True)
    X = df[feature_cols].values.astype("float32")
    error_matrix, thresholds = single.compute_error_matrix(X, backend=backend)
    pred = (error_matrix > np.array(thresholds)[:, None]).astype(float)  # (n_seeds, n_flows)

    benign = df["is_attack"] == 0

    # --- table 1: segment x window composition (all segments) ---
    comp = (df.groupby(["segment_id", "segment_label", "window_id"]).size()
              .rename("n").reset_index())
    seg_totals = comp.groupby("segment_id")["n"].transform("sum")
    comp["pct_of_segment"] = (100 * comp["n"] / seg_totals).round(1)
    comp.to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_CSV}")

    # --- table 2: per-window benign FPR (deterministic, mean +/- std over seeds) ---
    win_rows = []
    for w, g in df[benign].groupby("window_id"):
        idx = g.index.values
        per_seed_fpr = pred[:, idx].mean(axis=1)
        win_rows.append({"window_id": w, "n_benign": len(idx),
                         "fpr_mean": per_seed_fpr.mean(), "fpr_std": per_seed_fpr.std()})
    win_fpr = pd.DataFrame(win_rows).sort_values("window_id").set_index("window_id")

    # --- table 3: benign gaps -- measured FPR vs composition-weighted FPR ---
    gap_rows = []
    for seg_id, g in df[benign].groupby("segment_id"):
        idx = g.index.values
        per_seed_fpr = pred[:, idx].mean(axis=1)
        weights = g["window_id"].value_counts(normalize=True)
        weighted = float((weights * win_fpr.loc[weights.index, "fpr_mean"]).sum())
        gap_rows.append({"segment_id": seg_id, "n": len(idx),
                         "fpr_measured": per_seed_fpr.mean(),
                         "fpr_composition_weighted": weighted,
                         "windows": ", ".join(f"{w} {100*p:.0f}%" for w, p in weights.items())})
    gaps = pd.DataFrame(gap_rows).sort_values("segment_id")

    lines = [
        "# Segment x window kompozisyonu — benign-gap FPR farklarının kaynağı (O6 kanıtı)",
        "",
        "`build_segmented_injection.py` benign havuzunu **ts sırasına göre** bitişik,",
        "yakın-eşit parçalara böler; capture window'ları zamanda ardışık olduğundan her",
        "benign gap **farklı window'ların** benign flow'larını içerir. Aşağıdaki tablolar,",
        "gap'ler arası FPR farkının (0.032 / 0.036 / 0.093 / 0.069) örnekleme gürültüsü",
        "değil, bu kompozisyon farkının sistematik sonucu olduğunu gösterir.",
        "(Skor: deterministik z_mean, 20 seed, seed başına val-benign'den yeniden",
        "hesaplanan threshold_95 — segmented değerlendirmenin kendisiyle aynı konvansiyon.)",
        "",
        "## 1. Segment x window kompozisyonu",
        "",
        "| segment_id | segment_label | window_id | n | segment'in %'si |",
        "|---|---|---|---|---|",
    ]
    for _, r in comp.iterrows():
        lines.append(f"| {int(r['segment_id'])} | {r['segment_label']} | {r['window_id']} "
                     f"| {int(r['n'])} | {r['pct_of_segment']:.1f} |")

    lines += [
        "",
        "## 2. Window başına benign FPR (deterministik, 20 seed ort. ± std)",
        "",
        "| window_id | n_benign | FPR |",
        "|---|---|---|",
    ]
    for w, r in win_fpr.iterrows():
        lines.append(f"| {w} | {int(r['n_benign'])} | {r['fpr_mean']:.4f} +/- {r['fpr_std']:.4f} |")

    lines += [
        "",
        "## 3. Benign gap'ler: ölçülen FPR vs kompozisyon-ağırlıklı FPR",
        "",
        "Her gap'in FPR'si, içerdiği window'ların (tüm-window) FPR'lerinin",
        "flow-sayısı-ağırlıklı ortalamasıyla yeniden kurulur. Eşleşme yaklaşıktır",
        "(gap bir window'un bitişik ts-dilimini içerir, window FPR'si ise window'un",
        "tamamından hesaplanır; window-içi zamansal varyasyon ≤~0.008'lik artıklar",
        "bırakır) — ama gap'ler arası sıralama ve büyüklük birebir yeniden üretilir,",
        "yani fark 'hangi gap hangi window'ları içeriyor' sorusuna indirgenir:",
        "",
        "| segment_id | n | FPR (ölçülen) | FPR (kompozisyon-ağırlıklı) | kompozisyon |",
        "|---|---|---|---|---|",
    ]
    for _, r in gaps.iterrows():
        lines.append(f"| {int(r['segment_id'])} | {int(r['n'])} | {r['fpr_measured']:.4f} "
                     f"| {r['fpr_composition_weighted']:.4f} | {r['windows']} |")

    fpr_lo, fpr_hi = win_fpr["fpr_mean"].min(), win_fpr["fpr_mean"].max()
    lines += [
        "",
        "## Yorum",
        "",
        f"Window'lar arası benign FPR {fpr_lo:.4f}–{fpr_hi:.4f} aralığında — gap'ler arası",
        "farkın tamamını üretecek genişlikte. n≈1705'lik bir gap'te FPR≈0.05'in binom",
        "std'si ~0.005'tir; gözlenen 0.032→0.093 farkı örnekleme gürültüsüyle açıklanamaz.",
        "Deterministik z_mean skoru skorlama gürültüsünü tamamen kaldırdığı hâlde desenin",
        "aynen korunması da (bkz. `../../deterministic_vs_stochastic_comparison.md`) aynı",
        "sonucu bağımsız olarak doğrular: **fark sistematiktir ve ts-sıralı bölünmenin",
        "yarattığı window kompozisyonundan gelir; model 'drift' etmiyor, örneklem",
        "gürültüsü de değil.**",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT_MD}")
    print("\n" + gaps.to_string(index=False))
    print("\nPer-window benign FPR:")
    print(win_fpr.to_string())


if __name__ == "__main__":
    main()
