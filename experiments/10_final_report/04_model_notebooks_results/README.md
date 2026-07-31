# 04_model_notebooks_results — Model eğitim notebook'larından çıkarılan grafikler ve sayısal sonuçlar

Bu klasör, `04_model_notebooks/dense_v1.ipynb` ve `04_model_notebooks/vae_v1.ipynb`
(v1, 18-feature, concurrency_src_1s yok) çalıştırılmış notebook'larının
sonuç/değerlendirme hücrelerinde üretilen PNG grafiklerin dışa aktarılmış
hâlini ve bu hücrelerdeki sayısal çıktıların (print/tablo) `results.md`
özetini içerir. Notebook dosyalarının kendisi buraya kopyalanmadı — sadece
çıktıları.

## dense_v1/ — Dense autoencoder (v1, 18 feature)

Kaynak notebook: `phase3_dense/phase3_dense_autoencoder.ipynb`.

| Dosya | İçerik |
|---|---|
| `01_loss_curve_demo_run.png` | Tek çalıştırma (seed=0, full_features) train/val loss eğrisi |
| `02_reconstruction_error_histogram.png` | Test setinde benign vs. attack reconstruction error histogramı |
| `03_roc_curve.png` | ROC eğrisi (test, seed=0, full_features) |
| `04_ablation_full_vs_no_conn_state.png` | full_features vs. no_conn_state ablation karşılaştırması (5-seed) |
| `results.md` | Tüm sayısal sonuçlar (5-seed tabloları, ROC-AUC, reconstruction error istatistikleri, ablation delta'ları) |

## vae_v1/ — VAE (v1, 18 feature)

Kaynak notebook: `phase3_vae/phase3_vae_autoencoder.ipynb`. Bu notebook bir
**mimari/hiperparametre seçim** notebook'u (latent-dim sweep + beta/KL-annealing
karşılaştırması) — final rapordaki 5-seed `contam_0pct` kanonik değerlendirmeyle
aynı çalıştırma değil, bkz. `dense_v1/results.md` ve `vae_v1/results.md` içindeki
notlar.

| Dosya | İçerik |
|---|---|
| `01_loss_curves_kl_collapse_check.png` | Seçilen model (latent=10) için total/recon/KL loss eğrileri |
| `02_test_evaluation_roc_and_histogram.png` | Test AUC + ROC + reconstruction error histogramı (latent=10, beta=1.0 baseline) |
| `03_loss_curves_beta_variants_comparison.png` | beta=1.0/0.5/0.25 ve KL-annealing varyantlarının loss eğrileri (yan yana) |
| `results.md` | Latent-dim sweep, threshold kalibrasyonu, beta-varyant karşılaştırması ve final seçim/test sonuçları |
