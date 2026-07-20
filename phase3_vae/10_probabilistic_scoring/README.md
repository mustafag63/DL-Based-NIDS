# Anomali skoruna KL/olasılıksal bileşen eklemek işe yarıyor mu?

## Amaç

Final VAE konfigürasyonu (latent=10, beta=0.25, [`08_beta_multiseed/`](../08_beta_multiseed/README.md)'de
doğrulandı) **hiç değiştirilmeden**, sadece **inference zamanındaki
anomali skoru** üç farklı şekilde hesaplanıp karşılaştırıldı. Model
yeniden eğitilmedi; sadece skor fonksiyonu değişti.

## Üç skor tanımı

- **(a) baseline** — saf reconstruction MSE: `mean((x - recon)^2)`. Şu ana
  kadar `phase3_vae/`'deki tüm deneylerin kullandığı skor.
- **(b) elbo_score** — training loss'un per-sample, inference-zamanı hali:
  `recon_loss_sum + beta * KL`, `recon_loss_sum = sum((x-recon)^2)`,
  `KL = -0.5 * sum(1 + log_var - mu^2 - exp(log_var))`. Modelin eğitim
  sırasında minimize ettiği şeyin ta kendisi, ama artık batch ortalaması
  değil örnek başına.
- **(c) recon_prob** — An & Cho (2015) "reconstruction probability":
  `z ~ q(z|x)`'den Monte Carlo ile **L=10** kez örnekleme, her örneklemede
  decoder çıktısının Gaussian log-likelihood'unu hesaplama, ortalamasını
  alma. Anomali skoru olarak **negatif** ortalama log-likelihood kullanıldı
  (diğer iki skorla aynı yönde: yüksek = daha anormal).
  **Varsayım:** decoder'ın varyans çıktısı yok (lineer, deterministik
  çıktı) — log-likelihood hesabı birim varyanslı (σ²=1) izotropik Gaussian
  varsayıyor, bu da modelin eğitildiği ham-MSE loss'un zaten örtük olarak
  varsaydığı şeyle tutarlı bir yaklaştırma. Gerçek bir varyans-kafası
  (variance head) olsaydı daha doğru olurdu; bu bir sınırlama olarak not
  edilmeli.

## Yöntem

