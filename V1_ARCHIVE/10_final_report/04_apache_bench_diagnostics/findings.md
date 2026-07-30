# Why apache_bench flows are not separable from benign

Diagnostic on the clean-only (0% train contamination) VAE (`phase3_vae/05_contamination_sweep/04_models/contam_0pct`, 20 seeds, inference only, no retraining), using `06_attack_type_analysis/test_with_attack_type.csv`. Companion outputs: `feature_diagnostics_{apache_bench,portscan,slowloris}.csv`, `vae_reconstruction_error_hist.png`, `vae_reconstruction_error_summary.csv`, `top_features_apache_bench_boxplots.png`.

> **Skorlama notu (2026-07-28):** `vae_reconstruction_error_hist.png` ve `vae_reconstruction_error_summary.csv` **deterministik z_mean** skoruyla yeniden üretildi (audit O2; threshold_95 val-benign üzerinde deterministik skordan, per-seed — projenin diğer deterministik sonuçlarıyla aynı konvansiyon). Eski stokastik versiyonlar `_stochastic_legacy/` altında. Feature-KS analizleri (bölüm 1-2, 4-5) ve IAT testi (bölüm 6) VAE skoruna bağlı olmadığından değişmedi. Yeniden üretim: `../06_scripts/zmean_rescore/regenerate_apache_diagnostics_zmean.py`.

## 1. Per-feature separability: apache_bench vs. benign

Ranked by Kolmogorov-Smirnov statistic (0 = distributions fully overlap, 1 = fully separated). All 18 modeling features are scaled (StandardScaler, fit on train-split benign only), one-hots included.

| feature | group | KS stat | KS p-value | mean shift (benign std) | benign mean (std) | apache_bench mean (std) |
|---|---|---|---|---|---|---|
| orig_pkts_scaled | packet count/rate | 0.755 | 1.34e-321 | -0.44 sigma | -0.058 (0.764) | -0.397 (0.014) |
| orig_bytes_scaled | byte volume | 0.755 | 1.34e-321 | -0.39 sigma | -0.052 (0.778) | -0.357 (0.005) |
| resp_bytes_scaled | byte volume | 0.754 | 1.35e-321 | -0.68 sigma | -0.079 (0.900) | -0.693 (0.012) |
| resp_pkts_scaled | packet count/rate | 0.754 | 1.35e-321 | -0.62 sigma | -0.077 (0.872) | -0.616 (0.018) |
| duration_scaled | duration | 0.693 | 1.90e-321 | -0.42 sigma | -0.058 (0.792) | -0.391 (0.002) |
| byte_ratio_scaled | byte volume | 0.679 | 2.02e-321 | -0.37 sigma | 0.059 (1.180) | -0.378 (0.039) |
| bytes_per_sec_scaled | byte volume | 0.672 | 2.08e-321 | -0.24 sigma | 0.098 (1.231) | -0.201 (0.039) |
| pkts_per_sec_scaled | packet count/rate | 0.622 | 3.28e-321 | +1.15 sigma | 0.108 (1.238) | 1.527 (10.506) |
| service_http | service (one-hot) | 0.225 | 8.42e-55 | +0.52 sigma | 0.749 (0.434) | 0.974 (0.160) |
| service_none | service (one-hot) | 0.168 | 1.41e-30 | -0.42 sigma | 0.194 (0.396) | 0.026 (0.160) |
| proto_udp | protocol (one-hot) | 0.051 | 3.72e-03 | -0.23 sigma | 0.051 (0.219) | 0.000 (0.000) |
| service_dns | service (one-hot) | 0.051 | 3.72e-03 | -0.23 sigma | 0.051 (0.219) | 0.000 (0.000) |
| proto_tcp | protocol (one-hot) | 0.051 | 3.72e-03 | +0.23 sigma | 0.949 (0.219) | 1.000 (0.000) |
| conn_state_REJ | connection state (one-hot) | 0.026 | 3.63e-01 | n/a (constant in benign) | 0.000 (0.000) | 0.026 (0.160) |
| conn_state_SF | connection state (one-hot) | 0.025 | 4.12e-01 | -0.79 sigma | 0.999 (0.032) | 0.974 (0.160) |
| service_ssh | service (one-hot) | 0.007 | 1.00e+00 | -0.08 sigma | 0.007 (0.081) | 0.000 (0.000) |
| conn_state_RSTO | connection state (one-hot) | 0.001 | 1.00e+00 | -0.03 sigma | 0.001 (0.032) | 0.000 (0.000) |
| conn_state_S1 | connection state (one-hot) | 0.000 | 1.00e+00 | n/a (constant in benign) | 0.000 (0.000) | 0.000 (0.000) |

