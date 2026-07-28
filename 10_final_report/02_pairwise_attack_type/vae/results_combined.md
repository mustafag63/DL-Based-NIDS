# Single vs. pairwise attack-type evaluation (clean-only VAE, contam_0pct)

Combines results.md (single) and results.md (pairwise) into one table, so each attack type's solo performance can be read next to its performance when a second attack type shares the evaluation set (both compared against the same fixed benign pool; the non-participating attack type is excluded from each run, never present as unlabeled noise). Deterministic z_mean scoring throughout.

**Dipnot (PR-AUC / F1):** PR-AUC ve F1, tekrarlanan (resampled) flow kopyalarının prevalans'ı çarpıtmasını önlemek için dedup edilmiş test setinden (tekli: apache_bench n=968, portscan n=539, slowloris n=640; ikili: portscan+apache_bench n=1507, portscan+slowloris n=1179, apache_bench+slowloris n=1608; benign n=5428) hesaplanmıştır; recall/ROC-AUC/FPR davranış metrikleri olduğu için kanonik (dedup'suz) sette hesaplanmıştır — iki set arasında davranışsal fark <0.02 olduğu doğrulanmıştır (bkz. `dedup_sanity_check/` / `../01_single_attack_type/vae/dedup_sanity_check/`).

| evaluation set | n_benign | n_attack | ROC-AUC | PR-AUC (dedup) | F1 (thr95, dedup) | attack recall (thr95) |
|---|---|---|---|---|---|---|
| apache_bench (solo) | 6821 | 1487 | 0.6670 +/- 0.0890 | 0.2244 +/- 0.0349 | 0.0410 +/- 0.0011 | 0.0262 +/- 0.0000 |
| portscan (solo) | 6821 | 694 | 0.9988 +/- 0.0005 | 0.9921 +/- 0.0023 | 0.7689 +/- 0.0195 | 0.9983 +/- 0.0077 |
| slowloris (solo) | 6821 | 929 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 0.7986 +/- 0.0169 | 1.0000 +/- 0.0000 |
| portscan+apache_bench (pair) | 6821 | 2181 | 0.7725 +/- 0.0606 | 0.5952 +/- 0.0335 | 0.4719 +/- 0.0075 | 0.3355 +/- 0.0025 |
| portscan+slowloris (pair) | 6821 | 1623 | 0.9995 +/- 0.0002 | 0.9981 +/- 0.0007 | 0.8792 +/- 0.0115 | 0.9993 +/- 0.0033 |
| apache_bench+slowloris (pair) | 6821 | 2416 | 0.7950 +/- 0.0548 | 0.6362 +/- 0.0323 | 0.5135 +/- 0.0067 | 0.4007 +/- 0.0000 |

## apache_bench recall: solo vs. paired

Two different numbers, both included because they answer different questions:

- **pooled recall (pair)**: fraction of ALL attack flows in that pair's mixed evaluation set that get flagged. Moves mechanically with the mix (e.g. adding well-detected portscan flows pulls the pooled number up) even if no individual apache_bench flow's detection outcome changes -- it is not a measure of apache_bench detectability by itself.
- **apache_bench-only recall (pair)**: recall computed using only the apache_bench flows inside that pair's evaluation set, at the same model/threshold. Since detection is a per-flow decision (errors > thr95) that does not depend on which other flows share the test set, this matches the solo number exactly (deterministic scoring: the equality is now literal, not up-to-noise) -- it is here to make that point explicit, not because pairing is expected to change it.

| evaluation set | pooled recall (pair) | apache_bench-only recall (pair) |
|---|---|---|
| apache_bench (solo) | -- | 0.0262 +/- 0.0000 |
| portscan+apache_bench (pair) | 0.3355 +/- 0.0025 | 0.0262 +/- 0.0000 |
| apache_bench+slowloris (pair) | 0.4007 +/- 0.0000 | 0.0262 +/- 0.0000 |
