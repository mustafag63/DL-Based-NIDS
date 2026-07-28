# Dense autoencoder v1 (full_features), evaluated per pairwise attack-type combination

Model: `phase3_dense/04_phase3_models/full_features` (5 seeds, threshold_95 = 95th percentile of val-benign reconstruction error per seed, inference only, no retraining).

| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| portscan+apache_bench | 6821 | 2181 | 0.7921 +/- 0.0539 | 0.6023 +/- 0.0370 | 0.4375 +/- 0.0069 | 0.0615 +/- 0.0023 | 0.3339 +/- 0.0049 |
| portscan+slowloris | 6821 | 1623 | 0.9995 +/- 0.0003 | 0.9981 +/- 0.0008 | 0.8840 +/- 0.0068 | 0.0615 +/- 0.0023 | 0.9970 +/- 0.0066 |
| apache_bench+slowloris | 6821 | 2416 | 0.8127 +/- 0.0487 | 0.6663 +/- 0.0344 | 0.5090 +/- 0.0021 | 0.0615 +/- 0.0023 | 0.4007 +/- 0.0000 |
