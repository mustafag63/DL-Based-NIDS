# V2 (deconfounded) contamination 4% — deterministic z_mean, 20 seeds

Pipeline: `prepare_contamination_data_v2.py` (K2: signature-grouped window_10 split; K1: test benign = 70% window_10 + 30% window_02-08, equal per-window shares). Architecture/hyperparameters identical to the original sweep (latent=10, beta=0.25). threshold_95 = 95th pctl of deterministic error on val_benign_v2.csv, per seed.

| metric | mean | std |
|---|---|---|
| threshold_95 | 0.2500 | 0.1136 |
| pr_auc | 0.6529 | 0.0393 |
| roc_auc | 0.8098 | 0.0406 |
| f1 | 0.6507 | 0.0564 |
| benign_fpr | 0.0355 | 0.0153 |
| attack_recall | 0.6342 | 0.0583 |
| fpr_w10 | 0.0308 | 0.0145 |
| fpr_0208 | 0.0463 | 0.0214 |
