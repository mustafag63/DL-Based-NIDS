# Phase 3 — VAE variant

Companion to `phase3_dense/` (plain autoencoder). Trains on `window_10_0pct`
only (a dedicated clean-benign capture, see `prepare_window10.py`), evaluated
against Dense's existing labeled val/test split (`phase3_dense/03_phase3_splits/`,
read-only) purely as a labeled evaluation set — not an architecture comparison.

Final architecture (see `phase3_vae_autoencoder.ipynb`, sections 9-10):
latent_dim=10, beta=0.25 (selected over beta=1.0/0.5 and KL-annealing to address
partial posterior collapse — see notebook section 9.3 for the reasoning).
Health-check result: test AUC=0.9372, F1=0.8413.

## ✅ Lambda-layer deserialization bug — fixed (2026-07-18)

`vae_encoder_final.keras` previously used a `Lambda` layer to clip
`z_log_var` to `[-10, 10]` (prevents `exp()` overflow). Keras's
`Lambda.from_config` → `func_load` rebuilds the clip closure using its own
`python_utils` module's globals, which never import `tensorflow` — so loading
the model in a fresh process (even with `safe_mode=False`) raised `NameError:
name 'tf' is not defined` as soon as the encoder was called. This affected
both `vae_encoder_final.keras`/`vae_decoder_final.keras` and every model
saved by `05_contamination_sweep/train_contamination_sweep.py`.

**Fix:** the `Lambda` layer is replaced with `ClipLogVar`, a proper
`tf.keras.layers.Layer` subclass marked with
`@tf.keras.utils.register_keras_serializable(package="phase3_vae")`
(functionally identical to `tf.keras.saving.register_keras_serializable` —
used instead because this repo's tf 2.21 / keras 3.15 combo doesn't expose
`tf.keras.saving` on the lazily-loaded `tf.keras` namespace). A registered
`Layer` has no closure to lose, so there is nothing for `func_load` to
reconstruct incorrectly. `VAE2` (the class whose `call()` implements the
reparameterization trick — see below) is likewise registered and now has
`get_config`/`from_config`. Both classes live in **`phase3_vae/model_layers.py`**
(a shared module, not defined inline in the notebook), so any script — not
just the notebook — can import them.

As a result, `vae_encoder_final.keras` / `vae_decoder_final.keras` now load
with **plain `keras.models.load_model(path, safe_mode=True)`** (the default —
no `safe_mode=False`, no `custom_objects=` dict, no monkeypatching Keras
internals). The only remaining requirement is the normal one for *any* custom
Keras layer: the `ClipLogVar`/`VAE2` classes must be imported in the process
before `load_model` runs — `from model_layers import ClipLogVar, VAE2` — so
their decorators have run and registered them; this is standard Keras
behavior, not a workaround. **Any new script that loads these models must do
that import first**, since Keras's registry lookup only finds classes that
have already been imported/defined in the current process — see
`phase3_vae/scripts/verify_model_loading.py` for a minimal example.

The final architecture was retrained from scratch with the fixed
implementation (same data/split, same hyperparameters: latent_dim=10,
beta=0.25, Adam clipnorm=1.0, EarlyStopping patience=12/monitor=val_loss) and
reproduced the pre-fix numbers exactly: test AUC=0.9372, F1=0.8413 (fixed
seed, so this is expected, not just "close").

Two caveats from before still apply — the fix only touches the Lambda bug,
not the model's architecture:

- The **reparameterization trick** (`z = z_mean + exp(0.5*z_log_var) * eps`)
  is plain Python code inside `VAE2.call()`, not part of either saved model's
  graph/config.
- The **combined loss** (`recon_loss + beta * kl_loss`, beta=0.25) used
  during training is likewise only defined in `VAE2._compute_losses()`.

To run the full encode → sample → decode pipeline (or retrain), you still
need the `VAE2` class from `phase3_vae/model_layers.py` — not just the two
`.keras` files.

## `04_phase3_models/latest_run/`

Section 8 of the notebook (the health-check/latent-sweep model, *not* the
final architecture) saves here, never straight into `04_phase3_models/` —
this is only the raw output of the most recent notebook run, not an
official/approved final model; the final model is always
`04_phase3_models/vae_encoder_final.keras` / `vae_decoder_final.keras`. Any
file already in `latest_run/` from a previous run is archived in place with a
timestamp suffix before a new one is saved, so re-running the notebook can
never silently overwrite or collide with either an earlier run or the
approved final files.

## `04_phase3_models/superseded/`

- `vae_encoder_latent10.keras` / `vae_decoder_latent10.keras` — the beta=1.0
  baseline from before the collapse fix (section 9.3), retrained with the
  `ClipLogVar` fix; 1/10 active latent dimensions, no longer used. Kept only
  for comparison/traceability against the beta=0.25 result.
- `vae_encoder_final_lambda_bug.keras` / `vae_decoder_final_lambda_bug.keras`
  — the pre-fix, `Lambda`-based final architecture (beta=0.25) that hit the
  `NameError` described above. Kept only for traceability; superseded by
  `vae_encoder_final.keras` / `vae_decoder_final.keras` above, which are
  bit-for-bit equivalent in behavior (same seed, same data, same test
  AUC/F1) but load cleanly.
