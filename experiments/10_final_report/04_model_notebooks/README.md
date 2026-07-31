# 04_model_notebooks — Model eğitim notebook'ları (kopya)

Bu klasördeki notebook'lar, `phase3_dense/` ve `phase3_vae/` altındaki
orijinal eğitim notebook'larının **çalıştırılmış (output hücreleri dolu)
kopyalarıdır** — orijinaller kendi yerlerinde değişmeden duruyor, burada
sadece final rapora eşlik etmesi için kopyalanmış hâlleri var.

| Dosya | Model | Versiyon | Feature seti |
|---|---|---|---|
| `dense_v1.ipynb` | Dense autoencoder | v1 | 18 feature (concurrency_src_1s yok) |
| `vae_v1.ipynb` | VAE (Variational autoencoder) | v1 | 18 feature (concurrency_src_1s yok) |

**Not — v2 notebook yok:** Güncel kanonik model (19 feature,
`concurrency_src_1s` dahil, bkz. `07_final_written_report/`) sadece script
olarak üretildi — `09_dense_v2_comparison/dense_backend_v2.py` +
`evaluate_by_attack_type_dense_v2.py`, ve `10_vae_v2_comparison/
vae_backend_v2.py` + `evaluate_by_attack_type_vae_v2.py`. Bu script'lerin
karşılığı olan, çalıştırılmış bir v2 notebook hiçbir zaman üretilmedi;
dolayısıyla burada `dense_v2.ipynb` / `vae_v2.ipynb` yok. İstenirse
script'ler notebook formatına çevrilip çalıştırılabilir.

**Sade v2 inference figürleri var:** `../04_model_notebooks_results/dense_v2/`
ve `vae_v2/` içinde, zaten eğitilmiş kanonik v2 modellerinden (seed=0)
üretilmiş ROC eğrisi + reconstruction-error histogramı bulunuyor (bkz.
`06_scripts/report_generation/build_04_notebooks_v2.py`). Loss curve,
ablation ve latent-dim/beta sweep bölümleri YOK — bunlar retraining
gerektirir ve v1'in mimari seçimi v2'de değişmeden kullanıldığı için
tekrarlanmadı.

Kaynak (orijinal) dosyalar:
- `phase3_dense/phase3_dense_autoencoder.ipynb`
- `phase3_vae/phase3_vae_autoencoder.ipynb`
