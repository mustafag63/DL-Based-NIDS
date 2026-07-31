# Segmented (contiguous-block) injection: Clean-only VAE (contam_0pct), per-segment results

Sequence: `segmented_sequence.csv` (9931 flows, block order from `segmented_sequence_config.json`). Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct` (20 seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.

| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |
|---|---|---|---|---|---|---|
| 0 | benign | 1705 | 0.0305 +/- 0.0070 | -- | -- | -- |
| 1 | apache_bench | 1487 | -- | 0.0322 +/- 0.0044 | 0.0623 +/- 0.0083 | 0.0328 +/- 0.0055 |
| 2 | benign | 1705 | 0.0336 +/- 0.0078 | -- | -- | -- |
| 3 | slowloris | 929 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 4 | benign | 1705 | 0.0962 +/- 0.0222 | -- | -- | -- |
| 5 | portscan | 694 | -- | 0.9882 +/- 0.0148 | 0.9940 +/- 0.0075 | 0.9889 +/- 0.0138 |
| 6 | benign | 1706 | 0.0696 +/- 0.0088 | -- | -- | -- |

## Interpretation

apache_bench block recall = 0.0322 -- still near-zero when the attack type arrives as one contiguous block instead of interleaved with other attack types. Since detection is a static per-flow decision (reconstruction error > a fixed threshold) with no sequence memory in either model tested here, contiguous placement is not expected to change per-flow outcomes; this row exists to confirm that empirically rather than assume it.

Benign-segment FPR ranges 0.0305-0.0962 across the 4 benign gaps in this stream (vs. a single 0.0575 average if measured as one block) -- some spread is expected from smaller per-segment sample sizes rather than the model drifting, since it has no state carried between flows; worth a larger-n rerun before reading anything into the specific gap sizes.
