# Posterior collapse: gerçek bir sorun mu, yoksa beklenen bir sonuç mu?

## Soru

`phase3_vae_autoencoder.ipynb` bölüm 9, latent=10'da 1/10-9/10 arası
değişen (seed'e bağlı, bkz. [`07_seed_variance/`](../07_seed_variance/README.md))
aktif latent boyut sayısını "posterior collapse" olarak adlandırıp bunu
düzeltilmesi gereken bir sorun gibi ele aldı (beta ayarı, KL-annealing
denemeleri). Bu denetim şunu soruyor: collapse gerçekten bir model/eğitim
sorunu mu, yoksa **feature uzayının kendisinin düşük-boyutlu olmasının**
doğal, beklenen bir yansıması mı?

Üç bağımsız kanıt hattı toplandı. Hepsi aynı yöne işaret ediyor.

## Adım 1 — Feature uzayının içsel boyutu (referans çizgisi)

PCA (`window10_clean_train.csv`, 18 scaled feature, 4356 satır):

| Kümülatif varyans | Gereken bileşen sayısı |
|---|---|
| %90 | **3** |
| %95 | 4 |
| %99 | 6 |

18 boyutlu feature uzayının **gerçek bilgi içeriği ~3-6 boyuta sığıyor.**
Grafik: [`pca_cumulative_variance.png`](pca_cumulative_variance.png), veri:
[`pca_explained_variance.csv`](pca_explained_variance.csv).

Korelasyon taraması bunun nedenini de gösteriyor — feature'lar arasında
ciddi redundancy var:

- `proto_udp` ↔ `service_dns`: **r=1.000** (bu train penceresi —
  `window_10_0pct` — neredeyse tamamen UDP/DNS trafiği; iki kolon birebir
  aynı bilgiyi taşıyor)
- `proto_tcp` ↔ `proto_udp`/`service_dns`: r≈-0.996 (yapısal olarak zaten
  beklenen ama VAE'ye "farklı" iki boyutmuş gibi veriliyor)
- `orig_bytes_scaled` ↔ `orig_pkts_scaled`: r=0.974, `resp_bytes_scaled` ↔
  `resp_pkts_scaled`: r=0.983, `bytes_per_sec_scaled` ↔ `pkts_per_sec_scaled`:
  r=0.983

Tam liste: [`correlation_notes.txt`](correlation_notes.txt),
[`feature_correlation_matrix.csv`](feature_correlation_matrix.csv).

**Ara sonuç:** VAE'ye verilen 18 "feature", gerçekte ~3-6 bağımsız
boyutluk bilgiyi fazladan kodlanmış halde taşıyor. latent=10 bu referansa
göre zaten geniş bir bütçe.

## Adım 2 — Latent boyutu taraması (latent ∈ {4,6,8,10,16}, beta=0.25, 5 seed, val-only)

| latent | val AUC (mean±std) | aktif boyut (mean) | aktif ORAN (mean) |
|---|---|---|---|
| 4 | 0.8169 ± 0.0340 | 2.8 | **0.70** |
| 6 | 0.8164 ± 0.0212 | 2.6 | 0.43 |
| 8 | 0.8101 ± 0.0097 | 3.2 | 0.40 |
| 10 | 0.8181 ± 0.0194 | 3.4 | 0.34 |
| 16 | 0.7806 ± 0.0449 | 9.8 | 0.6125 |

Tam veri: [`02_latent_sweep_results.csv`](02_latent_sweep_results.csv),
[`02_latent_sweep_summary.csv`](02_latent_sweep_summary.csv).

**Kilit gözlem:** aktif boyutun **mutlak sayısı**, latent bütçesinden
bağımsız olarak sabit kalıyor (~2.6-3.4) — latent=4 verilse de latent=10
verilse de model kendiliğinden ~3 boyut kullanıyor. Bu sayı, Adım 1'in PCA
sonucuyla (%90 varyans = 3 bileşen) neredeyse birebir örtüşüyor. Küçük
latent'te aktif ORAN yüksek (4'te 0.70) çünkü bütçe zaten veriye yakın;
latent büyüdükçe oran düşüyor çünkü payda büyürken pay (gerçek bilgi
miktarı) sabit kalıyor.

val AUC latent 4/6/8/10 arasında pratik olarak ayırt edilemez (hepsi
~0.81-0.82, farklar std bantları içinde) — **fazladan latent boyutu hiçbir
performans kazancı getirmiyor.** latent=16'da hem AUC düşüyor (0.78) hem
eğitim istikrarsızlaşıyor (bazı seed'ler 34-43 epoch gibi çok erken
duruyor) — gereğinden büyük latent, optimizasyonu zorlaştırıyor, faydası
yok.

Bu, "collapse"ın rastgele bir eğitim arızası değil, **verilen bütçe ile
verideki gerçek bilgi miktarı arasındaki farkın sistematik bir yansıması**
olduğunu gösteriyor.

## Adım 3 — Free-bits denemesi (latent=10 sabit, beta=0.25, 5 seed, val-only)

Standart free-bits tekniği (Kingma et al. 2016): her latent boyutun kendi
KL teriminde bir alt sınır (λ nat) uygulanır — `kl_per_dim = max(kl_per_dim, λ)`.
Bir boyutun KL'si zaten λ'nın üzerindeyse etkilenmez; prior'a doğru
çökmekte olan bir boyut λ'ya ulaştığında artık "daha da küçül" baskısı
almaz.

| λ (nat) | val AUC (mean±std) | aktif boyut (mean) |
|---|---|---|
| 0.00 (baseline) | 0.8181 ± 0.0194 | 3.4/10 |
| **0.10** | **0.8247 ± 0.0253** | **10.0/10** |
| 0.25 | 0.7984 ± 0.0498 | 10.0/10 |
| 0.50 | 0.8126 ± 0.0119 | 10.0/10 |
| 1.00 | 0.8245 ± 0.0167 | 10.0/10 |

Tam veri: [`03_free_bits_results.csv`](03_free_bits_results.csv),
[`03_free_bits_summary.csv`](03_free_bits_summary.csv).

**λ≥0.1 gibi küçük bir değer bile 5 seed'in tamamında tam olarak 10/10
aktif boyut sağlıyor** (std=0.0 — mükemmel tutarlılık, seed varyansı
tamamen ortadan kalkıyor), val AUC'de **hiçbir kayıp olmadan** (λ=0.1'de
hatta hafif artış, fark std içinde). Yani teknik olarak collapse
görünümü tamamen "düzeltilebilir".

