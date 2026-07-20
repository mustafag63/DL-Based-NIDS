# window01_shift_test değerlendirmesi — final VAE'nin görülmemiş-benign genelleme yeteneği

## Amaç

`window01_shift_test.csv`, `window_01_0pct`'in ana train/val/test split'ine
hiç girmeyen yarısı — 274 flow, **tamamı benign**. `window_01`, 11 Temmuz
EDA'sında diğer 7 pencereden istatistiksel olarak saptığı için (daha yüksek
ortalama duration/bytes, duration CV=0.37) özellikle ayrılmıştı: "gerçek
ama görülmemiş bir benign dağılımı" karşısında modelin ne kadar dayanıklı
olduğunu ölçmek için. Final VAE (latent=10, beta=0.25, kayıtlı
`04_phase3_models/vae_encoder_final.keras`/`vae_decoder_final.keras`)
**yeniden eğitilmedi** — sadece inference çalıştırıldı.

## Adım 1-2 — Sonuç: FPR ve dağılım karşılaştırması

Eşik: val-benign pctl95 = **0.08808** (final modelin kendi val split'inden
kalibre edildi, notebook'taki aynı yöntem).

| grup | n | mean error | median error | std | FPR |
|---|---|---|---|---|---|
| train benign (`window_10_0pct`) | 4356 | 0.0346 | 0.0124 | 0.386 | 4.61% |
| test benign (windows 02-08 held-out) | 4678 | 0.0370 | 0.0127 | 0.512 | 4.19% |
| **window01_shift_test** | **274** | **0.1521** | **0.0180** | **1.455** | **7.30%** |

Tam veri: [`shift_test_results.json`](shift_test_results.json),
üç histogram: [`three_distribution_histograms.png`](three_distribution_histograms.png).

**FPR %5'in (eşik tanımı gereği beklenen taban) hafifçe üzerinde: %7.30**
(20/274 flow yanlış pozitif). train/test benign FPR'leri (%4.61, %4.19)
beklenen ~%5 tabanına yakın — yani sapma sadece `window01_shift_test`'e
özgü.

**Dağılımın şekli önemli:** median (0.018) train/test benign medyanlarına
(0.012-0.013) oldukça yakın — flow'ların **çoğu** normal görünüyor. Ama
mean (0.152), medyandan **8x büyük** — birkaç aşırı uç değer ortalamayı
yukarı çekiyor. En büyük hata 23.3 (tek bir flow), sonra 5.94, 1.91, 1.87 —
274 flow'un sadece 20'si eşiği geçiyor ama bunlardan birkaçı çok büyük
hatalarla geçiyor. Yani: **flow'ların büyük çoğunluğu (%92.7) train
dağılımıyla tutarlı, küçük bir azınlık (%7.3, ağırlıklı olarak birkaç aşırı
uç değer) gerçekten sapıyor.**

## Adım 2 (devam) — Dense ile yan yana karşılaştırma

Dense'in 10 modeli (5 seed × 2 varyant) `phase3_dense/04_phase3_models/`'dan
yüklenip aynı `window01_shift_test.csv` üzerinde taze çalıştırıldı
(`evaluate_dense_shift_test.py` — mevcut `analysis/window01_shift_test_evaluation.py`
ile aynı mantık, sadece path'ler `phase3_dense/` klasör yapısına
güncellendi; orijinal script'e dokunulmadı).

| model | test-benign FPR | window01_shift FPR | fark (shift − test) |
|---|---|---|---|
| Dense full_features (5 seed) | 2.27% ± 0.76% | **11.31% ± 0.89%** | **+9.04 pp** |
| Dense no_conn_state (5 seed) | 1.87% ± 1.05% | 10.73% ± 0.99% | +8.86 pp |
| **VAE final (latent=10, beta=0.25)** | 4.19% | **7.30%** | **+3.11 pp** |

Tam veri: [`dense_shift_test_per_seed.csv`](dense_shift_test_per_seed.csv),
[`dense_shift_test_summary.csv`](dense_shift_test_summary.csv).

Kullanıcının hatırladığı "~%11 FPR" sayısı doğrulandı — Dense'in
full_features varyantı window01_shift_test'te **%11.31±0.89** FPR veriyor.

**VAE, bu dağılım kaymasına Dense'den belirgin şekilde daha dayanıklı:**
mutlak FPR'de (%7.30 vs %11.31) hem de sapma büyüklüğünde (+3.11pp vs
+9.04pp — Dense'in kaçağı yaklaşık 3x daha büyük). Dense'in kendi
test-benign FPR'si zaten beklenen ~%5'in altında (%2.27) olduğu için Dense
için gap daha da çarpıcı görünüyor; ama mutlak sayı karşılaştırması
(shift FPR) da VAE lehine net.

## Adım 3 — Neden (kısmi) sapma var?

Feature-bazlı sapma analizi (`window01_shift_test`'in ortalamasının
`train_benign`'in ortalama/std'sine göre z-skoru,
[`feature_deviation_window01_vs_train.csv`](feature_deviation_window01_vs_train.csv)):

| feature | z-sapma (train std cinsinden) |
|---|---|
| duration_scaled | **+0.49** |
| orig_bytes_scaled | +0.42 |
| orig_pkts_scaled | +0.42 |
| resp_pkts_scaled | +0.38 |
| resp_bytes_scaled | +0.33 |
| byte_ratio_scaled | +0.31 |
| service_ssh | +0.28 |
| pkts_per_sec_scaled | +0.20 |

En büyük sapma `duration_scaled`'de (+0.49 std) — tam olarak 11 Temmuz
EDA'sının işaret ettiği şey (`window_01`'in duration CV'si diğer
pencerelerden yüksekti). `orig/resp_bytes` ve `orig/resp_pkts` da aynı
yönde sapıyor — bunlar [`09_collapse_investigation/`](../09_collapse_investigation/README.md)'da
zaten yüksek korelasyonlu olduğu gösterilen bir küme (orig_bytes↔orig_pkts
r=0.974, resp_bytes↔resp_pkts r=0.983) — yani tek bir alttaki gerçek
davranış farkı ("bu pencerede flow'lar biraz daha uzun/daha fazla
veri taşıyor"), birbiriyle korele 4-5 feature üzerinden VAE'ye
"çoklanmış" bir sinyal olarak giriyor. Sapmaların hiçbiri tek başına çok
büyük değil (en fazla ~0.5 std) — asıl etki, birkaç aşırı uç flow'un
(23.3, 5.94, 1.91, 1.87 hata değerleri) bu genel eğilimin **çok ötesine**
geçmesinden geliyor; muhtemelen o birkaç flow window_01'in gerçekten
sıradışı (belki uzun bir bağlantı, ya da nadir bir servis) örnekleri.

## Yorum ve sonuç

**VAE, görülmemiş-ama-gerçek bir benign dağılımına Dense'den daha iyi
genelliyor.** Sayılar:

- VAE window01_shift FPR: **%7.30** (Dense'in ~2/3'ü kadar)
- VAE'nin taban FPR'sinden sapması: **+3.11pp** (Dense'in ~1/3'ü kadar)
- Sapmanın kaynağı: birkaç aşırı uç flow + `duration`/`bytes`/`pkts`
  ailesinde hafif ama tutarlı bir kayma (window_01'in bilinen
  istatistiksel farklılığıyla uyumlu) — flow'ların büyük çoğunluğu
  (%92.7) hâlâ normal görünüyor.

Bu, VAE'nin (özellikle
[`09_collapse_investigation/`](../09_collapse_investigation/README.md)'da
gösterilen düşük içsel-boyutlu latent temsilinin) Dense'in daha yüksek
kapasiteli/daha az düzenlileştirilmiş rekonstrüksiyonuna kıyasla, eğitim
dağılımına daha az "ezberleyerek" bağlı kaldığını, doğal varyasyona karşı
biraz daha toleranslı bir sınır öğrendiğini düşündürüyor. %7.30 hâlâ
%5 taban değerinin üzerinde — yani bu tamamen "sorunsuz" değil, ama
%11.31'lik Dense sonucunun işaret ettiği "ciddi hassasiyet" seviyesinde
değil.

**Öneri:** Bu tek başına bir aksiyon gerektirmiyor (VAE zaten Dense'den
daha dayanıklı çıktı) — ama üretimde izlenmesi gereken bir metrik olarak
not edilmeli: `window_01` benzeri istatistiksel olarak sapan yeni
benign trafik geldiğinde, %7'ye yakın bir false-positive oranı
beklenmeli, bu oranın çoğu birkaç aşırı-uç flow'dan geliyor (toplu bir
"model kırılması" değil, münferit uç değerler).

## Dosyalar

- `evaluate_shift_test.py` — VAE final modelinin (inference-only) window01_shift_test değerlendirmesi
- `evaluate_dense_shift_test.py` — Dense'in 10 modelinin aynı set üzerindeki taze değerlendirmesi (path-düzeltilmiş kopya, `analysis/window01_shift_test_evaluation.py`'ye dokunulmadı)
- `shift_test_results.json`, `train_benign_errors.csv`, `test_benign_errors.csv`, `window01_shift_errors.csv` — VAE hata dağılımları
- `three_distribution_histograms.png` — üç dağılımın yan yana histogramı
- `feature_deviation_window01_vs_train.csv` — feature-bazlı sapma analizi
- `dense_shift_test_per_seed.csv`, `dense_shift_test_summary.csv` — Dense karşılaştırma verisi

Hiçbir final/root/önceki-klasöre dokunulmadı (`04_phase3_models/`,
`latest_run/`, `06_beta_selection_audit/` – `10_probabilistic_scoring/`,
`phase3_dense/`, `analysis/` değişmedi). Model yeniden eğitilmedi, sadece
kayıtlı final ağırlıklarla inference çalıştırıldı.
