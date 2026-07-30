# Clean-only (0% contamination) VAE, evaluated per attack type

Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (20 seeds, threshold_95 per seed, inference only, no retraining).

Each row = that attack type's flows vs. the full test-split benign set only (other attack types excluded from that run). Mean +/- std across 20 seeds.

**Scoring: deterministic z_mean** (reparameterization skipped at inference, z = z_mean -- no eps sample, no eval seed; audit finding O2). threshold_95 recomputed per seed as the 95th percentile of the deterministic error on the same held-out val-benign set (`05_contamination_sweep/01_data/val_benign.csv`), because the stored `threshold.json` values were calibrated on stochastic val errors and do not transfer. The original stochastic-scoring results live in `_stochastic_legacy/` next to this file; model weights identical, no retraining.

**Dipnot (PR-AUC / F1):** PR-AUC ve F1, tekrarlanan (resampled) flow kopyalarının prevalans'ı çarpıtmasını önlemek için dedup edilmiş test setinden (apache_bench n=968, portscan n=539, slowloris n=640, benign n=5428) hesaplanmıştır; recall/ROC-AUC/FPR davranış metrikleri olduğu için kanonik (dedup'suz) sette hesaplanmıştır — iki set arasında davranışsal fark <0.02 olduğu doğrulanmıştır (bkz. `dedup_sanity_check/` / `../01_single_attack_type/vae/dedup_sanity_check/`).

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 6821 | 1487 | 0.6670 +/- 0.0890 | 0.2244 +/- 0.0349 | 0.0410 +/- 0.0011 | 0.0577 +/- 0.0058 | 0.0262 +/- 0.0000 |
| portscan | 6821 | 694 | 0.9988 +/- 0.0005 | 0.9921 +/- 0.0023 | 0.7689 +/- 0.0195 | 0.0577 +/- 0.0058 | 0.9983 +/- 0.0077 |
| slowloris | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.7986 +/- 0.0169 | 0.0577 +/- 0.0058 | 1.0000 +/- 0.0000 |
