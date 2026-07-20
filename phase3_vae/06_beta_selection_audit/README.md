# Beta-varyant seçimi audit'i — test set sızıntısı

## Bulgu: SIZINTI VAR (kod düzeltildi, sayılar değişmedi)

`phase3_vae_autoencoder.ipynb`, bölüm 9 (beta karşılaştırması: 1.0 / 0.5 /
0.25 / KL-annealing), iki bağımsız sızıntı içeriyordu:

1. **Test seti 4 varyantın HER BİRİ için çalıştırılmış.**
   Cell 22, satır 20-22: döngünün her adımında (`for name, beta_target,
   anneal_epochs in VARIANTS:`) `X_test`/`y_test` üzerinde `test_auc` ve
   `test_f1` hesaplanmış, `variant_rows`'a eklenmiş — seçim yapılmadan
   **önce**, 4 kez.

2. **Seçim kriteri VAL AUC değil, TEST AUC üzerinden hesaplanmış.**
   Cell 26, satır 3/11/14/19/22: `baseline_auc = variant_df.loc[baseline_name,
   "test_auc"]` ve döngü içinde `auc = variant_df.loc[name, "test_auc"]`.
   Tolerans karşılaştırması (`drop <= ACTIVE_DIM_AUC_TOLERANCE`) ve kazananın
   belirlenmesi tamamen `test_auc` sütunu üzerinden yapılmış. `val_auc`
   sütunu hesaplanıyordu (Cell 22, satır 16) ama seçim mantığında hiç
   kullanılmamış — sadece raporlama amaçlıydı.

Not: bölüm 3-4'teki **latent boyutu seçimi** (6/8/10 arasından latent=10
seçen kısım, Cell 10) temizdi — orada karar yalnızca `val_auc` üzerinden
veriliyor, test seti hiç dokunulmuyor. Sızıntı yalnızca bölüm 9 (beta
karşılaştırması) ile sınırlıydı.

## Düzeltme

`rerun_beta_selection.py`: aynı 4 varyant, aynı hiperparametrelerle
(latent=10, patience=12, clipnorm=1.0, z_log_var clip [-10,10], seed=0)
yeniden eğitildi. Fark:

- Karşılaştırma ve seçim **sadece** `val_indices.csv` üzerinden yüklenen
  veriyle yapılıyor (val AUC + aktif latent boyut sayısı, mevcut ≤0.03 val
  AUC toleransı kuralı korunarak).
- `test_indices.csv` verisi kazanan konfigürasyon belirlenene kadar hiçbir
  hesaplamaya girmiyor.
- Kazanan (`beta=0.25`) belirlendikten **sonra**, test setinde tek bir kez
  değerlendirme yapılıyor.
- Modeller `06_beta_selection_audit/models/` altına kaydedildi;
  `04_phase3_models/vae_*_final.keras` dosyalarına dokunulmadı.

## Eski (sızıntılı) vs yeni (temiz) sayılar

| | Eski (sızıntılı, test her varyant için koşuldu + seçim test_auc'ye göre) | Yeni (temiz, seçim val_auc'ye göre, test tek seferlik) |
|---|---|---|
| Seçilen varyant | beta=0.25 | beta=0.25 |
| Seçim kriteri metriği | test_auc (yanlış) | val_auc (doğru) |
| val AUC (beta=0.25) | raporlanmamış | 0.8432 |
| val AUC (baseline beta=1.0) | raporlanmamış | 0.8014 |
| Test AUC (final) | 0.9372 | 0.9372 |
| Test F1 (pctl95, final) | 0.8413 | 0.8413 |

## Yorum

Kod sızıntı içeriyordu ve düzeltilmesi gerekiyordu — ama **sonuç sayıları
değişmedi**. Sebebi: beta=0.25, val_auc'de de (0.8432) diğer 3 varyanttan
açık ara önde (en yakın rakip baseline 0.8014, fark 0.0418) ve aktif boyut
sayısında da baseline'ı geçiyor (3 vs 1), yani zaten hem val hem test
metriğine göre net kazanan. Sızıntılı sürüm şans eseri val-only sürecin de
seçeceği konfigürasyonu seçmiş. Dolayısıyla `0.9372` / `0.8413` sayıları artık
**metodolojik olarak sağlam gerekçeyle** doğrulanmış durumda — ama bu,
kodun düzeltilmesini gereksiz kılmıyor: sızıntı yapısal bir hataydı, bu sefer
tesadüfen zarar vermedi.

## Önerilen sonraki adım

`phase3_vae_autoencoder.ipynb` cell 22 ve 26, bu script'teki mantığa göre
düzeltilmeli (test hesaplaması döngüden çıkarılıp seçimden sonraki tek bir
hücreye taşınmalı, seçim kriteri `val_auc` kullanmalı). Bu audit klasöründeki
`rerun_beta_selection.py` referans alınabilir. Onay verilirse bu değişikliği
notebook'a da uygularım; `04_phase3_models/` ve `latest_run/` mekanizmasına
bu audit sırasında dokunulmadı.
