"""
Robustluk duzeltmesi (kullanici sarti #1) once byte_ratio_var_src ailesi icin:
raw degerler zaten log1p'den gecmisti (build_concurrency_features.py) ama
KS=1.0 hala duruyordu -- asagida gorulecegi gibi bu bir outlier/kuyruk sorunu
degil, apache_bench komsuluklarinin TAMAMININ sistemik olarak yuksek varyansli
olmasi (bkz. README, "byte_ratio_var: mixed-attack-type confound" bolumu).
Yine de talep edilen iki duzeltme de uygulanip KS yeniden olculuyor:

  1. winsorize: raw degerler, BENIGN TRAIN split'inin 1. ve 99. persentiline
     kirpiliyor (leakage-free -- persentiller sadece benign train'den).
  2. log1p(winsorized) -> StandardScaler (yine benign train'e fit).

Ciktilar: concurrency_features_all_rows.csv'ye
byte_ratio_var_src_{r}s_wins_log_scaled kolonlari eklenir (var olan dosya
guncellenir, diger kolonlara dokunulmaz).
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DENSE_TRAIN_IDX = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits", "train_indices.csv")
FEAT_CSV = os.path.join(HERE, "concurrency_features_all_rows.csv")

RADII_TAGS = ["1s", "2s", "5s"]

df = pd.read_csv(FEAT_CSV)
train_idx = pd.read_csv(DENSE_TRAIN_IDX)
assert (train_idx["is_attack"] == 0).all()
train_mask = df["row_index"].isin(train_idx["row_index"].values)

for tag in RADII_TAGS:
    raw_col = f"byte_ratio_var_src_{tag}"
    lo, hi = df.loc[train_mask, raw_col].quantile([0.01, 0.99])
    print(f"{raw_col}: benign-train p1={lo:.4f} p99={hi:.4f}  "
          f"(pre-clip full-col min={df[raw_col].min():.2f} max={df[raw_col].max():.2f})")
    clipped = df[raw_col].clip(lo, hi)
    logc = np.log1p(clipped)
    mu = float(logc[train_mask].mean())
    sigma = float(logc[train_mask].std(ddof=0)) or 1.0
    df[f"{raw_col}_wins_log_scaled"] = (logc - mu) / sigma

df.to_csv(FEAT_CSV, index=False)
print(f"\nUpdated {FEAT_CSV} with winsorized+log+scaled byte_ratio_var_src columns")