13/18 features show a statistically significant (p<0.05) KS difference between apache_bench and benign, and the top features (`orig_pkts_scaled`, `orig_bytes_scaled`, `resp_bytes_scaled`, `resp_pkts_scaled`, `duration_scaled`) all have KS >= 0.69 -- on paper, apache_bench looks separable. But the KS statistic and the *mean shift in benign std* column tell different stories. KS is large here because apache_bench is a **very narrow, low-variance cluster** (its p5-p95 range on `orig_pkts_scaled` collapses almost to a single point -- see the percentile columns in `feature_diagnostics_apache_bench.csv` -- because ab is a stereotyped, fixed-size HTTP GET request repeated many times), so its empirical CDF jumps sharply against benign's much wider spread even though the cluster's *center* sits only 0.43 benign-std away on average -- i.e. **inside** the range of ordinary benign traffic, not out in its tail. Reconstruction error is a sum of squared per-feature deviations from a benign-fit manifold, so a point sitting inside the training distribution's normal range reconstructs cleanly regardless of how sharply its CDF differs from benign's.

## 2. Reference: same analysis on portscan and slowloris

Per `06_attack_type_analysis/results_single_attack_type.md`, the same clean-only VAE gets ROC-AUC 0.58 / recall@thr95 3.3% on apache_bench, vs. ROC-AUC 0.998-1.000 / recall 98.9-100% on portscan and slowloris -- the gap this diagnostic is investigating.

### portscan

| feature | KS stat (this type) | mean shift (this type, benign std) | apache_bench KS stat (same feature) | apache_bench mean shift (benign std) |
|---|---|---|---|---|
| conn_state_SF | 0.999 | -31.2 sigma | 0.025 | -0.79 sigma |
| conn_state_REJ | 0.965 | n/a | 0.026 | n/a |
| pkts_per_sec_scaled | 0.963 | +57.7 sigma | 0.622 | +1.15 sigma |

### slowloris

| feature | KS stat (this type) | mean shift (this type, benign std) | apache_bench KS stat (same feature) | apache_bench mean shift (benign std) |
|---|---|---|---|---|
| byte_ratio_scaled | 1.000 | +1355.4 sigma | 0.679 | -0.37 sigma |
| conn_state_SF | 0.999 | -31.2 sigma | 0.025 | -0.79 sigma |
| conn_state_RSTO | 0.999 | +31.2 sigma | 0.001 | -0.03 sigma |

The KS statistics alone look comparable across all three attack types (all mostly >0.6 on their top features), but the mean-shift-in-benign-std column is where portscan and slowloris diverge sharply from apache_bench: portscan and slowloris push their top features tens to hundreds of benign standard deviations away (huge, obviously-anomalous values -- e.g. slowloris's `byte_ratio_scaled` and portscan's `conn_state_SF`/`conn_state_REJ` are near-categorical splits), while apache_bench's shifts stay within a few benign standard deviations even on its best features. portscan trips connection-state/protocol one-hots that essentially never fire for benign traffic (half-open scans, rejected connections), and slowloris's deliberately slow, long-held connections send far fewer bytes per unit time than any normal flow. apache_bench, by contrast, is ordinary completed-handshake HTTP traffic -- its flows are individually unremarkable; only their volume and repetition are unusual, and the current feature set has no per-flow way to represent that.

## 3. VAE reconstruction error by group (deterministic z_mean)

| group | n | mean error | median error | std error | % flagged at mean threshold_95 (0.0903) |
|---|---|---|---|---|---|
| benign | 6821 | 0.04872 | 0.01306 | 0.6561 | 5.1% |
| apache_bench | 1487 | 5.744 | 0.01711 | 37.92 | 2.6% |
| portscan+slowloris | 1623 | 5.696e+04 | 8.807e+04 | 5.033e+04 | 100.0% |

The medians are the honest summary here (both means are outlier-dominated: benign's by a handful of large-error flows, apache_bench's by the same ~39 flows that every seed flags): the **typical apache_bench flow's deterministic error is 0.0171 — only ~1.3x the typical benign flow's 0.0131, and ~5x BELOW the 0.0903 threshold**. With the stochastic scoring noise removed, `vae_reconstruction_error_hist.png` shows this even more sharply than before: apache_bench forms an extremely narrow spike sitting *inside* the right shoulder of the benign distribution, while portscan+slowloris sits ~6 orders of magnitude away. apache_bench's mean (5.74) vs. median (0.017) gap is the 39-flow flagged subset — a fixed set, identical across all 20 seeds (see `deterministic_vs_stochastic_comparison.md`). This confirms, now without any scoring-noise caveat, that the miss is a genuine feature-level separability problem, not a downstream thresholding artifact.

## 4. Top discriminative features (still weak in absolute terms)

