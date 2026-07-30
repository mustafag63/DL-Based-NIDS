# Clean-only (0% contamination) VAE, evaluated per pairwise attack-type combination

Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (20 seeds, threshold_95 per seed, inference only, no retraining).

Each row = both listed attack types' flows vs. the full test-split benign set (the third attack type is excluded from that run). Mean +/- std across 20 seeds.

| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| portscan+apache_bench | 6821 | 2181 | 0.7135 +/- 0.0527 | 0.5598 +/- 0.0232 | 0.4447 +/- 0.0070 | 0.0571 +/- 0.0053 | 0.3369 +/- 0.0061 |
| portscan+slowloris | 6821 | 1623 | 0.9993 +/- 0.0002 | 0.9975 +/- 0.0007 | 0.8905 +/- 0.0105 | 0.0572 +/- 0.0065 | 0.9953 +/- 0.0057 |
| apache_bench+slowloris | 6821 | 2416 | 0.7427 +/- 0.0474 | 0.6283 +/- 0.0219 | 0.5170 +/- 0.0054 | 0.0567 +/- 0.0056 | 0.4044 +/- 0.0029 |