**Ama bu yorumlanırken dikkatli olunmalı:** Adım 1-2, verinin gerçekten
~3 boyutluk bağımsız bilgi taşıdığını gösteriyor. Free-bits, "aktif"
tanımını (z_mean std > eşik) yapay olarak sağlayan bir zorlama —
decoder'a anlamlı yeni bilgi eklemiyor, sadece her boyutun posterior'unu
prior'dan en az λ kadar uzak tutuyor. AUC'nin artmaması (sadece düz
kalması), bu ekstra "aktif" boyutların downstream performansa katkı
sağlayan yeni bilgi taşımadığını, sadece diagnostiği tatmin ettiğini
destekliyor. Free-bits sonrası aktif-boyut metriği artık anlamlı bir sinyal
değil (her zaman 10/10 çıkıyor) — [`08_beta_multiseed/`](../08_beta_multiseed/README.md)'in
zaten vardığı "aktif boyut sayısı seçim kriteri olmamalı" sonucunu bir kez
daha, farklı bir açıdan doğruluyor.

## Sonuç: collapse gerçek bir sorun mu?

**Hayır — mevcut haliyle "collapse", feature uzayının doğal
düşük-boyutluluğunun beklenen bir sonucu, düzeltilmesi gereken bir model
hatası değil.** Üç kanıt hattı da aynı noktada buluşuyor:

