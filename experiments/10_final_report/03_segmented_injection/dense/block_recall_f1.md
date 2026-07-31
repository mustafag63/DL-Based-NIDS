# Segmented (contiguous-block) injection: Dense autoencoder (full_features + concurrency_src_1s), per-segment results

Sequence: `segmented_sequence.csv` (9931 flows, block order from `segmented_sequence_config.json`, unchanged from v1). Model: `phase3_dense/04_phase3_models/full_features` (5 seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.

| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |
|---|---|---|---|---|---|---|
| 0 | benign | 1705 | 0.0151 +/- 0.0027 | -- | -- | -- |
| 1 | apache_bench | 1487 | -- | 0.9092 +/- 0.0382 | 0.9521 +/- 0.0211 | 0.9092 +/- 0.0382 |
| 2 | benign | 1705 | 0.0142 +/- 0.0061 | -- | -- | -- |
| 3 | slowloris | 929 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 4 | benign | 1705 | 0.1478 +/- 0.0051 | -- | -- | -- |
| 5 | portscan | 694 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 6 | benign | 1706 | 0.0870 +/- 0.0063 | -- | -- | -- |

## Interpretation

apache_bench block recall = 0.9092 -- notably higher, consistent with the shuffled-test-set single_attack_type/pairwise v2 results. Static per-flow threshold decision, no sequence memory: contiguous placement is not expected to change per-flow outcomes; confirmed empirically here.

Benign-segment FPR ranges 0.0142-0.1478 across the 4 benign gaps (vs. a single 0.0660 average if measured as one block).
