# Dense autoencoder v1 (full_features), evaluated per attack type

Model: `phase3_dense/04_phase3_models/full_features` (5 seeds, threshold_95 = 95th percentile of val-benign reconstruction error per seed, inference only, no retraining).

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 6821 | 1487 | 0.6957 +/- 0.0791 | 0.2704 +/- 0.0406 | 0.0401 +/- 0.0003 | 0.0615 +/- 0.0023 | 0.0262 +/- 0.0000 |
| portscan | 6821 | 694 | 0.9988 +/- 0.0007 | 0.9912 +/- 0.0032 | 0.7645 +/- 0.0135 | 0.0615 +/- 0.0023 | 0.9931 +/- 0.0155 |
| slowloris | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8157 +/- 0.0055 | 0.0615 +/- 0.0023 | 1.0000 +/- 0.0000 |
