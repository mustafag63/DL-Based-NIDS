# Single vs. pairwise attack-type evaluation (clean-only VAE, contam_0pct)

Combines results_single_attack_type.md and results_pairwise_attack_type.md into one table, so each attack type's solo performance can be read next to its performance when a second attack type shares the evaluation set (both compared against the same fixed benign pool; the non-participating attack type is excluded from each run, never present as unlabeled noise).

| evaluation set | n_benign | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | attack recall (thr95) |
|---|---|---|---|---|---|---|
| apache_bench (solo) | 6821 | 1487 | 0.5815 +/- 0.0768 | 0.2133 +/- 0.0219 | 0.0507 +/- 0.0081 | 0.0328 +/- 0.0055 |
| portscan (solo) | 6821 | 694 | 0.9982 +/- 0.0005 | 0.9886 +/- 0.0023 | 0.7737 +/- 0.0161 | 0.9889 +/- 0.0138 |
| slowloris (solo) | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.8271 +/- 0.0158 | 1.0000 +/- 0.0000 |
| portscan+apache_bench (pair) | 6821 | 2181 | 0.7135 +/- 0.0527 | 0.5598 +/- 0.0232 | 0.4447 +/- 0.0070 | 0.3369 +/- 0.0061 |
| portscan+slowloris (pair) | 6821 | 1623 | 0.9993 +/- 0.0002 | 0.9975 +/- 0.0007 | 0.8905 +/- 0.0105 | 0.9953 +/- 0.0057 |
| apache_bench+slowloris (pair) | 6821 | 2416 | 0.7427 +/- 0.0474 | 0.6283 +/- 0.0219 | 0.5170 +/- 0.0054 | 0.4044 +/- 0.0029 |

## apache_bench recall: solo vs. paired

Two different numbers, both included because they answer different questions:

- **pooled recall (pair)**: fraction of ALL attack flows in that pair's mixed evaluation set that get flagged. Moves mechanically with the mix (e.g. adding well-detected portscan flows pulls the pooled number up) even if no individual apache_bench flow's detection outcome changes -- it is not a measure of apache_bench detectability by itself.
- **apache_bench-only recall (pair)**: recall computed using only the apache_bench flows inside that pair's evaluation set, at the same model/threshold. Since detection is a per-flow decision (errors > thr95) that does not depend on which other flows share the test set, this is expected to match the solo number exactly (up to seed-sampling noise from the VAE's stochastic reparameterization) -- it is here to make that point explicit, not because pairing is expected to change it.

| evaluation set | pooled recall (pair) | apache_bench-only recall (pair) |
|---|---|---|
| apache_bench (solo) | -- | 0.0328 +/- 0.0055 |
| portscan+apache_bench (pair) | 0.3369 +/- 0.0061 | 0.0324 +/- 0.0050 |
| apache_bench+slowloris (pair) | 0.4044 +/- 0.0029 | 0.0322 +/- 0.0048 |
