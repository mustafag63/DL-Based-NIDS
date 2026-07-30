# Segmented (contiguous-block) injection: Clean-only VAE (contam_0pct), deterministic z_mean scoring, per-segment results

Sequence: `segmented_sequence.csv` (9931 flows, block order from `segmented_sequence_config.json`). Model: `phase3_vae/05_contamination_sweep/04_models/contam_0pct (z_mean scoring, threshold_95 recomputed on val-benign)` (20 seeds, threshold_95 per seed, inference only, no retraining). Mean +/- std across seeds.

| segment_id | segment_label | n | benign FPR (thr95) | attack recall (thr95) | F1 (thr95) | recall in shuffled test set (for comparison) |
|---|---|---|---|---|---|---|
| 0 | benign | 1705 | 0.0321 +/- 0.0110 | -- | -- | -- |
| 1 | apache_bench | 1487 | -- | 0.0262 +/- 0.0000 | 0.0511 +/- 0.0000 | 0.0262 +/- 0.0000 |
| 2 | benign | 1705 | 0.0361 +/- 0.0108 | -- | -- | -- |
| 3 | slowloris | 929 | -- | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 |
| 4 | benign | 1705 | 0.0933 +/- 0.0239 | -- | -- | -- |
| 5 | portscan | 694 | -- | 0.9983 +/- 0.0077 | 0.9991 +/- 0.0039 | 0.9983 +/- 0.0077 |
| 6 | benign | 1706 | 0.0694 +/- 0.0083 | -- | -- | -- |

## Interpretation

apache_bench block recall = 0.0262 -- still near-zero when the attack type arrives as one contiguous block instead of interleaved with other attack types. Since detection is a static per-flow decision (reconstruction error > a fixed threshold) with no sequence memory in either model tested here, contiguous placement is not expected to change per-flow outcomes; this row exists to confirm that empirically rather than assume it.

Benign-segment FPR ranges 0.0321-0.0933 across the 4 benign gaps in this stream (vs. a single 0.0577 average if measured as one block). This spread is a **systematic composition effect, not sampling noise** (audit finding O6): the benign pool is split into contiguous gaps in ts order (`build_segmented_injection.py`) and the capture windows are consecutive in time, so each gap holds a different mix of windows' benign flows -- and per-window benign FPR differs sharply (window_06: 0.100, window_07: 0.115, vs. 0.029-0.053 for the others; deterministic z_mean, 20 seeds). Gap 4 (FPR 0.093) is 45% window_06 + 26% window_07; gap 0 (FPR 0.032) contains neither. At n~=1705 per gap the binomial std of an FPR near 0.05 is only ~0.005, which cannot produce a 0.032->0.093 spread, and the pattern survived unchanged when deterministic scoring removed all scoring noise. It is also not the model drifting -- no state is carried between flows. Full evidence: [segment_window_composition.md](segment_window_composition.md) (segment x window composition, per-window FPR, and each gap's FPR reconstructed from its composition).

## Dedup prevalans düzeltmesi bu rapora neden uygulanmadı

01/02'deki kanonik tablolarda PR-AUC ve F1, resampled kopyaların prevalans'ı çarpıtmaması için dedup edilmiş test setinden alınmıştır. Bu raporda ise prevalans-duyarlı metrik yok: PR-AUC hiç raporlanmıyor ve blok F1'i, her attack bloğu %100 attack flow'dan oluştuğu için (blokta benign yok) precision=1 ile F1 = 2·recall/(1+recall) — yani recall'un birebir fonksiyonu, bir davranış metriği. Dedup sağlamlık kontrolü (`../../01_single_attack_type/vae/dedup_sanity_check/`) davranış metriklerinin dedup'la <0.02 değiştiğini doğruladı; resampled kopyalar burada yalnızca segment başına n'i şişirir (attack satırlarının %31'i kopya), hiçbir orandaki sonucu değiştirmez.
