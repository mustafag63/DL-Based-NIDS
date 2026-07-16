# Phase 3 — VAE variant

Companion to `phase3_dense/` (plain autoencoder). Trains on `window_10_0pct`
only (a dedicated clean-benign capture, see `prepare_window10.py`), evaluated
against Dense's existing labeled val/test split (`phase3_dense/03_phase3_splits/`,
read-only) purely as a labeled evaluation set — not an architecture comparison.

Final architecture (see `phase3_vae_autoencoder.ipynb`, sections 9-10):
latent_dim=10, beta=0.25 (selected over beta=1.0/0.5 and KL-annealing to address
partial posterior collapse — see notebook section 9.3 for the reasoning).
Health-check result: test AUC=0.9372, F1=0.8413.

## ⚠️ `vae_encoder_final.keras` / `vae_decoder_final.keras` do not run standalone

Each is a complete, ordinary Keras Functional model, and
`tf.keras.models.load_model(path, safe_mode=False)` — `safe_mode=False` is required
because of the log-var clipping `Lambda` layer — loads the graph/weights. But in a
fresh process this currently raises `NameError: name 'tf' is not defined` when the
model is called (see the workaround note below), and even once loaded, that is
**not** enough to reproduce the VAE's actual inference behavior:

- The **reparameterization trick** (`z = z_mean + exp(0.5*z_log_var) * eps`) that
  turns the encoder's two outputs into a latent sample is plain Python code inside
  the `VAE2.call()` method in the notebook — it is not part of either saved model's
  graph/config.
- The **combined loss** (`recon_loss + beta * kl_loss`, beta=0.25) used during
  training is likewise only defined in `VAE2._compute_losses()` in the notebook.

To actually run the full encode → sample → decode pipeline (or retrain), you need
the `VAE2` class definition from `phase3_vae_autoencoder.ipynb` (section 9) — not
just these two `.keras` files.

**`NameError` on load, workaround:** Keras's `Lambda.from_config` → `func_load`
rebuilds the log-var-clip closure using its own `python_utils` module's globals,
which never imports `tensorflow` — so calling the loaded encoder raises `NameError:
name 'tf' is not defined`. Fix before calling `load_model`:
`import keras.src.utils.python_utils as u; u.tf = tf`. Discovered and worked around
in `05_contamination_sweep/evaluate_contamination_sweep.py`.

## `04_phase3_models/superseded/`

`vae_encoder_latent10.keras` / `vae_decoder_latent10.keras` are the beta=1.0
baseline from before the collapse fix (section 9.3) — 1/10 active latent
dimensions, no longer used. Kept only for comparison/traceability against the
beta=0.25 result; the actual model is `vae_encoder_final.keras` /
`vae_decoder_final.keras` above.
