# V2 (deconfounded) contamination 0% — deterministic z_mean, 20 seeds

Pipeline: `prepare_contamination_data_v2.py` (K2: signature-grouped window_10 split; K1: test benign = 70% window_10 + 30% window_02-08, equal per-window shares). Architecture/hyperparameters identical to the original sweep (latent=10, beta=0.25). threshold_95 = 95th pctl of deterministic error on val_benign_v2.csv, per seed.

| metric | mean | std |
|---|---|---|
| threshold_95 | 0.1215 | 0.0391 |
| pr_auc | 0.7516 | 0.0281 |
| roc_auc | 0.8961 | 0.0504 |
| f1 | 0.7041 | 0.0223 |
| benign_fpr | 0.0256 | 0.0076 |
| attack_recall | 0.6673 | 0.0093 |
| fpr_w10 | 0.0204 | 0.0071 |
| fpr_0208 | 0.0375 | 0.0149 |
