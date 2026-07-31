"""
Standalone proof that the Lambda-layer deserialization bug is fixed and that
ClipLogVar/VAE2 are now centrally importable from phase3_vae/model_layers.py
(not defined only inline in the notebook).

Run from anywhere: `python phase3_vae/scripts/verify_model_loading.py`
No custom_objects= dict, no safe_mode=False, no monkeypatching Keras
internals - just the import, then a plain load_model() call.
"""
import sys
from pathlib import Path

import numpy as np
import keras

PHASE3_VAE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE3_VAE_DIR))
from model_layers import ClipLogVar, VAE2  # noqa: F401  (import registers both with Keras)

MODEL_DIR = PHASE3_VAE_DIR / "04_phase3_models"


def main() -> None:
    encoder = keras.models.load_model(MODEL_DIR / "vae_encoder_final.keras", safe_mode=True)
    decoder = keras.models.load_model(MODEL_DIR / "vae_decoder_final.keras", safe_mode=True)
    print("Loaded vae_encoder_final.keras / vae_decoder_final.keras: "
          "no custom_objects=, safe_mode=True (default), classes imported from model_layers.")

    x = np.random.randn(5, 18).astype("float32")
    z_mean, z_log_var = encoder(x)
    assert z_mean.shape == (5, 10) and z_log_var.shape == (5, 10)
    assert float(z_log_var.numpy().min()) >= -10.0 and float(z_log_var.numpy().max()) <= 10.0
    print(f"encoder call OK: z_mean{tuple(z_mean.shape)}, z_log_var{tuple(z_log_var.shape)} "
          f"(clipped range confirmed within [-10, 10])")

    recon = decoder(z_mean)
    assert recon.shape == (5, 18)
    print(f"decoder call OK: recon{tuple(recon.shape)}")

    print("\nPASS: model_layers.ClipLogVar/VAE2 are sufficient for any external "
          "script to load and run the final VAE encoder/decoder.")


if __name__ == "__main__":
    main()
