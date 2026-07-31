# VAE (contam_0pct, 19 features: +concurrency_src_1s, deterministic z_mean), evaluated per attack type

Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (5 seeds, threshold_95 = 95th percentile of DETERMINISTIC (z_mean) val-benign reconstruction error per seed, inference only).

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 6821 | 1487 | 0.9836 +/- 0.0123 | 0.9035 +/- 0.0805 | 0.8428 +/- 0.0337 | 0.0664 +/- 0.0110 | 0.9500 +/- 0.0453 |
| portscan | 6821 | 694 | 0.9998 +/- 0.0001 | 0.9983 +/- 0.0006 | 0.7551 +/- 0.0309 | 0.0664 +/- 0.0110 | 1.0000 +/- 0.0000 |
| slowloris | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8048 +/- 0.0262 | 0.0664 +/- 0.0110 | 1.0000 +/- 0.0000 |
