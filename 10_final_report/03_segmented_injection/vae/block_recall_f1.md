# Segmented (contiguous-block) injection: VAE (contam_0pct, 19 features: +concurrency_src_1s, deterministic z_mean), per-segment results

Sequence: `segmented_sequence.csv` (9931 flows, block order from `segmented_sequence_config.json`, unchanged from v1). Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (5 seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.

| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |
|---|---|---|---|---|---|---|
| 0 | benign | 1705 | 0.0386 +/- 0.0166 | -- | -- | -- |
| 1 | apache_bench | 1487 | -- | 0.9500 +/- 0.0453 | 0.9739 +/- 0.0242 | 0.9500 +/- 0.0453 |
| 2 | benign | 1705 | 0.0490 +/- 0.0191 | -- | -- | -- |
| 3 | slowloris | 929 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 4 | benign | 1705 | 0.0967 +/- 0.0097 | -- | -- | -- |
| 5 | portscan | 694 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 6 | benign | 1706 | 0.0811 +/- 0.0117 | -- | -- | -- |

## Interpretation

apache_bench block recall = 0.9500 -- notably higher, consistent with the shuffled-test-set single_attack_type/pairwise v2 results. Static per-flow threshold decision, no sequence memory: contiguous placement is not expected to change per-flow outcomes; confirmed empirically here.

Benign-segment FPR ranges 0.0386-0.0967 across the 4 benign gaps (vs. a single 0.0664 average if measured as one block).
