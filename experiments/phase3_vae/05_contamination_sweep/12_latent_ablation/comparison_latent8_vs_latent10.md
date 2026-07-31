# Latent-dim ablation: latent=8 (== bottleneck) vs. canonical latent=10

Audit finding O1: latent_dim (10) > bottleneck width (8), so nominal
latent capacity exceeds what the encoder can express (rank <= 8).
This run: identical everything (clean-only train set, beta=0.25, 20 seeds
0-19, deterministic z_mean scoring, per-seed val-benign threshold_95),
only latent_dim changed 10 -> 8. Paired per-seed diffs, bootstrap 95% CI
(10000 resamples over the 20 seeds).

Metrics computed on the canonical (non-dedup) evaluation set for both
variants; the published hybrid dedup correction affects PR-AUC/F1 only
and would apply identically to both.

## Per-attack-type comparison (20-seed mean +/- std)

| attack_type | metric | latent=8 | latent=10 | paired diff (8-10) | 95% CI | CI excludes 0 |
|---|---|---|---|---|---|---|
| portscan | roc_auc | 0.9990 ± 0.0005 | 0.9988 ± 0.0005 | +0.0002 | [+0.0000, +0.0004] | **yes** |
| portscan | pr_auc | 0.9925 ± 0.0026 | 0.9911 ± 0.0025 | +0.0014 | [+0.0003, +0.0024] | **yes** |
| portscan | attack_recall | 0.9983 ± 0.0077 | 0.9983 ± 0.0077 | +0.0000 | [+0.0000, +0.0000] | no |
| portscan | f1 | 0.7711 ± 0.0229 | 0.7785 ± 0.0183 | -0.0074 | [-0.0196, +0.0042] | no |
| portscan | benign_fpr | 0.0603 ± 0.0076 | 0.0577 ± 0.0058 | +0.0026 | [-0.0015, +0.0068] | no |
| apache_bench | roc_auc | 0.7020 ± 0.0781 | 0.6670 ± 0.0890 | +0.0350 | [-0.0137, +0.0864] | no |
| apache_bench | pr_auc | 0.2756 ± 0.0439 | 0.2565 ± 0.0391 | +0.0191 | [-0.0055, +0.0435] | no |
| apache_bench | attack_recall | 0.0262 ± 0.0000 | 0.0262 ± 0.0000 | +0.0000 | [+0.0000, +0.0000] | no |
| apache_bench | f1 | 0.0403 ± 0.0011 | 0.0406 ± 0.0008 | -0.0004 | [-0.0010, +0.0002] | no |
| apache_bench | benign_fpr | 0.0603 ± 0.0076 | 0.0577 ± 0.0058 | +0.0026 | [-0.0014, +0.0068] | no |
| slowloris | roc_auc | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | +0.0000 | [-0.0000, +0.0000] | no |
| slowloris | pr_auc | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | +0.0000 | [+0.0000, +0.0000] | no |
| slowloris | attack_recall | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | +0.0000 | [+0.0000, +0.0000] | no |
| slowloris | f1 | 0.8191 ± 0.0186 | 0.8254 ± 0.0144 | -0.0063 | [-0.0167, +0.0035] | no |
| slowloris | benign_fpr | 0.0603 ± 0.0076 | 0.0577 ± 0.0058 | +0.0026 | [-0.0014, +0.0067] | no |

## Active latent dimensions (std(z_mean) > 0.15 on the clean train set, 09_collapse_investigation convention)

| variant   |   mean |     std |   min |   max |
|:----------|-------:|--------:|------:|------:|
| latent10  |   5.85 | 2.73909 |     1 |    10 |
| latent8   |   4.4  | 2.11262 |     2 |     8 |

