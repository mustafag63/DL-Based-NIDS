# Dedup sanity check — clean-only VAE (contam_0pct), deterministic z_mean, per attack type

Audit finding **O3**: the test set contains both the source-window copy and the resampled-window copy of the same real flow (2356/9931 rows; 963 = 31.0% of attack rows), double-counting those flows in the metrics. **Dedup rule:** drop every `window_resampled_*` row, keep the real-window original (asserted: every dropped row has a ts-matched, label-identical real-window twin in this same test set, so nothing unique is lost). Dedup table: `dedup_test_with_attack_type.csv` (this folder).

Everything else is identical to the canonical deterministic run (`../results.csv`): same 20 seeds, z_mean scoring, per-seed threshold_95 recomputed on val-benign, no retraining. This is a sanity check only — the canonical results are unchanged.

## Dedup results

| attack_type | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | benign FPR (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|---|
| apache_bench | 5428 | 968 | 0.6601 +/- 0.0889 | 0.2244 +/- 0.0349 | 0.0410 +/- 0.0011 | 0.0596 +/- 0.0062 | 0.0279 +/- 0.0000 |
| portscan | 5428 | 539 | 0.9989 +/- 0.0005 | 0.9921 +/- 0.0023 | 0.7689 +/- 0.0195 | 0.0596 +/- 0.0062 | 0.9985 +/- 0.0066 |
| slowloris | 5428 | 640 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.7986 +/- 0.0169 | 0.0596 +/- 0.0062 | 1.0000 +/- 0.0000 |

## Comparison vs. canonical (non-dedup) deterministic results

| attack_type | metric | canonical (dup) | dedup | delta |
|---|---|---|---|---|
| portscan | n_benign / n_attack | 6821 / 694 | 5428 / 539 | -1393 / -155 |
| portscan | roc_auc | 0.9988 +/- 0.0005 | 0.9989 +/- 0.0005 | +0.0001 |
| portscan | pr_auc (prevalence-sensitive) | 0.9911 +/- 0.0025 | 0.9921 +/- 0.0023 | +0.0010 |
| portscan | f1 (prevalence-sensitive) | 0.7785 +/- 0.0183 | 0.7689 +/- 0.0195 | -0.0096 |
| portscan | benign_fpr | 0.0577 +/- 0.0058 | 0.0596 +/- 0.0062 | +0.0019 |
| portscan | attack_recall | 0.9983 +/- 0.0077 | 0.9985 +/- 0.0066 | +0.0002 |
| apache_bench | n_benign / n_attack | 6821 / 1487 | 5428 / 968 | -1393 / -519 |
| apache_bench | roc_auc | 0.6670 +/- 0.0890 | 0.6601 +/- 0.0889 | -0.0069 |
| apache_bench | pr_auc (prevalence-sensitive) | 0.2565 +/- 0.0391 | 0.2244 +/- 0.0349 | -0.0321 |
| apache_bench | f1 (prevalence-sensitive) | 0.0406 +/- 0.0008 | 0.0410 +/- 0.0011 | +0.0003 |
| apache_bench | benign_fpr | 0.0577 +/- 0.0058 | 0.0596 +/- 0.0062 | +0.0019 |
| apache_bench | attack_recall | 0.0262 +/- 0.0000 | 0.0279 +/- 0.0000 | +0.0017 |
| slowloris | n_benign / n_attack | 6821 / 929 | 5428 / 640 | -1393 / -289 |
| slowloris | roc_auc | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | +0.0000 |
| slowloris | pr_auc (prevalence-sensitive) | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | +0.0000 |
| slowloris | f1 (prevalence-sensitive) | 0.8254 +/- 0.0144 | 0.7986 +/- 0.0169 | -0.0268 |
| slowloris | benign_fpr | 0.0577 +/- 0.0058 | 0.0596 +/- 0.0062 | +0.0019 |
| slowloris | attack_recall | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | +0.0000 |

## Verdict

Max |delta|, behavior metrics (ROC-AUC / recall / FPR — depend only on per-flow scores and decisions): **0.0069**. Max |delta|, prevalence-sensitive metrics (PR-AUC / F1 — depend on the eval set's benign:attack mix by definition): **0.0321**. Threshold: 0.02.

Behavior metrics are practically identical with and without the duplicates: **the resampled copies were not changing the model's per-flow results — they only inflated n_benign/n_attack** (and made seed stds look tighter than the number of independent flows justifies).

PR-AUC/F1 do move past the threshold, but this is the *mechanical* effect of dedup changing the benign:attack prevalence these metrics are defined on (dedup removes ~20% of benign rows vs. ~31% of attack rows), not a change in model behavior — the recall/FPR rows above show the per-flow decisions are the same. If dedup numbers are adopted for reporting, PR-AUC/F1 should be quoted from the dedup set (its prevalence reflects distinct real flows); if the canonical numbers stand, the dedup n values give the true distinct-flow counts.