`score_comparison.py`: 5 model (seed 0-4, latent=10, beta=0.25,
`08_beta_multiseed/` ile aynı hiperparametreler ve protokol) sıfırdan
eğitildi — **mevcut kayıtlı final `.keras` dosyaları kullanılmadı**, çünkü
tek bir modelle mean±std raporlanamaz. Faz A: üç skorun val AUC'si her 5
modelde hesaplandı (test seti bu fazda hiç yüklenmedi). Faz B: sadece
kazanan skor fonksiyonu, aynı 5 modelin test setinde bir kez
değerlendirilmesiyle raporlandı (seçim test'e dayanmadı — sadece gözlem).

## Adım 2 sonucu — val AUC karşılaştırması (n=5 seed)

| skor | val AUC (mean±std) | ortalama hesaplama süresi (6576 satır) |
|---|---|---|
| **recon_prob** | **0.8264 ± 0.0208** | 0.0323 sn |
| baseline | 0.8181 ± 0.0194 | 0.0084 sn |
| elbo_score | 0.7509 ± 0.0383 | 0.0060 sn |

Tam veri: [`val_score_comparison_per_seed.csv`](val_score_comparison_per_seed.csv),
[`val_score_comparison_summary.csv`](val_score_comparison_summary.csv).

**recon_prob en yüksek ortalamayı veriyor, ama fark istatistiksel olarak
anlamlı değil.** Welch t-testi (recon_prob vs baseline): **p=0.5316** —
std bantları geniş ölçüde örtüşüyor. Yani "recon_prob, baseline'dan
kesin olarak daha iyi" denemez; sadece bu 5 seed'lik örneklemde hafifçe
önde çıktı.

**elbo_score açıkça daha kötü** (0.7509±0.0383) — hem ortalaması düşük
hem std'si en yüksek (en tutarsız). Bunun nedeni muhtemelen KL teriminin
zaten [`09_collapse_investigation/`](../09_collapse_investigation/README.md)'da
gösterilen seed'e bağlı, AUC ile ilişkisiz oynaklığı: KL'yi doğrudan
skora eklemek, anomali sinyaline alakasız bir gürültü kaynağı katıyor.

## Adım 3 sonucu — kazananın (recon_prob) test performansı (n=5, tek sefer)

| | test AUC (mean±std) | test F1 (mean±std) | n |
|---|---|---|---|
| **recon_prob (bu denetim)** | **0.9312 ± 0.0102** | 0.8524 ± 0.0116 | 5 |
| baseline, `07_seed_variance/` | 0.9197 ± 0.0149 | — | 10 |
| baseline, `08_beta_multiseed/` | 0.9259 ± 0.0095 | 0.8474 ± 0.0099 | 5 |

Tam veri: [`winner_test_per_seed.csv`](winner_test_per_seed.csv).

recon_prob'un test AUC'si (0.9312±0.0102), baseline'ın iki bağımsız
ölçümüyle (0.9197±0.0149 ve 0.9259±0.0095) geniş ölçüde örtüşen bir
aralıkta — yine "kesin olarak daha iyi" denemez, ama en azından hiçbir
performans kaybı yok, aksine tutarlı biçimde hafif önde.

## Hesaplama maliyeti (üretilebilirlik açısından)

| skor | ort. süre (6576 satır) | baseline'a oran |
|---|---|---|
| baseline | 0.0084 sn | 1x |
| elbo_score | 0.0060 sn | 0.7x |
| recon_prob (L=10) | 0.0323 sn | **~3.8x** |

recon_prob, L=10 Monte Carlo örneklemesi nedeniyle decoder'ı 10 kez
çalıştırıyor (baseline 1 kez) — bu yüzden ~3.8x daha yavaş (tam 10x değil,
çünkü encoder tek seferlik ve L döngüsü vektörleştirilmiş numpy
işlemleriyle amorti ediliyor). Mutlak olarak hâlâ çok ucuz: 6576 satır
için 32ms — bu ölçekte hiçbir gerçek zamanlı kullanım senaryosunda sorun
olmaz. L düşürülerek (örn. L=5) maliyet yarıya inebilir, AUC kaybı büyük
ihtimalle ölçülemeyecek kadar küçük olur (denenmedi, ileri çalışma
notu). Çok daha büyük batch'lerde veya çok düşük gecikme (sub-ms)
gerektiren senaryolarda bu ~4x fark önemli olabilir; bu projenin ölçeği
için değil.

## Öneri

**Mevcut saf-reconstruction skoruna (baseline) devam edilebilir — geçiş
zorunlu değil, ama recon_prob'a geçmek de savunulabilir, düşük riskli bir
iyileştirme.**

Gerekçe:
- recon_prob, val'de de test'te de baseline'dan hafifçe önde, ama fark
  istatistiksel olarak anlamlı değil (p=0.53) — "kanıtlanmış bir
  iyileştirme" olarak sunulamaz.
- Hiçbir senaryoda recon_prob baseline'dan kötü çıkmadı — yani geçişin
  aşağı yönlü riski yok, sadece ~4x ekstra (yine de mutlak olarak küçük)
  hesaplama maliyeti var.
- **elbo_score kullanılmamalı** — KL teriminin skora doğrudan eklenmesi,
  09_collapse_investigation'da zaten gösterilen "aktif boyut sayısı
  AUC'yle ilişkisiz" bulgusuyla tutarlı biçimde, anlamlı sinyali
  bozuyor ve performansı belirgin şekilde düşürüyor.
- Eğer üretimde en basit/en hızlı/en az hareketli parçalı çözüm
  isteniyorsa: **baseline'da kalın.** Eğer birkaç ms ekstra maliyet kabul
  edilebilirse ve olasılıksal bir skorun yorumlanabilirliği (log-likelihood
  temelli eşikleme, kalibre olasılık) değerli görülüyorsa: **recon_prob'a
  geçiş** makul bir seçim, ama "zorunlu düzeltme" değil "isteğe bağlı
  iyileştirme" olarak ele alınmalı.

## Dosyalar

- `score_comparison.py` — script (3 skor tanımı, 5-seed val karşılaştırma, kazananın tek-seferlik test değerlendirmesi)
- `val_score_comparison_per_seed.csv` — Faz A, 5 satır (seed × 3 skor)
- `val_score_comparison_summary.csv` — Faz A özet (skor başına mean/std/süre)
- `winner_test_per_seed.csv` — Faz B, kazanan (recon_prob) için 5 seed'lik test sonucu

Hiçbir final/root/önceki-audit dosyasına dokunulmadı (`04_phase3_models/`,
`latest_run/`, `06_beta_selection_audit/`, `07_seed_variance/`,
`08_beta_multiseed/`, `09_collapse_investigation/`, `model_layers.py`
değişmedi — bu denetim kendi 5 modelini eğitti, kayıtlı final modele
dokunmadı).
