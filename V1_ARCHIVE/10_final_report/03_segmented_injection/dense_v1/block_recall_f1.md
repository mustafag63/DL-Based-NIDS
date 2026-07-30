# Segmented (contiguous-block) injection: Dense autoencoder v1 (full_features), per-segment results

Sequence: `segmented_sequence.csv` (9931 flows, block order from `segmented_sequence_config.json`). Model: `phase3_dense/04_phase3_models/full_features` (5 seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.

| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |
|---|---|---|---|---|---|---|
| 0 | benign | 1705 | 0.0183 +/- 0.0046 | -- | -- | -- |
| 1 | apache_bench | 1487 | -- | 0.0262 +/- 0.0000 | 0.0511 +/- 0.0000 | 0.0262 +/- 0.0000 |
| 2 | benign | 1705 | 0.0171 +/- 0.0064 | -- | -- | -- |
| 3 | slowloris | 929 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 4 | benign | 1705 | 0.1336 +/- 0.0175 | -- | -- | -- |
| 5 | portscan | 694 | -- | 0.9931 +/- 0.0155 | 0.9965 +/- 0.0079 | 0.9931 +/- 0.0155 |
| 6 | benign | 1706 | 0.0771 +/- 0.0028 | -- | -- | -- |

## Interpretation

apache_bench block recall = 0.0262 -- still near-zero when the attack type arrives as one contiguous block instead of interleaved with other attack types. Since detection is a static per-flow decision (reconstruction error > a fixed threshold) with no sequence memory in either model tested here, contiguous placement is not expected to change per-flow outcomes; this row exists to confirm that empirically rather than assume it.

Benign-segment FPR ranges 0.0171-0.1336 across the 4 benign gaps in this stream (vs. a single 0.0615 average if measured as one block). This spread is a **systematic composition effect, not sampling noise** (audit finding O6): the benign pool is split into contiguous gaps in ts order (`build_segmented_injection.py`) and the capture windows are consecutive in time, so each gap holds a different mix of windows' benign flows, and per-window benign FPR differs. At n~=1705 per gap the binomial std of an FPR near 0.06 is only ~0.006, which cannot produce a spread this wide; it is also not the model drifting -- no state is carried between flows. The segment-by-window composition (model-independent, same sequence file) is tabulated in [../vae/segment_window_composition.md](../vae/segment_window_composition.md); the per-window FPR values there are the VAE's, but the same composition mechanism drives this Dense spread.
