# Clean-only (0% contamination) VAE, evaluated per attack type

Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (20 seeds, threshold_95 per seed, inference only, no retraining).

Each row = that attack type's flows vs. the full test-split benign set only (other attack types excluded from that run). Mean +/- std across 20 seeds.

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 6821 | 1487 | 0.5815 +/- 0.0768 | 0.2133 +/- 0.0219 | 0.0507 +/- 0.0081 | 0.0565 +/- 0.0059 | 0.0328 +/- 0.0055 |
| portscan | 6821 | 694 | 0.9982 +/- 0.0005 | 0.9886 +/- 0.0023 | 0.7737 +/- 0.0161 | 0.0578 +/- 0.0056 | 0.9889 +/- 0.0138 |
| slowloris | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8271 +/- 0.0158 | 0.0570 +/- 0.0062 | 1.0000 +/- 0.0000 |
