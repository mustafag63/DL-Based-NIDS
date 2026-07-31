# Exploratory / with-replacement — ana sweep'e dahil değil

Bu klasördeki dosyalar `window_resampled_{22,25,28,30}pct` (with-replacement
attack sampling, `_dupN` etiketli tekrar eden satırlar içeriyor) üzerinde
eğitilmiş modellerin ve sonuçların **taşınmış** hâli — silinmedi, ana
`05_contamination_sweep/` sweep'inden çıkarıldı.

**Neden:** with-replacement örneklemenin kendisi, bu seviyelerde gözlenen
"toparlanma" (PR-AUC'un %20+ civarında tekrar yükselmesi) için olası bir
konfaunt/artefakt riski taşıyor. Bağımsız, tam without-replacement bir
kontrol noktası (`window_resampled_22pct_clean`, ana `05_contamination_sweep/`
altında) benzer bir toparlanma gösterdi — bu artefakt şüphesini büyük ölçüde
azalttı ama %25-30 aralığı hâlâ without-replacement doğrulanmadı.

Detaylı yazı: `../README.md`'nin "Exploratory / with-replacement deneme"
bölümü.

İçerik:
- `02_contaminated_train_sets/train_contam_{22,25,28,30}pct.csv`
- `04_models/contam_{22,25,28,30}pct/` (4 seviye × 5 seed = 20 model)
- `04_models/training_run_log_with_replacement.json`
- `05_results/results_per_seed_with_replacement.csv` (20 satır, 5-seed × 4 seviye)

Bu verileri ana sweep'in `results_per_seed.csv`/`results_summary.csv`/
`contamination_curve.png`'siyle birleştirmeyin — ayrı, doğrulanmamış bir
kol olarak kalmalı.
