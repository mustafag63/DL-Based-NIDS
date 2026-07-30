# Clean-only (0% contamination) VAE, evaluated per pairwise attack-type combination

Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (20 seeds, threshold_95 per seed, inference only, no retraining).

Each row = both listed attack types' flows vs. the full test-split benign set (the third attack type is excluded from that run). Mean +/- std across 20 seeds.

**Scoring: deterministic z_mean** (reparameterization skipped at inference, z = z_mean -- no eps sample, no eval seed; audit finding O2). threshold_95 recomputed per seed as the 95th percentile of the deterministic error on the same held-out val-benign set (`05_contamination_sweep/01_data/val_benign.csv`), because the stored `threshold.json` values were calibrated on stochastic val errors and do not transfer. The original stochastic-scoring results live in `_stochastic_legacy/` next to this file; model weights identical, no retraining.

**Dipnot (PR-AUC / F1):** PR-AUC ve F1, tekrarlanan (resampled) flow kopyalarının prevalans'ı çarpıtmasını önlemek için dedup edilmiş test setinden (portscan+apache_bench n=1507, portscan+slowloris n=1179, apache_bench+slowloris n=1608, benign n=5428) hesaplanmıştır; recall/ROC-AUC/FPR davranış metrikleri olduğu için kanonik (dedup'suz) sette hesaplanmıştır — iki set arasında davranışsal fark <0.02 olduğu doğrulanmıştır (bkz. `dedup_sanity_check/` / `../01_single_attack_type/vae/dedup_sanity_check/`).

| attack_type_pair | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| portscan+apache_bench | 6821 | 2181 | 0.7725 +/- 0.0606 | 0.5952 +/- 0.0335 | 0.4719 +/- 0.0075 | 0.0577 +/- 0.0058 | 0.3355 +/- 0.0025 |
| portscan+slowloris | 6821 | 1623 | 0.9995 +/- 0.0002 | 0.9981 +/- 0.0007 | 0.8792 +/- 0.0115 | 0.0577 +/- 0.0058 | 0.9993 +/- 0.0033 |
| apache_bench+slowloris | 6821 | 2416 | 0.7950 +/- 0.0548 | 0.6362 +/- 0.0323 | 0.5135 +/- 0.0067 | 0.0577 +/- 0.0058 | 0.4007 +/- 0.0000 |