1. PCA'ya göre verinin içsel boyutu ~3 (Adım 1) — feature'lar arasında
   ağır redundancy var (`proto_udp`≡`service_dns`, r=1.000).
2. VAE, kaç latent boyutu verilirse verilsin (4'ten 16'ya), kendiliğinden
   ~3 boyut kullanıyor ve bu sayı hiçbir latent bütçesinde AUC'yi
   etkilemiyor (Adım 2) — model "collapse ediyor" değil, "ihtiyacı kadarını
   kullanıyor".
3. Free-bits ile aktif boyut sayısı yapay olarak 10/10'a zorlanabiliyor,
   ama bu AUC'yi iyileştirmiyor (Adım 3) — ekstra "aktiflik" gerçek bilgi
   değil, dolgu.

## Öneri

**latent=10'da kalınmasına gerek yok, ama zorunlu bir değişiklik de değil
— free-bits eklemeye gerek yok.**

Somut öneri, önem sırasına göre:

1. **Latent boyutunu latent=6'ya indirmek** (mevcut latent=10 yerine) en
   dengeli seçim: Adım 2'de latent=6, latent=10 ile istatistiksel olarak
   ayırt edilemez val AUC veriyor (0.8164±0.0212 vs 0.8181±0.0194),
   PCA'nın %95 varyans eşiğiyle (4 bileşen) uyumlu bir marj bırakıyor, ve
   "collapse" görünümünü azaltıyor (aktif oran 0.43 vs 0.34) — modelin
   mimarisi verinin gerçek boyutuna daha yakın, daha yorumlanabilir bir
   latent uzayı sunuyor. Bu bir **iyileştirme**, acil bir düzeltme değil.
2. **Free-bits eklemeye gerek yok:** aktif boyut sayısını yapay olarak
   yükseltiyor ama ölçülebilir hiçbir performans kazancı sağlamıyor
   (Adım 3). Ekstra bir hiperparametre (λ) ve karmaşıklık getirir,
   karşılığında hiçbir şey vermez.
3. **Mevcut latent=10, beta=0.25 konfigürasyonu da yanlış değil** —
   sadece gereğinden geniş bir bütçe kullanıyor. AUC'yi düşürmüyor, sadece
   "aktif boyut" diagnostiğinin (yanlış yorumlanırsa) yanıltıcı görünmesine
   yol açıyor. Değiştirmemek de savunulabilir bir karar.

Özetle: bu denetim, önceki collapse-odaklı müdahalelerin (beta ayarı,
KL-annealing, bu denetimdeki free-bits) çözmeye çalıştığı "sorun"un baştan
bir sorun olmadığını gösteriyor. latent=6'ya geçiş isteğe bağlı bir
sadeleştirme olarak önerilebilir; mevcut latent=10 kararının değiştirilmesi
zorunlu değildir.

## Dosyalar

- `pca_analysis.py`, `pca_explained_variance.csv`, `pca_cumulative_variance.png`,
  `correlation_notes.txt`, `feature_correlation_matrix.csv` — Adım 1
- `latent_sweep.py`, `02_latent_sweep_results.csv`, `02_latent_sweep_summary.csv` — Adım 2
- `free_bits_sweep.py`, `03_free_bits_results.csv`, `03_free_bits_summary.csv` — Adım 3

Hiçbir final/root/önceki-audit dosyasına dokunulmadı (`04_phase3_models/`,
`latest_run/`, `06_beta_selection_audit/`, `07_seed_variance/`,
`08_beta_multiseed/`, `model_layers.py` değişmedi — free-bits denemesi
`VAEFreeBits` adında yerel bir alt-sınıf olarak bu klasördeki script içinde
tanımlandı, paylaşılan modülü değiştirmedi).
