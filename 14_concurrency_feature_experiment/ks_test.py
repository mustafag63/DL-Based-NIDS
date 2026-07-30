"""
Adim 2: retrain'e gecmeden once ucuz KS-test kontrolu. Her 9 yeni
(log-transform + benign-train-fit scaled) feature icin apache_bench vs
benign KS istatistigi, test_with_attack_type.csv uzerinde (tam flow seti,
13'teki seyrek-alt-kume artefaktini tekrarlamamak icin
concurrency_features_all_rows.csv row_index ile birebir merge edilerek).
"""
import os

import pandas as pd
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

feat = pd.read_csv(os.path.join(HERE, "concurrency_features_all_rows.csv"))
lab = pd.read_csv(os.path.join(PROJECT_ROOT, "06_attack_type_analysis", "test_with_attack_type.csv"))
m = lab.merge(feat, on="row_index", suffixes=("", "_feat"))
assert (m["window_id"] == m["window_id_feat"]).all()
assert (m["is_attack"] == m["is_attack_feat"]).all()

scaled_cols = [c for c in feat.columns if c.endswith("_scaled")]

rows = []
for c in scaled_cols:
    for atype in ["apache_bench", "portscan", "slowloris"]:
        b = m.loc[m["attack_type"] == "benign", c]
        a = m.loc[m["attack_type"] == atype, c]
        stat, p = ks_2samp(b, a)
        shift = float((a.mean() - b.mean()) / b.std())
        rows.append({"feature": c, "attack_type": atype, "ks_stat": stat, "ks_p": p,
                     "mean_shift_benign_std": shift, "n_attack": len(a)})

res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "ks_results.csv"), index=False)

print("\n=== apache_bench KS, sorted descending ===")
ab = res[res.attack_type == "apache_bench"].sort_values("ks_stat", ascending=False)
print(ab[["feature", "ks_stat", "ks_p", "mean_shift_benign_std"]].to_string(index=False))

print("\nReference points:")
print("  best 18-feature (orig_pkts_scaled etc.):        KS ~= 0.62-0.76")
print("  13_temporal_feature_experiment IAT (KS):         0.375")
print(f"  concurrency best (apache_bench):                 {ab['ks_stat'].max():.4f}  ({ab.iloc[0]['feature']})")

print("\n=== portscan / slowloris KS, sorted descending (context) ===")
for atype in ["portscan", "slowloris"]:
    sub = res[res.attack_type == atype].sort_values("ks_stat", ascending=False).head(3)
    print(f"-- {atype} --")
    print(sub[["feature", "ks_stat", "mean_shift_benign_std"]].to_string(index=False))