`top_features_apache_bench_boxplots.png` shows the 8 features with the highest apache_bench-vs-benign KS statistic: `orig_pkts_scaled`, `orig_bytes_scaled`, `resp_bytes_scaled`, `resp_pkts_scaled`, `duration_scaled`, `byte_ratio_scaled`, `bytes_per_sec_scaled`, `pkts_per_sec_scaled`. Even these show heavy box overlap rather than clean separation -- there is no single feature or small combination in the current 18-feature set that isolates apache_bench.

## 5. Weakest feature groups for apache_bench, and a hypothesis

By mean KS statistic within group: byte-volume features (orig_bytes_scaled, resp_bytes_scaled, byte_ratio_scaled, bytes_per_sec_scaled) = 0.715, packet count/rate features (orig_pkts_scaled, resp_pkts_scaled, pkts_per_sec_scaled) = 0.711, duration (duration_scaled) = 0.693, protocol/service/conn-state one-hots (mean over 10 columns) = 0.060.

**Hypothesis:** section 1 shows apache_bench flows form a tight, low-variance cluster (its p5-p95 range collapses almost to a point on `orig_pkts_scaled`/`orig_bytes_scaled`/etc., see `feature_diagnostics_apache_bench.csv`) that sits only a few benign standard deviations from benign's mean -- i.e. a stereotyped, repeated, but individually unremarkable HTTP GET request. apache_bench (`ab`) is a benchmarking tool that fires many near-identical short HTTP requests, often concurrently, at a single target; every *individual* flow it produces looks like an ordinary short HTTP request because that's what it literally is at the single-flow level. What is actually anomalous about apache_bench is that this same request repeats far more often, and with far less inter-arrival-time variance, than organic HTTP traffic to the same destination -- a property that is invisible to a model scoring one flow at a time. The current 18-feature set has no notion of request rate, concurrency, or inter-arrival time across flows sharing an endpoint. Adding features computed over a short sliding window per (src, dst, dst_port) tuple -- e.g. connections-per-second to the same destination, distinct-source-port reuse rate, or inter-arrival-time mean/variance across the last N flows to the same service -- would give the model a traffic-pattern-level signal instead of a single-flow-level one. This is a hypothesis, not a validated fix: it should be checked by re-running this same KS / reconstruction-error diagnostic once such a feature is added, to confirm it actually pushes apache_bench's reconstruction error above threshold rather than just adding noise.

## 6. Temporal hypothesis test: inter-arrival time

Quick, no-retrain check of the section 5 hypothesis: compute one flow-window feature directly from the existing `ts` column -- inter-arrival time (IAT) between consecutive same-label flows, diffed within each `window_id` only (see `test_apache_bench_temporal_hypothesis.py`). This is not a modeling feature added to the VAE; it is a standalone statistical check of whether such a feature *could* separate apache_bench from benign.

| group | n | mean IAT (s) | std IAT (s) | p5 | p25 | median | p75 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|
| benign | 6812 | 10.43 | 90.06 | 0.0001731 | 0.004726 | 2.18 | 8.04 | 33.92 | 81.54 |
| apache_bench | 1481 | 24.31 | 291.5 | 0.0006671 | 0.000839 | 0.000922 | 0.001683 | 0.006738 | 999.6 |

KS statistic = 0.7097, p-value = 1.744e-321 (n_benign=6812, n_apache_bench=1481).

apache_bench's median inter-arrival time (0.000922s) is about 2364x shorter than benign's (2.18s). The KS statistic (0.710) is in the same range as section 1's strongest single-flow features (0.62-0.76), not higher -- so IAT alone is not obviously a *better* discriminator by KS. What is different is the **effect size**: section 1 found apache_bench's strongest features had means only ~0.4-0.7 benign-std away from benign's mean (inside benign's normal range); here the two groups' medians differ by ~3 orders of magnitude, with apache_bench's IAT overwhelmingly under 2ms (consecutive apache_bench requests arriving almost back-to-back) against benign's multi-second median. See `iat_apache_bench_vs_benign_hist.png`. (apache_bench's mean, 24.31s, and p99, 999.6s, are much larger than its median because the IAT distribution is bimodal: sub-2ms within a burst of apache_bench requests, and occasional much longer gaps between separate bursts in the same window -- both consistent with a benchmarking tool that fires rapid request bursts rather than one steady stream.)

This partially supports the section 5 hypothesis: IAT does not beat the best single-flow features on KS statistic alone, but it separates apache_bench from benign via a completely different, much larger-magnitude signal (multi-order-of-magnitude rate difference vs. a sub-1-sigma mean shift) that the current 18 features have no way to represent, since none of them look across flows. That is still grounds to expect a rate/concurrency feature to help, though which of KS statistic or effect size actually predicts VAE reconstruction-error separation is untested here. This is a statistical check of the feature's separability alone, not a validation that adding it to the VAE and retraining would actually raise apache_bench's reconstruction error above threshold -- that would need to be confirmed with a real retrain-and-evaluate pass, which is out of scope here.

