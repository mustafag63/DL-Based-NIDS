# VAE vs. Dense autoencoder v1: side-by-side comparison

Both models are evaluated inference-only (no retraining) on the same flows
(`06_attack_type_analysis/test_with_attack_type.csv` and
`07_segmented_injection/segmented_sequence.csv`), the same 18 modeling
feature columns, and the same threshold_95 convention (95th percentile of
benign reconstruction error, computed per seed).

- **VAE**: clean-only (0% train contamination), `phase3_vae/05_contamination_sweep/04_models/contam_0pct`, 20 seeds, threshold_95 read from each seed's saved `threshold.json`.
- **Dense v1**: `phase3_dense/04_phase3_models/full_features`, 5 seeds, threshold_95 computed fresh per seed as the 95th percentile of reconstruction error on `phase3_dense/03_phase3_splits`'s validation-split benign flows (same convention as `analysis/attack_type_breakdown_evaluation.py`, since Dense v1 has no saved per-seed threshold file).

## Single attack type (vs. full benign pool)

| attack_type | model | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | VAE | 1487 | 0.5815 +/- 0.0768 | 0.2133 +/- 0.0219 | 0.0507 +/- 0.0081 | 0.0565 +/- 0.0059 | **0.0328 +/- 0.0055** |
| apache_bench | Dense v1 | 1487 | 0.6957 +/- 0.0791 | 0.2704 +/- 0.0406 | 0.0401 +/- 0.0003 | 0.0615 +/- 0.0023 | **0.0262 +/- 0.0000** |
| portscan | VAE | 694 | 0.9982 +/- 0.0005 | 0.9886 +/- 0.0023 | 0.7737 +/- 0.0161 | 0.0578 +/- 0.0056 | 0.9889 +/- 0.0138 |
| portscan | Dense v1 | 694 | 0.9988 +/- 0.0007 | 0.9912 +/- 0.0032 | 0.7645 +/- 0.0135 | 0.0615 +/- 0.0023 | 0.9931 +/- 0.0155 |
| slowloris | VAE | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8271 +/- 0.0158 | 0.0570 +/- 0.0062 | 1.0000 +/- 0.0000 |
| slowloris | Dense v1 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8157 +/- 0.0055 | 0.0615 +/- 0.0023 | 1.0000 +/- 0.0000 |

## Pairwise attack-type combinations

| attack_type_pair | model | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | attack recall (thr95, pooled) |
|---|---|---|---|---|---|---|
| portscan+apache_bench | VAE | 2181 | 0.7135 +/- 0.0527 | 0.5598 +/- 0.0232 | 0.4447 +/- 0.0070 | 0.3369 +/- 0.0061 |
| portscan+apache_bench | Dense v1 | 2181 | 0.7921 +/- 0.0539 | 0.6023 +/- 0.0370 | 0.4375 +/- 0.0069 | 0.3339 +/- 0.0049 |
| portscan+slowloris | VAE | 1623 | 0.9993 +/- 0.0002 | 0.9975 +/- 0.0007 | 0.8905 +/- 0.0105 | 0.9953 +/- 0.0057 |
| portscan+slowloris | Dense v1 | 1623 | 0.9995 +/- 0.0003 | 0.9981 +/- 0.0008 | 0.8840 +/- 0.0068 | 0.9970 +/- 0.0066 |
| apache_bench+slowloris | VAE | 2416 | 0.7427 +/- 0.0474 | 0.6283 +/- 0.0219 | 0.5170 +/- 0.0054 | 0.4044 +/- 0.0029 |
| apache_bench+slowloris | Dense v1 | 2416 | 0.8127 +/- 0.0487 | 0.6663 +/- 0.0344 | 0.5090 +/- 0.0021 | 0.4007 +/- 0.0000 |

## Segmented (contiguous-block) injection

| segment | model | attack recall (thr95) | F1 (thr95) |
|---|---|---|---|
| apache_bench block | VAE | 0.0322 +/- 0.0044 | 0.0623 +/- 0.0083 |
| apache_bench block | Dense v1 | 0.0262 +/- 0.0000 | 0.0511 +/- 0.0000 |
| slowloris block | VAE | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| slowloris block | Dense v1 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| portscan block | VAE | 0.9882 +/- 0.0148 | 0.9940 +/- 0.0075 |
| portscan block | Dense v1 | 0.9931 +/- 0.0155 | 0.9965 +/- 0.0079 |

Both models' block-recall numbers match their own shuffled-test-set numbers essentially exactly (see `07_segmented_injection/results_segmented.md` and `08_dense_v1_comparison/results_segmented_dense.md`) -- contiguous placement changes neither model's per-flow behavior, confirming both are static per-flow detectors with no sequence state.

## Does Dense v1 have the same apache_bench weakness as the VAE?

**Yes, and it is at least as bad, arguably slightly worse at the operating threshold.** Across every evaluation here (solo, both pairwise combinations that include it, and the segmented block), Dense v1's apache_bench recall is 0.026-0.033, essentially the same order of near-total miss as the VAE's 0.026-0.041. This is not something either architecture happens to fix -- it is the same underlying feature-set problem (apache_bench's fixed 80-byte/`SF`/<1s-duration signature sits close enough to ordinary benign HTTP traffic in the 18-column feature space that neither model's reconstruction error separates it well at a 95th-percentile threshold).

One real difference worth noting: Dense v1's raw ranking of apache_bench flows is *better* than the VAE's (ROC-AUC 0.696 vs 0.581, PR-AUC 0.270 vs 0.213) -- its continuous anomaly score does put more apache_bench flows above more benign flows than the VAE's does. But this doesn't translate into better detection at the actual thr95 operating point: Dense v1's F1/recall for apache_bench are marginally *lower* than the VAE's (0.040 vs 0.051 F1, 0.026 vs 0.033 recall), because each model's threshold is calibrated independently against its own benign error distribution, and Dense v1's benign errors are apparently heavier-tailed relative to its apache_bench errors than the VAE's are. So: better separability in principle, same failure in practice at this threshold policy.

The segmented-injection plots make the qualitative difference visible: the VAE's apache_bench block is a noisy scatter of points hugging just below threshold (stochastic reparameterization sampling), while Dense v1's apache_bench block is a nearly flat, deterministic line at a similarly low error level -- Dense v1 reconstructs every apache_bench flow almost identically well, with no randomness to occasionally push a flow above threshold, which is part of why its recall has essentially zero seed-to-seed variance (std=0.0000) versus the VAE's small but nonzero spread.

## Which model is more balanced across attack types overall?

Computing macro-average recall and F1 across the 3 solo attack-type runs:

| model | macro recall | macro F1 |
|---|---|---|
| VAE | 0.6739 | 0.5505 |
| Dense v1 | 0.6731 | 0.5401 |

The two are within noise of each other (VAE's own apache_bench ROC-AUC has a std of 0.077 across seeds, larger than this whole gap) -- **neither model is meaningfully more balanced than the other.** Both show the identical pattern: portscan and slowloris are detected almost perfectly (recall >=0.99), apache_bench is almost completely missed (recall <=0.033), and that split accounts for essentially all of the variance in "overall" accuracy numbers reported elsewhere in this project. If a single practical takeaway is needed: **switching between these two architectures will not fix the apache_bench blind spot** -- that requires either a different/expanded feature set for that attack signature or a per-attack-type threshold/ensemble strategy, not a different autoencoder.
