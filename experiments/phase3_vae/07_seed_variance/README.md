# Final VAE konfigürasyonu — seed varyansı (latent=10, beta=0.25)

## Amaç

`phase3_vae_autoencoder.ipynb` bölüm 9'da seçilen final konfigürasyon
(latent=10, beta=0.25, dropout=0.1, patience=12, Adam clipnorm=1.0,
z_log_var clip [-10,10]) **tek bir seed** (SEED=0) ile eğitilip test
setinde tek sefer raporlandı (AUC=0.9372, F1=0.8413 — bkz.
[`06_beta_selection_audit/`](../06_beta_selection_audit/README.md)). Bu
sayı ne kadar temsilci? Aynı mimari/hiperparametreler sabit tutulup
sadece ağırlık-başlatma seed'i değiştirilerek (0-9, 10 seed) bu sorunun
cevabı ölçüldü.

**Test seti kullanımı hakkında not:** bu çalışmada hiçbir seçim
yapılmıyor — 10 seed'in hepsi test setinde skorlandı çünkü amaç sadece
zaten sabitlenmiş TEK bir konfigürasyonun dağılımını gözlemlemek.
06_beta_selection_audit'teki sorun farklıydı: orada 4 **farklı aday**
test setinde skorlanıp aralarından biri seçiliyordu (seçim + sızıntı).
Burada seçim yok, sadece gözlem var — metodolojik olarak sorunsuz.

## Sonuçlar (10 seed, latent=10, beta=0.25)

Tam tablo: [`results_per_seed.csv`](results_per_seed.csv), özet:
[`results_summary.csv`](results_summary.csv).

| seed | val AUC | test AUC | test F1 (pctl95) | aktif latent boyut | epochs | |
|---|---|---|---|---|---|---|
| 0 | 0.8432 | **0.9372** | 0.8413 | 3/10 | 200 | ← mevcut kayıtlı final model |
| 4 | 0.8328 | 0.9330 | 0.8375 | 1/10 | 164 | |
| 9 | 0.8291 | 0.9272 | 0.8355 | 6/10 | 100 | |
| 7 | 0.8067 | 0.9233 | 0.8537 | 6/10 | 115 | |
| 1 | 0.8138 | 0.9220 | 0.8488 | 9/10 | 68 | |
| 6 | 0.7966 | 0.9195 | 0.8493 | 8/10 | 109 | |
| 3 | 0.8004 | 0.9189 | 0.8517 | 2/10 | 163 | |
| 2 | 0.8001 | 0.9175 | 0.8576 | 2/10 | 130 | |
| 5 | 0.7949 | 0.9157 | 0.8457 | 8/10 | 79 | |
| 8 | 0.7109 | 0.8821 | 0.8472 | 8/10 | 36 | en düşük — aykırı değer |

(Test AUC'ye göre azalan sırayla.)

**Özet istatistikler (n=10):**

| metrik | mean | std | median | trimmed_mean (0.2) |
|---|---|---|---|---|
| val AUC | 0.8029 | 0.0364 | 0.8036 | 0.8078 |
| test AUC | 0.9197 | 0.0149 | 0.9208 | 0.9214 |
| test F1 (pctl95) | 0.8468 | 0.0070 | 0.8480 | 0.8473 |
| aktif latent boyut | 5.30 | 3.02 | 6.00 | 5.50 |

**Raporlanabilir cümle:**

> Final VAE konfigürasyonu (latent=10, beta=0.25), 10 bağımsız
> ağırlık-başlatma seed'i üzerinden **test AUC = 0.9197 ± 0.0149**,
> **test F1 = 0.8468 ± 0.0070** (mean ± std) veriyor. Mevcut kayıtlı
> final model (seed=0) bu dağılımın en üstünde: test AUC=0.9372,
> ortalamanın ~1.2 std üzerinde — yani daha önce raporlanan sayı
> tesadüfen dağılımın iyi ucundan bir örnek, tipik/ortalama bir sonuç
> değil.

## Yorum

**AUC/F1 tarafı:** seed varyansı orta düzeyde (test AUC std=0.0149, ~%1.6
bağıl) — bir aykırı değer (seed=8, AUC=0.8821, en erken durmuş run:
sadece 36 epoch) dışarıda tutulursa geri kalan 9 seed 0.9157-0.9372
aralığında, daha sıkı bir bant. Mevcut kayıtlı model (seed=0) bu 10
seed'in **en iyisi** — ortalamanın üstünde, "iyimser" bir nokta tahmini.
Rapor edilirken tek-seed 0.9372 sayısı yerine bu ± aralığın (veya en
azından "seed=0 dağılımın üst ucunda" notunun) birlikte verilmesi daha
dürüst bir temsil olur.

**Aktif latent boyut tarafı — çok tutarsız, bir sonraki collapse
çalışmasına girdi:** aktif boyut sayısı 1/10 ile 9/10 arasında değişiyor
(std=3.02, ortalamaya göre bağıl varyasyon çok yüksek — mean'in
%57'si). Daha da çarpıcısı: **aktif boyut sayısı ile test AUC arasında
görünür bir ilişki yok.** seed=4 sadece **1/10** aktif boyutla ikinci en
iyi test AUC'yi (0.9330) veriyor; seed=8 ise **8/10** aktif boyutla en
kötü performansı (0.8821) veriyor. Bu, bölüm 9.3'ün orijinal
gerekçesini ("daha fazla aktif boyut = daha iyi kullanılan latent uzayı")
zayıflatıyor — en azından tek bir seed'e dayanarak "beta=0.25, aktif
boyutu 1'den 3'e çıkardı, bu iyi bir şey" demek, 10-seed tablosunda aktif
boyut sayısının kendisinin oynaklığı (posterior collapse'ın seed'e göre
ne kadar dengesiz olduğu) yanında ikinci planda kalıyor. Erken durma
(early stopping) epoch sayısı ile aktif boyut sayısı arasında kabaca ters
bir ilişki var gibi görünüyor (kısa süren run'lar — seed 1, 5, 6, 8 — daha
çok aktif boyutla bitiyor, uzun süren run'lar — seed 0, 3, 4 — daha az),
ki bu da collapse'ın patience/early-stopping zamanlamasıyla etkileşimini
işaret ediyor; sistematik bir collapse çalışmasında bu ilişki ayrıca
incelenmeli.

## Dosyalar

- `train_seed_variance.py` — script (mimari/hiperparametreler notebook
  bölüm 9'dan birebir kopyalandı, sadece seed değişiyor)
- `results_per_seed.csv` — 10 satır, seed başına tüm metrikler
- `results_summary.csv` — mean/std/median/trimmed_mean özet satırı

Hiçbir final/root dosyaya dokunulmadı (`04_phase3_models/`,
`latest_run/`, `06_beta_selection_audit/` değişmedi); bu klasördeki
modeller diskte tutulmuyor (script sadece metrik hesaplıyor, `.keras`
kaydetmiyor).
