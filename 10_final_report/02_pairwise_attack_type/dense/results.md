# Dense autoencoder v2 (full_features + concurrency_src_1s), evaluated per pairwise attack-type combination

Model: `phase3_dense/05_phase3_models_v2/full_features_v2` (5 seeds, threshold_95 per seed, inference only, no retraining).

Each row = both listed attack types' flows vs. the full test-split benign set (the third attack type is excluded from that run). Mean +/- std across 5 seeds.

| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95, pooled) |
|---|---|---|---|---|---|---|---|
| portscan+apache_bench | 6821 | 2181 | 0.9868 +/- 0.0052 | 0.9587 +/- 0.0181 | 0.8747 +/- 0.0125 | 0.0660 +/- 0.0036 | 0.9381 +/- 0.0261 |
| portscan+slowloris | 6821 | 1623 | 0.9999 +/- 0.0001 | 0.9995 +/- 0.0003 | 0.8782 +/- 0.0058 | 0.0660 +/- 0.0036 | 1.0000 +/- 0.0000 |
| apache_bench+slowloris | 6821 | 2416 | 0.9882 +/- 0.0046 | 0.9672 +/- 0.0141 | 0.8862 +/- 0.0113 | 0.0660 +/- 0.0036 | 0.9441 +/- 0.0235 |

## apache_bench decomposed (own-flows-only) recall: solo vs. paired

Per-flow decision (errors > thr95) does not depend on which other flows share the eval set, so apache_bench's own recall is expected to match the solo number up to seed-sampling noise -- checked explicitly here, not assumed.

| evaluation set | apache_bench-only recall |
|---|---|
| apache_bench (solo) | 0.9092 +/- 0.0382 |
| portscan+apache_bench (pair) | 0.9092 +/- 0.0382 |
| apache_bench+slowloris (pair) | 0.9092 +/- 0.0382 |
