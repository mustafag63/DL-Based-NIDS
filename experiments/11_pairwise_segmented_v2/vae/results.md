# VAE v2 (contam_0pct, 19 features: +concurrency_src_1s, deterministic z_mean), evaluated per pairwise attack-type combination

Model: `phase3_vae/05_contamination_sweep/04_models_v2/contam_0pct` (5 seeds, threshold_95 per seed, inference only, no retraining).

Each row = both listed attack types' flows vs. the full test-split benign set (the third attack type is excluded from that run). Mean +/- std across 5 seeds.

| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95, pooled) |
|---|---|---|---|---|---|---|---|
| portscan+apache_bench | 6821 | 2181 | 0.9887 +/- 0.0084 | 0.9641 +/- 0.0288 | 0.8888 +/- 0.0238 | 0.0664 +/- 0.0110 | 0.9659 +/- 0.0309 |
| portscan+slowloris | 6821 | 1623 | 0.9999 +/- 0.0000 | 0.9997 +/- 0.0001 | 0.8779 +/- 0.0178 | 0.0664 +/- 0.0110 | 1.0000 +/- 0.0000 |
| apache_bench+slowloris | 6821 | 2416 | 0.9899 +/- 0.0076 | 0.9715 +/- 0.0228 | 0.8989 +/- 0.0216 | 0.0664 +/- 0.0110 | 0.9692 +/- 0.0279 |

## apache_bench decomposed (own-flows-only) recall: solo vs. paired

Per-flow decision (errors > thr95) does not depend on which other flows share the eval set, so apache_bench's own recall is expected to match the solo number up to seed-sampling noise -- checked explicitly here, not assumed.

| evaluation set | apache_bench-only recall |
|---|---|
| apache_bench (solo) | 0.9500 +/- 0.0453 |
| portscan+apache_bench (pair) | 0.9500 +/- 0.0453 |
| apache_bench+slowloris (pair) | 0.9500 +/- 0.0453 |
