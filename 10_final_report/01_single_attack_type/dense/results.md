# Dense autoencoder (full_features + concurrency_src_1s), evaluated per attack type

Model: `phase3_dense/04_phase3_models/full_features` (5 seeds, threshold_95 = 95th percentile of val-benign reconstruction error per seed, inference only, no retraining).

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 6821 | 1487 | 0.9808 +/- 0.0076 | 0.8930 +/- 0.0511 | 0.8218 +/- 0.0188 | 0.0660 +/- 0.0036 | 0.9092 +/- 0.0382 |
| portscan | 6821 | 694 | 0.9997 +/- 0.0002 | 0.9973 +/- 0.0013 | 0.7551 +/- 0.0100 | 0.0660 +/- 0.0036 | 1.0000 +/- 0.0000 |
| slowloris | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8050 +/- 0.0085 | 0.0660 +/- 0.0036 | 1.0000 +/- 0.0000 |
