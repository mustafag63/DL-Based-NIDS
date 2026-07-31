"""Step 1: intrinsic dimensionality of the 18-feature space (reference line for
how many latent dims a VAE could reasonably be expected to use), plus a
one-hot column correlation check.

Reads window10_clean_train.csv (the VAE's clean-benign train set) - the
same features/scaling the VAE trains on, so PCA is comparable to the VAE's
own latent space.

Writes only into 09_collapse_investigation/ - no other file touched.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.decomposition import PCA

BASE = Path(__file__).resolve().parent.parent  # phase3_vae/
TRAIN_PATH = BASE / "window10_clean_train.csv"
OUT_DIR = Path(__file__).resolve().parent

FEATURE_COLS = [
    "duration_scaled", "orig_bytes_scaled", "resp_bytes_scaled",
    "orig_pkts_scaled", "resp_pkts_scaled",
    "bytes_per_sec_scaled", "pkts_per_sec_scaled", "byte_ratio_scaled",
    "proto_tcp", "proto_udp",
    "service_dns", "service_http", "service_none", "service_ssh",
    "conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF",
]
ONEHOT_GROUPS = {
    "proto": ["proto_tcp", "proto_udp"],
    "service": ["service_dns", "service_http", "service_none", "service_ssh"],
    "conn_state": ["conn_state_REJ", "conn_state_RSTO", "conn_state_S1", "conn_state_SF"],
}


def main():
    df = pd.read_csv(TRAIN_PATH)
    assert (df["is_attack"] == 0).all()
    X = df[FEATURE_COLS].values.astype("float64")
    print(f"train rows: {len(df)}, features: {X.shape[1]}")

    # ---- PCA on all 18 features (as fed to the VAE) ----
    pca = PCA(n_components=X.shape[1])
    pca.fit(X)
    explained = pca.explained_variance_ratio_
    cum = np.cumsum(explained)

    thresholds = [0.90, 0.95, 0.99]
    n_for_threshold = {t: int(np.searchsorted(cum, t) + 1) for t in thresholds}
    for t in thresholds:
        print(f"components for {int(t*100)}% variance: {n_for_threshold[t]}")

    pca_table = pd.DataFrame({
        "component": np.arange(1, len(explained) + 1),
        "explained_variance_ratio": explained,
        "cumulative_variance_ratio": cum,
    })
    pca_table.to_csv(OUT_DIR / "pca_explained_variance.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(pca_table["component"], pca_table["cumulative_variance_ratio"], marker="o")
    for t in thresholds:
        ax.axhline(t, color="gray", linestyle="--", linewidth=0.8)
        ax.annotate(f"{int(t*100)}% @ n={n_for_threshold[t]}",
                    xy=(n_for_threshold[t], t), xytext=(n_for_threshold[t] + 0.3, t - 0.04))
    ax.set_xlabel("number of principal components")
    ax.set_ylabel("cumulative explained variance ratio")
    ax.set_title("PCA cumulative explained variance - window10_clean_train (18 features)")
    ax.set_xticks(pca_table["component"])
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "pca_cumulative_variance.png", dpi=130)
    print(f"Saved: {OUT_DIR / 'pca_cumulative_variance.png'}, {OUT_DIR / 'pca_explained_variance.csv'}")

    # ---- One-hot group correlation / redundancy check ----
    corr = df[FEATURE_COLS].corr()
    corr.to_csv(OUT_DIR / "feature_correlation_matrix.csv")

    redundancy_notes = []
    # Within-group: one-hot columns of the same categorical are structurally
    # anti-correlated (they sum to <=1 per row) - expected, not "redundant"
    # in the collapse sense. Flag pairs (same group or cross-group) with
    # |corr| > 0.8 as candidates for artificially shrinking intrinsic dim.
    all_onehot = sum(ONEHOT_GROUPS.values(), [])
    high_corr_pairs = []
    for i, c1 in enumerate(all_onehot):
        for c2 in all_onehot[i + 1:]:
            r = corr.loc[c1, c2]
            if abs(r) > 0.8:
                high_corr_pairs.append((c1, c2, r))
    for c1, c2, r in high_corr_pairs:
        redundancy_notes.append(f"|corr|>0.8: {c1} vs {c2} = {r:.3f}")

    # Also check numeric features for near-duplicate pairs (e.g. bytes_per_sec vs pkts_per_sec)
    numeric_cols = [c for c in FEATURE_COLS if c not in all_onehot]
    high_corr_numeric = []
    for i, c1 in enumerate(numeric_cols):
        for c2 in numeric_cols[i + 1:]:
            r = corr.loc[c1, c2]
            if abs(r) > 0.8:
                high_corr_numeric.append((c1, c2, r))
    for c1, c2, r in high_corr_numeric:
        redundancy_notes.append(f"|corr|>0.8 (numeric): {c1} vs {c2} = {r:.3f}")

    print("\nHigh-correlation (|r|>0.8) pairs found:")
    if redundancy_notes:
        for n in redundancy_notes:
            print(" ", n)
    else:
        print("  none")

    with open(OUT_DIR / "correlation_notes.txt", "w") as f:
        f.write("High-correlation (|r|>0.8) feature pairs (redundancy candidates):\n")
        if redundancy_notes:
            f.write("\n".join(redundancy_notes) + "\n")
        else:
            f.write("none\n")
        f.write(f"\nPCA components needed: 90%={n_for_threshold[0.90]}, "
                f"95%={n_for_threshold[0.95]}, 99%={n_for_threshold[0.99]} (of 18 total)\n")

    print(f"\nSaved: {OUT_DIR / 'feature_correlation_matrix.csv'}, {OUT_DIR / 'correlation_notes.txt'}")


if __name__ == "__main__":
    main()
