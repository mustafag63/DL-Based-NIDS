# Experiment: IP-based rolling time-window features (v2) — tried, archived, not adopted

## Motivation

The v1 autoencoder (18/14 flow-level columns, see `04_phase3_models/` and
`05_phase3_results/` at the repo root) had a specific, reproducible blind
spot: `attack_type_breakdown_evaluation.py` showed **0.00% recall on
apache_bench across all 5 seeds, both feature variants**. A single
apache_bench flow (a fast HTTP GET/response, SF close, ~0.04-0.05s) is
behaviorally indistinguishable from an ordinary benign HTTP request at the
single-flow level — there is nothing in one flow's own numbers that flags
it as part of a benchmarking-tool flood.

The hypothesis: the missing signal is not in any one flow, but in the
*rate* of similar requests from the same source over a short window. This
follows directly from the repo's `context.md` TODO on IP-based time-window
aggregation.

## What was built

Four rolling 60-second, per-source-IP features were added to Phase 2
(`conn_count_60s`, `unique_dst_ports_60s`, `unique_dst_ips_60s`,
`failed_conn_ratio_60s`), computed strictly within each capture window (no
leakage across window boundaries). The full pipeline was rerun and 10
autoencoders were retrained on the resulting 22-column (`full_features`) /
18-column (`no_conn_state`) feature sets — same architecture, same 5 seeds,
same threshold-calibration method as v1.

## Headline result

apache_bench recall: **0.00% -> 100.00%**, all 5 seeds, both variants,
std = 0. portscan/slowloris stayed at ~99-100% (unaffected). Test-set
benign false-positive rate rose slightly (~2% -> ~3%). Per-window
breakdown (window_02 through window_08, N=21 to N=190) showed 100% recall
in every window.

## Why it was rejected: the 100% figure is not a clean behavioral signal

Digging into *why* the separation was perfect (`rolling_feature_overlap_check.py`)
found it comes from two different mechanisms, only one of which is a
genuine, generalizable behavioral signal:

- **High-N windows (window_05 and up, N>=92): real signal.**
  `conn_count_60s` alone (independent of the other 3 columns) already
  exceeds the benign range — many connections from one source in 60s is
  legitimately anomalous, and this part should generalize.

- **Low-N windows (window_02-04, N=21-51): an artifact, not a signal.**
  In these windows `conn_count_60s` for apache_bench is *lower* than the
  benign mean (e.g. window_02: 32.0 vs 112.2) — on that column alone,
  apache_bench looks calmer than ordinary browsing traffic. The entire
  separation comes from `unique_dst_ports_60s`, which is constant within
  each occurrence and exactly equal to that window's `N` (the port range
  the *portscan* command — always launched from the same source IP about
  0.4s before apache_bench — just finished scanning). apache_bench itself
  only ever talks to port 80; the port diversity is inherited from the
  neighboring portscan run, not produced by apache_bench.

Two related but distinct lab-specific limitations compound this:

1. **"Portscan-inheritance artifact"** — `attack_orchestrator.py` always
   runs portscan immediately before apache_bench/slowloris from the same
   IP, so the 60s rolling window for apache_bench structurally "inherits"
   the preceding portscan's port-diversity, regardless of apache_bench's
   own behavior.
2. **Source-IP confound** — only 2 machines ever generate traffic in this
   lab (192.168.10.2 = attacker only, 192.168.10.3 = benign only, roles
   never mix), so any per-source-IP rolling feature risks partly encoding
   "which machine is this" rather than pure behavior; there is no idle
   baseline for the attacker machine in the dataset.

**Practical consequence:** a standalone, low-volume apache_bench-style
flood launched *without* a preceding portscan from the same source would
likely still be missed — the low-N recall in this experiment depended on
an attack-sequencing artifact specific to this lab's orchestrator, not on
apache_bench's own traffic pattern.

## Why this was not adopted into the main pipeline

The 100% recall headline number, taken at face value, overstates what the
feature addition actually proves. Given the mixed/contaminated evidence,
shipping this as "the model now catches apache_bench" would misrepresent
the result. Rather than delete the experiment, it is archived here with
this documented rejection rationale — v1 remains the project's official
result (F1=0.862, aggregate recall=80%, apache_bench flow-level recall=0%,
see the root `00_REPORT.md`).

## Open follow-up (not done)

An isolated test — apache_bench run standalone, with no preceding
portscan from the same source IP — would cleanly separate the two
mechanisms above (real high-N signal vs. low-N sequencing artifact). This
has not been run.

## Contents of this folder

- `04_phase3_models_v2/`, `05_phase3_results_v2/` — the 10 retrained
  models and their metrics (22/18-column feature set).
- `02_phase2_feature_extraction_v2/` — snapshot of the 26-column
  `features_all_windows.csv/parquet` and `by_window/` files produced by
  the rolling-feature pipeline (the main-pipeline copies at the repo root
  have been reverted to the original 22-column v1 feature set).
- `faz2_feature_extraction_with_rolling_features.py` — the modified
  Phase 2 script that added the 4 rolling features (the main-pipeline
  `faz2_feature_extraction.py` has been reverted to not include this
  logic).
- `phase3_autoencoder_v2_train.py` — the training script used for the 10
  v2 models.
- `analysis/attack_type_breakdown_v1_vs_v2_comparison.py`,
  `analysis/attack_type_v2_per_window_breakdown.py`,
  `analysis/rolling_feature_overlap_check.py` — the evaluation and
  root-cause analysis scripts referenced above.

All scripts here are read-only with respect to the main pipeline's
tracked outputs; none of them were re-run after the archival move.
