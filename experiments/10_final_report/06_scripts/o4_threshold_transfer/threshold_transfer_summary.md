# O4 threshold transfer check — val-benign (n=653) -> test benign

20 canonical clean-only VAE seeds, deterministic z_mean scoring.
Calibration set: window_10 val-benign, n=653. Applied to test benign, n=6821 (different windows).

- threshold_95 across seeds: mean 0.0903, std 0.0252 (CV 27.9%), range [0.0429, 0.1529]
- within-seed bootstrap 95% CI of the percentile estimate: mean relative width 59.7% of the threshold
- test-benign FPR at the val threshold (nominal 5.00%): mean 5.77% ± 0.58%, range [4.78%, 6.93%]
- threshold that would give exactly 5% on test benign / val threshold: mean ratio 1.082, range [0.951, 1.265]
- KS(val errors, test-benign errors): mean 0.0674, range [0.0469, 0.1230]; 5/20 seeds with p < 0.01

Per-seed table: threshold_transfer_per_seed.csv
