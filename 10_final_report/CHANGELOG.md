# CHANGELOG — 10_final_report

## 2026-07-30 — 08_documentation/ yenilendi: eski dosyalar arşivlendi, iki yeni Türkçe PDF (v2 sonuçlarına göre)

Eski `DOCUMENTATION.md/html/pdf` ve `METRIKLER_ACIKLAMA.md/pdf` (28 Temmuz
tarihli, 18-feature v1 sonuçlarına dayanan) `V1_ARCHIVE/10_final_report/
08_documentation/` altına taşındı (silinmedi; eski `build_pdf.py` de
`build_pdf_v1.py` olarak aynı yere taşındı). Yerlerine, güncel (19-feature,
concurrency_src_1s dahil) sonuçlara göre sıfırdan yazılmış iki yeni Türkçe
PDF üretildi:

- **`Proje_Sonuclar_TR.pdf`** (8 sayfa) — genel okuyucu seviyesinde özet:
  proje tanımı, Faz 1-2-3 kısa özeti, bağımsız denetim (Fable review,
  K1/K2/O1-O7) bulgu tablosu, apache_bench sorununun tam öyküsü (bulgu →
  IAT denemesinin başarısızlığı ve ölçüm-artefaktı bulgusu → concurrency
  denemesinin başarısı → 3 aşamalı canonical entegrasyon), güncel v2
  sonuç tabloları (single/pairwise/segmented, her iki model) ve ilgili
  grafikler (ROC/PR, error_plot, before/after özet), O3 dedup-prevalence
  açık sınırlama notu.
- **`Metrikler_Aciklama_TR.pdf`** (5 sayfa) — her metriğin (recall,
  ROC-AUC, PR-AUC, F1, benign FPR, threshold_95, KS istatistiği,
  reconstruction error, pooled vs. decomposed recall) matematiksel tanımı,
  NIDS bağlamındaki anlamı ve projenin güncel sayılarıyla somut bağlantısı;
  ayrıca yeni `concurrency_src_1s` feature'ının tasarım mantığını (log1p,
  leakage-free scaler, IP-agnostik hesaplama, ±1s seçimi, genellenebilirlik
  uyarısı) ayrı bir bölümde açıklıyor.

**Türkçe karakter desteği:** Her iki PDF, reportlab ile üretildi ve
matplotlib'in bu makinede zaten kurulu olan DejaVuSans/-Bold/-Oblique/
-BoldOblique TTF fontları açıkça `pdfmetrics.registerFont` ile kaydedilerek
oluşturuldu (varsayılan Helvetica KULLANILMADI — Türkçe karakter glyph'leri
içermiyor). Üretimden önce her iki PDF'in tüm sayfaları `pdftoppm` ile
render edilip (ı, İ, ğ, Ğ, ş, Ş, ç, Ç, ö, Ö, ü, Ü dahil) görsel olarak
doğrulandı; render sırasında iki ROC/PR figüründe (Dense/VAE apache_bench)
üst-başlık ile alt-grafik başlıklarının çakıştığı fark edildi ve kaynak
üretim script'leri (`build_01_single_v2_{dense_only,vae_only}.py`)
düzeltilip figürler yeniden üretildi.

Ortak stil modülü: `10_final_report/08_documentation/pdf_style_tr.py`
(font kaydı, başlık/tablo/figür yardımcı fonksiyonları — iki build
script'i de bunu import ediyor, stil mantığı iki kez yazılmadı).

## 2026-07-30 — V1 arşivlendi, "_v2" adlandırması kaldırıldı (concurrency_src_1s artık TEK canonical sürüm)

3 aşamalı rollout'un ardından, 18-feature v1 sonuçları `V1_ARCHIVE/`'a
taşındı (silinmedi) ve 19-feature "v2" sonuçları `_v2` son eki olmadan tek
canonical isimlerini devraldı. Bundan sonra proje kökündeki
`01_single_attack_type/`, `phase3_dense/04_phase3_models/full_features/` vb.
isimler HER ZAMAN `concurrency_src_1s` dahil 19-feature modeli ifade eder;
18-feature v1 sadece `V1_ARCHIVE/` altında yaşıyor. Ayrıntılı gerekçe ve
içerik listesi: `V1_ARCHIVE/README.md`.

**Yol eşleme tablosu** (bu ve önceki CHANGELOG maddelerindeki yol
referanslarını güncel tutmak için — eski maddelerin metni geriye dönük
düzenlenmedi, bu tablo referans noktası):

| eski yol (v1) | şimdi | yeni yol (v2, canonical) |
|---|---|---|
| `10_final_report/01_single_attack_type/` | → | `V1_ARCHIVE/10_final_report/01_single_attack_type/` |
| `10_final_report/01_single_attack_type_v2/` | → | `10_final_report/01_single_attack_type/` |
| `10_final_report/02_pairwise_attack_type/` | → | `V1_ARCHIVE/10_final_report/02_pairwise_attack_type/` |
| `10_final_report/02_pairwise_attack_type_v2/` | → | `10_final_report/02_pairwise_attack_type/` |
| `10_final_report/03_segmented_injection/` | → | `V1_ARCHIVE/10_final_report/03_segmented_injection/` |
| `10_final_report/03_segmented_injection_v2/` | → | `10_final_report/03_segmented_injection/` |
| `10_final_report/04_apache_bench_diagnostics/` | → | `V1_ARCHIVE/10_final_report/04_apache_bench_diagnostics/` (tarihsel; IAT bölümündeki ölçüm artefaktı için bkz. `V1_ARCHIVE/README.md`) |
| `10_final_report/05_notebooks/_stochastic_legacy/` | → | `V1_ARCHIVE/10_final_report/05_notebooks_stochastic_legacy/` |
| `phase3_dense/04_phase3_models/full_features/` (18f, 5 seed) | → | `V1_ARCHIVE/phase3_dense/04_phase3_models/full_features/` |
| `phase3_dense/05_phase3_models_v2/full_features_v2/` | → | `phase3_dense/04_phase3_models/full_features/` (19f, 5 seed) |
| `phase3_vae/05_contamination_sweep/04_models/contam_0pct/` (18f, 20 seed) | → | `V1_ARCHIVE/phase3_vae/05_contamination_sweep/04_models/contam_0pct/` |
| `phase3_vae/05_contamination_sweep/04_models_v2/contam_0pct/` | → | `phase3_vae/05_contamination_sweep/04_models/contam_0pct/` (19f, 5 seed) |
| `02_phase2_feature_extraction/features_v2_with_concurrency/` | → | `02_phase2_feature_extraction/features_with_concurrency/` (sadece "_v2" kaldırıldı) |
| `13_temporal_feature_experiment/` (proje kökü) | → | `V1_ARCHIVE/13_temporal_feature_experiment/` (elenen IAT hipotezi) |

**Kapsam dışı bırakılan (bilinçli, koleksiyon çakışması riski nedeniyle):**
`phase3_vae/05_contamination_sweep/01_data_v2/`,
`02_contaminated_train_sets_v2/`, ve `dense_backend_v2.py`/`vae_backend_v2.py`/
`concurrency_v2.py`/`train_dense_v2.py`/`train_vae_v2.py` gibi iç
script/veri-hazırlık dosyaları `_v2` son ekini korudu — bunlar "sonuç"
değil, iç boru hattı bileşenleri; `01_data` gibi isimler hâlâ contam_0pct
DIŞINDAKİ kontaminasyon seviyeleri için canlı/kullanımda olduğundan isim
çakışması riski var. `09_dense_v2_comparison/`, `10_vae_v2_comparison/`,
`11_pairwise_segmented_v2/` klasörleri de aynı gerekçeyle (script/analiz
klasörleri, `06_attack_type_analysis/`, `08_dense_v1_comparison/` gibi
mevcut adlandırma konvansiyonuna uyuyorlar) isimlerini korudu.

**Taşıma sonrası doğrulama:** Dense ve VAE'nin single_attack_type
değerlendirmeleri yeni yollardan yeniden çalıştırıldı; sonuçlar taşımadan
ÖNCEKİ sayılarla birebir aynı çıktı (apache_bench recall Dense=0.9092,
VAE=0.9500 — değişmedi). `dense_backend_v2.py`, `vae_backend_v2.py`,
`concurrency_v2.py`, `train_dense_v2.py`, `train_vae_v2.py`,
`build_features_v2_dense.py` içindeki hard-coded yollar yeni konumlara göre
güncellendi.

## 2026-07-30 — concurrency_src_1s canonical pipeline'a entegre edildi (AŞAMA 3/3: pairwise + segmented, v1→v2 GEÇİŞ TAMAMLANDI)

AŞAMA 3, hem Dense v2 hem VAE v2 için pairwise ve segmented_injection
değerlendirmelerini tamamlıyor — 3 aşamalık `concurrency_src_1s` rollout'unun
sonu.

**Yapılanlar:**

- `11_pairwise_segmented_v2/evaluate_pairwise_attack_type_v2.py`: 3 ikili
  kombinasyon (portscan+apache_bench, portscan+slowloris,
  apache_bench+slowloris), her iki model için, decomposed (pooled olmayan)
  apache_bench-only recall dahil. **v1'deki gibi doğrulandı: apache_bench'in
  kendi recall'u pairing'e göre değişmiyor** — hem Dense v2 hem VAE v2'de
  solo ve her iki pair'de birebir aynı (Dense v2: 0.9092 her yerde; VAE v2:
  0.9500 her yerde) — per-flow eşik kararı hangi flow'ların aynı test
  setinde olduğuna bağlı değil, v1'in bulduğu gibi.
- `11_pairwise_segmented_v2/evaluate_segmented_injection_v2.py`: aynı
  `segmented_sequence.csv` (benign→apache_bench→benign→slowloris→benign→
  portscan→benign, v1 ile birebir aynı sıra/flow'lar), `error_plot.png`
  dahil.
- Çıktılar `10_final_report/{02_pairwise_attack_type_v2,
  03_segmented_injection_v2}/{dense_v2,vae}/` altına kopyalandı. Eski
  `02_pairwise_attack_type/` ve `03_segmented_injection/` (v1) DEĞİŞMEDİ.

**Sonuç — v1 vs v2, apache_bench+portscan pairwise (en çok etkilenen çift):**

| model | recall (pooled) | ROC-AUC |
|---|---|---|
| VAE v1 | 0.3355 ± 0.0025 | 0.7725 ± 0.0606 |
| Dense v1 | 0.3339 ± 0.0049 | 0.7921 ± 0.0539 |
| **Dense v2** | **0.9381 ± 0.0261** | **0.9868 ± 0.0052** |
| **VAE v2** | **0.9659 ± 0.0309** | **0.9887 ± 0.0084** |

**Sonuç — segmented injection, apache_bench bloğu (contiguous, karışık değil):**

| model | block recall | benign FPR aralığı (4 boşluk) |
|---|---|---|
| VAE v1 | 0.0262 | 0.0321–0.0933 |
| Dense v1 | 0.0262 | 0.0183–0.1336 |
| **Dense v2** | **0.9092** | 0.0142–0.1478 |
| **VAE v2** | **0.9500** | 0.0386–0.0967 |

Shuffled test setiyle (single_attack_type) birebir tutarlı: apache_bench tek
başına gelse de (contiguous blok) sonuç değişmiyor — istatik per-flow eşik
kararının beklenen davranışı, hem v1'de hem v2'de doğrulandı.

---

## v1 → v2 GEÇİŞ TAMAMLANDI — özet

**Ne eklendi:** `concurrency_src_1s` — bir flow'un kendi zaman damgası
etrafında (±1s), aynı kaynak IP'den kaç flow daha geldiği (log1p +
benign-train-fit StandardScaler, hiçbir yerde sabit IP değeri kullanılmadan).
`14_concurrency_feature_experiment/`'de Config A olarak doğrulandı, sonra
kademeli olarak canonical pipeline'a taşındı:
- AŞAMA 1: Dense pipeline feature extraction + Dense v2 retrain (5 seed) +
  single_attack_type.
- AŞAMA 2: VAE pipeline'ının window_10 kısmı tamamlandı (Dense v2'nin AYNI
  scaler'ıyla, refit edilmeden — assert'le doğrulandı) + VAE v2 retrain
  (5 seed, latent=10/beta=0.25, deterministik z_mean) + single_attack_type.
- AŞAMA 3 (bu madde): pairwise + segmented_injection, her iki model.

**Hangi modeller/sonuçlar etkilendi:** Dense v1 ve VAE v1 (18 feature)
DEĞİŞMEDİ — hiçbir eski model, split, veri dosyası veya rapor klasörü
üzerine yazılmadı. Yeni: Dense v2 (`phase3_dense/05_phase3_models_v2/`) ve
VAE v2 (`phase3_vae/05_contamination_sweep/04_models_v2/contam_0pct/`),
19 feature, 5 seed her ikisi de. Üç yeni rapor klasörü:
`10_final_report/{01_single_attack_type_v2, 02_pairwise_attack_type_v2,
03_segmented_injection_v2}/`, her biri `dense_v2/` ve `vae/` alt klasörleriyle.

**apache_bench'teki genel etki (tüm değerlendirmelerde tutarlı):** recall
@thr95 ~%2.6 → ~%91–95 (Dense v2 / VAE v2), ROC-AUC ~0.70/0.67 → ~0.98,
benign FPR maliyeti küçük (+0.004 ila +0.005 puan ortalama). portscan ve
slowloris zaten güçlü olan performanslarını korudu. Sonuç hem shuffled test
setinde (single/pairwise) hem contiguous blok halinde (segmented) tutarlı,
ve iki bağımsız mimari/eğitim-verisi kombinasyonunda (Dense: windows 01-08,
VAE: window_10) aynı büyüklükte tekrarlandı — mimariye özgü bir artefakt
değil.

**Eski v1 dosyaları:** hiçbiri silinmedi, hepsi arşivde duruyor:
`phase3_dense/04_phase3_models/full_features/`,
`phase3_vae/05_contamination_sweep/04_models/contam_0pct/` (20 seed),
`10_final_report/{01_single_attack_type, 02_pairwise_attack_type,
03_segmented_injection}/` (v1). Eski/yeni karşılaştırması her zaman mümkün.

**Bilinen kapsam sınırlaması:** v2 raporları, v1'in `zmean_rescore/`
aşamasında eklenen dedup-prevalence düzeltmesini (PR-AUC/F1 için resampled
kopyaların prevalansı çarpıtmasını önleyen hybrid panel) içermiyor — v2
figürleri Aşama 1'in kurduğu temel düzeyde (`build_01_single.py` tarzı,
dedup düzeltmesiz). ROC-AUC/recall/FPR (davranış metrikleri) bundan
etkilenmiyor; PR-AUC/F1 sayıları v1'in dedup-düzeltilmiş halleriyle birebir
karşılaştırılırken bu farkı akılda tutmak gerekir.

## 2026-07-30 — concurrency_src_1s canonical pipeline'a entegre ediliyor (AŞAMA 2/3: VAE v2, single_attack_type)

AŞAMA 1'in devamı. window_10 (VAE-only, Dense pipeline'ının hiç parçası
olmayan ayrı bir capture) için `concurrency_src_1s`'i tamamladık ve VAE'yi
19-feature'lı canonical modele retrain ettik.

**Doğrulama (retrain'den önce durulması istenen adım):** window_10'un
`concurrency_src_1s_scaled` değerleri, Dense v2'nin scaler'ıyla (train
split'ine fit, mean_log=2.0864962884954803, std_log=0.6023503882972578)
ölçeklendi — REFIT EDİLMEDİ, `phase3_vae/05_contamination_sweep/
concurrency_v2.py` modül-seviyesi assert'iyle bu iki değere karşı doğrulandı;
**eşleşti**, script durmadı. VAE'nin kendi benign train/val/test split'i
(window_10, 70/15/15) ve attack pool/test set'i (window_02-08, SEED=42),
v2'de **v1 ile birebir aynı flow_id kümelerini** üretti (5/5 hash kontrolü
geçti) — sadece feature değerleri değişti, split değişmedi.

**VAE v2 retrain:** `phase3_vae/05_contamination_sweep/04_models_v2/
contam_0pct/` (5 seed, latent_dim=10, beta=0.25, dropout=0.1, batch=64,
epochs≤200, patience=12 — `train_contamination_sweep.py` ile birebir aynı
mimari/hiperparametre, sadece 19. feature ve 20→5 seed). Skorlama
**deterministik z_mean** (O2 düzeltmesi — stokastik tek-örnek yöntem
kullanılmadı; `threshold.json`'daki stokastik threshold'lar sadece dosya
formatı uyumluluğu için tutuldu, değerlendirmede kullanılmadı).
Eski `04_models/contam_0pct/` (20 seed, stokastik+deterministik ikisi de
mevcut) DEĞİŞMEDİ.

**single_attack_type değerlendirmesi (VAE v2 only):**
`10_vae_v2_comparison/results_single_attack_type_vae_v2.csv/.md`, rapor
figürleri `10_final_report/01_single_attack_type_v2/vae/`. Eski
`10_final_report/01_single_attack_type/` (v1) DEĞİŞMEDİ.

**Sonuç — üç modelin yan yana karşılaştırması (single_attack_type, apache_bench):**

| model | recall @thr95 | ROC-AUC | benign FPR @thr95 |
|---|---|---|---|
| VAE v1 (18f, 20 seed, deterministik z_mean) | 0.0262 | 0.6670 ± 0.0890 | 0.0577 ± 0.0058 |
| Dense v1 (18f, 5 seed) | 0.0262 | 0.6957 ± 0.0791 | 0.0615 ± 0.0023 |
| **Dense v2 (19f, 5 seed)** | **0.9092 ± 0.0382** | **0.9808 ± 0.0076** | 0.0660 ± 0.0036 |
| **VAE v2 (19f, 5 seed, deterministik z_mean)** | **0.9500 ± 0.0453** | **0.9836 ± 0.0123** | 0.0664 ± 0.0110 |

VAE v2, Dense v2'yi hafifçe geçiyor (recall 0.950 vs 0.909, ROC-AUC 0.984 vs
0.981) — iki farklı mimari, iki farklı eğitim veri kaynağı (window_10 vs.
windows 01-08) aynı yeni feature'la benzer büyüklükte kazanç gösteriyor,
bu da `concurrency_src_1s`'in mimariye özgü bir artefakt değil, gerçek bir
sinyal olduğunu destekliyor. portscan/slowloris her iki modelde de
etkilenmedi (recall 1.0000). Benign FPR maliyeti her iki modelde de küçük
(+0.004 ila +0.005 puan) ve exp14/AŞAMA 1'deki aralıkla tutarlı; VAE v2'nin
FPR std'si (0.011) Dense v2'ninkinden (0.004) daha geniş — 5 seed'lik VAE
örnekleminde biraz daha fazla seed-varyansı var, niteliksel sonucu değiştirmiyor.

**Bekleyen aşama:** AŞAMA 3 — pairwise + segmented_injection v2
değerlendirmeleri (hem Dense hem VAE), `10_final_report/
{02_pairwise_attack_type_v2, 03_segmented_injection_v2}/`. Kullanıcı onayı
bekleniyor.

## 2026-07-30 — concurrency_src_1s canonical pipeline'a entegre ediliyor (AŞAMA 1/3: Dense v2, single_attack_type)

`14_concurrency_feature_experiment/`'de doğrulanan Config A
(`concurrency_src_1s`: aynı kaynak IP'den ±1s içindeki flow sayısı, log1p +
benign-train-fit StandardScaler, hiçbir yerde sabit IP değeri kullanılmadan)
artık deneysel değil — canonical pipeline'a **kademeli olarak** entegre
ediliyor. Bu madde yalnızca AŞAMA 1'i kapsıyor; VAE v2 ve pairwise/segmented
v2 değerlendirmeleri sonraki aşamalarda ayrı madde olarak eklenecek.

**AŞAMA 1'de yapılanlar (Dense pipeline, single_attack_type):**

- **Yeni feature dataset:** `02_phase2_feature_extraction/
  features_v2_with_concurrency/features_v2_all_rows.csv` — orijinal 18
  feature birebir kopyalandı (değiştirilmedi), `concurrency_src_1s_scaled`
  eklendi. Hizalama (`ts`+`is_attack`+`window_id`), 14 numaralı deneydeki
  gibi TAM veri setinde (46.495 satır) assert'lendi, seyrek alt küme
  kullanılmadı. Scaler parametreleri (mean_log=2.0865, std_log=0.6024)
  14 numaralı deneyle birebir eşleşti (aynı formül, aynı train split).
  Eski `features_all_windows.csv` DEĞİŞMEDİ.
- **Dense v2 retrain:** `phase3_dense/05_phase3_models_v2/full_features_v2/`
  (5 seed, mimari/split/hiperparametreler v1 ile birebir aynı, tek fark 19.
  feature). Eski `phase3_dense/04_phase3_models/full_features/` DEĞİŞMEDİ.
- **single_attack_type değerlendirmesi (Dense v2 only):**
  `09_dense_v2_comparison/results_single_attack_type_dense_v2.csv/.md`,
  rapor figürleri `10_final_report/01_single_attack_type_v2/dense_v2/`.
  Eski `10_final_report/01_single_attack_type/` (v1, VAE+Dense) DEĞİŞMEDİ —
  eski/yeni karşılaştırması hâlâ mümkün.

**Sonuç (5 seed, 14 numaralı deneyin 3-seed Config A'sıyla tutarlı):**
apache_bench recall @thr95 0.0262 → **0.9092 ± 0.0382** (v1: 0.0262, exp14
Config A 3-seed: 0.9135 ± 0.0292), ROC-AUC 0.6957 → **0.9808 ± 0.0076**,
benign FPR 0.0615 → 0.0660 ± 0.0036 (+0.0045 puan, exp14'teki tahminle
uyumlu bir maliyet aralığında). portscan/slowloris etkilenmedi (recall
1.0000).

**Bekleyen aşamalar:** AŞAMA 2 — VAE v2 retrain (window_10 pipeline'ına
concurrency_src_1s entegrasyonu, latent=10/beta=0.25, deterministik z_mean
skorlama) kullanıcı onayı bekliyor. AŞAMA 3 — pairwise + segmented_injection
v2 değerlendirmeleri (hem Dense hem VAE), `10_final_report/
{02_pairwise_attack_type_v2, 03_segmented_injection_v2}/`.

## 2026-07-29 — O7: IP-bazlı ground truth tehdit modeli notu rapor ve dokümantasyona eklendi

Denetim bulgusu O7 kod üzerinden doğrulandı: `is_attack` proje genelinde
yalnızca kaynak IP ile tanımlı (`faz2_feature_extraction.py:134-136` —
lab-only filtre sonrası `id.orig_h == 192.168.10.2`; `prepare_window10.py`
aynı kural). Davranışsal sinyal etikete girmiyor; `attack_log.csv` yalnızca
saldırı tipini post-hoc atıyor (attack flow'ların %100'ü 1 sn toleransla bir
komut aralığına düşüyor — etiket bu lab'da pratikte temiz). IP model girdisi
değil (18 feature'da IP yok) — sınırlama etiket tanımında. Hiçbir final
doküman bu tanımı belirtmiyordu; tehdit modeli notu iki dokümana eklendi
(yalnızca yeni bölüm): `07_final_written_report/
rapport_final_attack_type_analysis.md` bölüm 7'ye O4 notunun ardına "Note
sur le modèle de menace — une vérité terrain définie par l'IP source" ve
`08_documentation/DOCUMENTATION.md`'ye "### 7.5 Tehdit modeli notu". Mesaj
üç parçalı: etiket = kaynak kimliği (davranış değil); model "saldırgan
makinenin istatistiksel imzasını" öğreniyor — spoofing/NAT/karışık
trafik/yanal hareket senaryolarına genelleme test edilmedi; diğer bulgular
bu ground truth tanımı altında geçerli, "gerçek dünya deployment" okumaları
bu notla sınırlanmalı. Her iki PDF yeniden üretildi. Kapsam doğrulaması +
taslaklar: `06_scripts/o7_ip_based_ground_truth/findings_o7_report_notes.md`.

## 2026-07-29 — O5: train-data confound doğrulandı, karşılaştırma notları rapor ve dokümantasyona eklendi

Denetim bulgusu O5 (VAE-vs-Dense karşılaştırmasında mimari farkı ile eğitim
verisi farkının karışması) split dosyaları ve script'lerden retrain'siz
doğrulandı: VAE yalnızca window_10 benign'iyle (train n=3.049, 20 seed,
rastgele 70/15/15), Dense v1 window_01-08 ile (train n=23.274 — ~7,6 kat,
5 seed, GroupShuffleSplit) eğitilmiş; window_10'daki icmp/OTH/S0 kategorik
değerleri Dense'in encoder'ında all-zero kodlanıyor. Scaler confound değil
(yalnızca Dense train'inde fit edilip iki tarafa uygulanıyor — ortak ölçek);
audit'in "ölçekleyiciyle confound'lu" ifadesi bu yönüyle nüanslandı.
Değerlendirme tarafı (aynı test flow'ları, 18 kolon, threshold konvansiyonu)
özdeş. Bu temelde iki dokümana okuma notu eklendi (yalnızca yeni bölüm):
`07_final_written_report/rapport_final_attack_type_analysis.md` §5 sonuna
"Note de lecture — les deux modèles n'ont pas été entraînés sur les mêmes
données" ve `08_documentation/DOCUMENTATION.md`'ye "### 7.4 Sınırlama notu —
VAE ve Dense v1 aynı eğitim verisiyle eğitilmedi". Mesaj üç parçalı: ince
taneli karşılaştırmalar (macro parite 0.674/0.551 vs 0.673/0.540, ROC-AUC
0.696 vs 0.581 nüansı) mimariye atfedilemez; "aynı şekilde tekrarlandı"
ifadeleri yalnızca eval protokolünü anlatır; ana bulgu (apache_bench →
feature-set sınırlaması) zayıflamaz, güçlenir. Her iki PDF yeniden üretildi.
Bulgular + taslaklar: `06_scripts/o5_train_data_confound/findings_o5_report_notes.md`.

## 2026-07-29 — O4: threshold transfer analizi + sınırlama notları rapor ve dokümantasyona eklendi

Denetim bulgusu O4 (threshold_95'in küçük val-benign setinden kalibrasyonu +
val→test dağılım-transferi varsayımı) retrain'siz sayısal analizle doğrulandı:
`06_scripts/o4_threshold_transfer/analyze_threshold_transfer.py` (20 kanonik
seed, deterministik z_mean). Sonuçlar: kalibrasyon seti n=653; threshold_95
seed-arası CV %27.9 (aralık 0.043–0.153), tek-seed bootstrap %95 CI ortalama
genişliği threshold'un ~%60'ı (oynaklığın önemli kısmı küçük-n persentil
gürültüsü); val threshold'unun test-benign'de gerçekleşen FPR'ı %5.77 ± 0.58
(nominal %5.00, 18/20 seed'de üstünde — sistematik yönlü sapma), KS ortalama
0.067 (5/20 seed p<0.01). AUC/PR-AUC threshold'dan bağımsız olduğundan
etkilenmiyor. Bu temelde iki dokümana sınırlama notu eklendi (yalnızca yeni
bölüm, mevcut bölümlere dokunulmadı):
`07_final_written_report/rapport_final_attack_type_analysis.md` bölüm 7'ye
O1 notunun ardına "Note de prudence — calibration du seuil sur un petit
ensemble de validation" alt-bölümü ve `08_documentation/DOCUMENTATION.md`'ye
"### 7.3 Sınırlama notu — threshold_95'in küçük val setinden kalibrasyonu";
her iki PDF yeniden üretildi. Bulgular + taslaklar:
`06_scripts/o4_threshold_transfer/findings_o4_report_notes.md`, per-seed
tablo: `threshold_transfer_per_seed.csv`.

## 2026-07-29 — 07_final_written_report: PDF build scripti kalıcı hale getirildi

O1 notu eklenirken geçici olarak yazılan rapor PDF build scripti,
`08_documentation/build_pdf.py` konvansiyonuyla `07_final_written_report/build_pdf.py`
olarak repoya alındı (md → gömülü-görselli HTML → headless Chrome PDF; rapor
artık tekrarlanabilir şekilde yeniden üretilebilir).

## 2026-07-29 — O1: mimari notu + latent ablation koşusu rapor ve dokümantasyona eklendi

Denetim bulgusu O1 (latent_dim=10 > bottleneck=8 — nominal kapasite fiilen
mevcut değil) için doğrulama ablation'ı koşuldu:
`phase3_vae/05_contamination_sweep/12_latent_ablation/` altında latent_dim=8
(bottleneck ile eşit) varyantı, aynı 20 seed / hiperparametre / split ve
deterministik z_mean skorlamayla eğitilip kanonik latent=10 ile seed-eşleşmeli
bootstrap karşılaştırmasına sokuldu. Sonuç: iki varyant pratikte ayırt
edilemez — tip başına recall birebir aynı (apache_bench 0.0262, portscan
0.9983, slowloris 1.0000), apache_bench ROC-AUC farkı (+0.035) %95 CI'ında
sıfırı içeriyor; aktif latent boyut her iki varyantta da nominal genişliğin
altında (ort. 4.4/8 vs 5.9/10). Orijinal latent=10 modelleri/sonuçlarına
dokunulmadı. Bu temelde O1 için mimari sınırlama notu iki ana dokümana
eklendi (yalnızca yeni bölüm eklendi, mevcut bölümlere dokunulmadı):
`07_final_written_report/rapport_final_attack_type_analysis.md` bölüm 7'ye
"Note d'architecture — dimension latente nominale vs. effective" alt-bölümü
ve `08_documentation/DOCUMENTATION.md` §0.2'ye "Mimari not — nominal vs.
etkin latent boyutu" paragrafı; her iki PDF yeniden üretildi. Taslak +
bulgular: `12_latent_ablation/findings_o1_report_notes.md`,
karşılaştırma tabloları: `comparison_latent8_vs_latent10.{csv,md}`.

## 2026-07-29 — 05_notebooks: dört notebook deterministik z_mean skorlamaya geçirildi (O2)

`05_notebooks/` altındaki dört notebook hâlâ eski stokastik skorlama
dönemindeydi; ana pipeline'a uygulanan O2 düzeltmesiyle hizalandı ve tüm
hücreler baştan sona yeniden çalıştırıldı (grafik/tablo çıktıları güncel).
Orijinal versiyonlar `05_notebooks/_stochastic_legacy/` altında.

- **Ortak:** demo VAE backend'leri `single.VAEBackend(..., deterministic=True)`
  oldu — z = z_mean, eps örneği ve eval seed yok; threshold_95 seed başına
  val-benign deterministik error'un 95. persentilinden yeniden kalibre
  (`run_zmean_rescore.py` ile aynı mekanizma, kod `evaluate_by_attack_type.py`
  içinde zaten mevcuttu). "Published" hücreleri artık stokastik
  `06_attack_type_analysis/` / `07_segmented_injection/` orijinallerini değil,
  `10_final_report`'un kanonik deterministik tablolarını okuyor.
- **01_attack_type_analysis:** demo backend deterministik; published tablolar →
  `01_single_attack_type/vae/results.csv`, `02_pairwise_attack_type/vae/
  results.csv` + `results_combined.md` (hibrit dedup metrik notu eklendi).
- **02_segmented_injection:** `eval_seed_offset=950_000` kalktı (sampling'le
  birlikte anlamını yitirdi); published çıktılar → `03_segmented_injection/
  vae/block_recall_f1_per_seed.csv` + `error_plot.png`.
- **03_dense_v1_comparison:** Dense tarafı zaten deterministikti, dokunulmadı;
  VAE karşılaştırma sayıları kanonik deterministik `results.csv`'den okunuyor,
  VAE-vs-Dense grafikleri/makro tablo bu sayılarla yeniden üretildi.
- **04_apache_bench_diagnostics:** ölü `10_final_deliverables_31_temmuz/
  06_diagnostics` yolu düzeltildi (scriptler `06_scripts/
  apache_bench_diagnostics/`, veri `04_apache_bench_diagnostics/`) — notebook
  bu yüzden hiç çalışmıyordu; demo backend deterministik; markdown
  `findings.md`'nin güncel median_error anlatımıyla hizalandı.

## 2026-07-28 — 04_apache_bench_diagnostics: skor-bağımlı çıktılar deterministik z_mean ile yeniden üretildi

`vae_reconstruction_error_hist.png` ve `vae_reconstruction_error_summary.csv`
hâlâ eski stokastik skordan kalmıştı; deterministik z_mean skoruyla (per-seed
val-benign deterministik threshold_95, diğer sonuçlarla aynı konvansiyon)
yeniden üretildi — eski versiyonlar `04_apache_bench_diagnostics/
_stochastic_legacy/` altında. Özet CSV'ye `median_error` kolonu eklendi çünkü
asıl hikâyeyi medyanlar anlatıyor: **tipik apache_bench flow'unun
deterministik error'u 0.0171 — tipik benign'in (0.0131) yalnızca ~1.3 katı ve
0.0903'lük threshold'un ~5 kat altında**; apache_bench histogramda benign
dağılımının sağ omzunun *içinde* dar bir sivri uç olarak oturuyor
(portscan+slowloris ~6 mertebe uzakta, %100 flagged). apache_bench'in
ortalama-medyan farkı (5.74 vs 0.017), 20 seed'in hepsinde aynı olan 39
flagged flow'dan geliyor. Skor gürültüsü kalktığı için "bu ayrım threshold
artefaktı olabilir" kaydı da düştü. `findings.md` bölüm 3 bu sayılarla
güncellendi. Skor-bağımsız analizler (feature KS/mean-shift CSV'leri, IAT
testi) doğrulanıp olduğu gibi bırakıldı. Script:
`06_scripts/zmean_rescore/regenerate_apache_diagnostics_zmean.py`.

## 2026-07-28 — O6: benign-gap FPR yorumu düzeltildi (kompozisyon etkisi, gürültü değil)

Denetim bulgusu O6: segmented-injection raporlarındaki benign gap FPR
farkları (VAE: 0.032/0.036/0.093/0.069) "küçük segment boyutundan gelen
örnekleme gürültüsü" diye yorumlanıyordu. Bu yanlıştı: n≈1705'te FPR≈0.05'in
binom std'si ~0.005'tir ve deterministik z_mean skoru tüm skorlama
gürültüsünü kaldırdığı hâlde desen birebir korunmuştu.

**Gerçek mekanizma:** `build_segmented_injection.py` benign havuzunu ts
sırasına göre bitişik parçalara böler; window'lar zamanda ardışık olduğundan
her gap farklı window'ların benign'ini içerir ve window başına benign FPR
keskin farklıdır (window_06: 0.100, window_07: 0.115; diğerleri 0.029–0.053,
deterministik, 20 seed). Gap 4 (FPR 0.093) %45 window_06 + %26 window_07'den
oluşuyor; gap 0 (FPR 0.032) ikisini de içermiyor. Her gap'in FPR'si,
kompozisyon-ağırlıklı window FPR ortalamasıyla ≤0.008 artıkla yeniden
kurulabiliyor.

**Yapılanlar:** kanıt tabloları eklendi
(`03_segmented_injection/vae/segment_window_composition.{csv,md}`: segment×
window kompozisyonu, window başına FPR, gap FPR'sinin kompozisyondan yeniden
kurulumu; script: `06_scripts/zmean_rescore/build_segment_window_composition.py`).
Yanlış yorum cümlesi üç yerde düzeltildi: `03_segmented_injection/vae/
block_recall_f1.md`, `03_segmented_injection/dense_v1/block_recall_f1.md`
(aynı yanlış cümle; kompozisyon mekanizması model-bağımsız) ve üretici
script `07_segmented_injection/evaluate_segmented_injection.py` (gelecek
koşumlar aynı hatayı yeniden üretmesin diye). README'nin 03 bölümüne ek
bulgu paragrafı eklendi. Sayılar değişmedi — bu bir yorum/metin düzeltmesi.

## 2026-07-28 — PR-AUC/F1 için dedup prevalans düzeltmesi (hibrit kanonik tablolar)

Dedup sağlamlık kontrolünün (aşağıdaki madde) sonucuna dayanan raporlama
kararı: kanonik VAE tablolarında **hangi metrik hangi setten geliyor** artık
metrik sınıfına göre ayrılıyor:

- **recall / ROC-AUC / benign-FPR → kanonik (dedup'suz) set.** Bunlar yalnızca
  per-flow skor ve karara bağlı davranış metrikleri; dedup'la fark <0.02
  olduğu doğrulandı, değiştirilmediler.
- **PR-AUC / F1 → dedup edilmiş set** (resampled kopyalar atılmış,
  distinct-flow sayıları: apache_bench 968, portscan 539, slowloris 640,
  benign 5428; ikili setler için 1507/1179/1608). Bu iki metrik tanım gereği
  benign:attack prevalans'ına bağlı ve kopyalar bu oranı çarpıtıyordu
  (benign satırların %20'si, attack satırların %31'i kopyaydı).

Uygulanan dosyalar: `01_single_attack_type/vae/results.{csv,md}`,
`02_pairwise_attack_type/vae/results.{csv,md}` + `results_combined.md`
(ikili PR-AUC/F1 dedup değerleri bu adımda hesaplandı; CSV'lere
`n_benign_dedup`/`n_attack_dedup` kolonları eklendi, md'lere hangi metriğin
hangi setten geldiğini söyleyen dipnot kondu).
`03_segmented_injection/vae/block_recall_f1.md`'ye düzeltmenin **neden
uygulanmadığı** notu eklendi: o raporda PR-AUC yok ve blok F1'i %100-attack
segmentlerde precision=1 ile F1=2r/(1+r), yani recall'un birebir fonksiyonu —
prevalans-duyarlı değil.

Script: `06_scripts/zmean_rescore/apply_dedup_prevalence_correction.py`.

**Figür tutarlılığı (aynı gün, ek düzeltme):** `roc_pr_*.png` figürleri
hibrit panellerle yeniden üretildi — **ROC paneli kanonik sette** (davranış
metriği, değişmedi), **PR paneli (eğri + AP değeri) dedup sette**, tabloyla
aynı temelde. Her figürün üst yazısına hangi panelin hangi setten geldiği
eklendi ("ROC: kanonik set (n=...), PR: dedup set (n=...)"); PR panelinin
baseline çizgisi de dedup prevalansını gösterir. Script:
`regenerate_plots_deterministic.py` (hibrit panel desteğiyle güncellendi).
Kalan bilinen ve tasarım gereği olan fark: figürdeki AUC/AP, 20 seed'in
**ortalama error'undan** hesaplanan tek havuzlanmış eğridir (apache_bench
AP=0.215); tablodaki değer ise **seed başına AP'lerin ortalamasıdır**
(0.2244 ± 0.0349) — aynı ilişki ROC için de eskiden beri geçerli
(figür 0.660, tablo 0.667). İki sayı artık aynı (dedup) setten geliyor;
kalan fark yalnızca havuzlama-vs-ortalama konvansiyonu.

## 2026-07-28 — O3 dedup sağlamlık kontrolü (kanonik sonuçlara dokunulmadı)

Denetim bulgusu O3 (resampled kopyaların test setinde çift sayım yaratması)
için sağlamlık kontrolü: `01_single_attack_type/vae/dedup_sanity_check/`.
Test setinden 2356 resampled kopya (attack satırlarının %31'i) atılıp tekli
attack-type değerlendirmesi aynı deterministik modellerle tekrarlandı.
**Sonuç:** davranış metrikleri (recall/ROC-AUC/FPR) pratik olarak aynı
(maks |Δ| = 0.0069 < 0.02) — kopyalar sonucu değiştirmiyordu, sadece n'i
şişiriyordu. PR-AUC/F1'deki daha büyük kaymalar (maks 0.0321) dedup'un
benign:attack oranını değiştirmesinin tanımsal/mekanik etkisi. Ayrıntı:
`dedup_sanity_check/results_dedup.md`. Kanonik `results.csv/.md` değişmedi.

## 2026-07-28 — VAE skorlaması stokastikten deterministik z_mean'e geçirildi

**Ne değişti:** Tüm VAE sonuçları (tekli attack-type, ikili kombinasyonlar,
bloklu/segmented injection — tablolar **ve** grafikler) deterministik z_mean
skoruyla yeniden üretildi ve kanonik dosya adlarını devraldı. Eski tek-örnekli
stokastik skorun çıktıları silinmedi; her `vae/` klasörünün
`_stochastic_legacy/` alt klasörüne taşındı. Dense v1 sonuçlarına dokunulmadı
(Dense'in skoru zaten deterministikti). Model ağırlıkları aynı — **retrain
yapılmadı**, yalnızca inference-zamanı skor fonksiyonu değişti.

**Neden:** Bağımsız denetim (`11_fable_review/independent_audit.md`, bulgu
**O2**) eski skorun her flow için reparametrizasyon trick'inden **tek** rastgele
z örneği çektiğini tespit etti (`tf.random.normal`, keyfî 900_000/950_000
eval-seed offset'leri). Sonuç: raporlanan her sayıda tek-örnek Monte Carlo
gürültüsü + keyfî seed'e bağımlılık. Yeni skor `z = z_mean` kullanır (eps yok,
eval seed'i yok); bir flow'un bir model altındaki skoru tek ve sabit bir sayı.
Zorunlu yan adım: `threshold.json`'daki threshold'lar stokastik val error'larından
kalibre edilmişti ve deterministik skora taşınamaz — threshold_95, **aynı kural**
(val-benign error %95 percentile) ve aynı val setiyle deterministik skor
üzerinden seed başına yeniden kalibre edildi.

**En önemli farklar** (tam tablo: `deterministic_vs_stochastic_comparison.md`):

- **apache_bench recall std = 0.0000:** 20 seed'in **her biri** 1487
  apache_bench flow'unun **tam olarak aynı 39 tanesini** işaretliyor
  (recall = 0.0262; seed 0/7/16'da küme kesişimi 39/39 olarak doğrulandı).
  apache_bench zafiyeti eğitim rastgeleliğine bağlı değil — yapısal bir
  feature-uzayı sınırı. Eski recall'un (0.0328 ± 0.0055) fazlası ve std'si
  tamamen skorlama gürültüsüymüş.
- **apache_bench ROC-AUC 0.5815 → 0.6670:** eps gürültüsü sıralamayı bozup
  AUC'yi 0.5'e doğru çekiyormuş; gürültüsüz skor modelin gerçek (ama hâlâ
  zayıf) ayrım gücünü gösteriyor.
- **portscan recall 0.9889 → 0.9983;** slowloris değişmedi (1.0000); benign
  FPR ~%5.77'de sabit (threshold rekalibrasyonu doğrulaması). Hiçbir
  niteliksel bulgu tersine dönmedi.
- Benign segment FPR deseni (%3.2/%3.6/%9.3/%6.9) gürültü kalktığı hâlde
  aynen durdu — farkın sistematik (window kompozisyonu) olduğu yönündeki
  denetim bulgusu (O6) güçlendi.

**Nasıl yeniden üretilir:**
`06_scripts/zmean_rescore/run_zmean_rescore.py` (tablolar + segmented çıktıları)
ve `06_scripts/zmean_rescore/regenerate_plots_deterministic.py` (ROC/PR +
pairwise grafikleri). Skor implementasyonu:
`06_attack_type_analysis/evaluate_by_attack_type.py` →
`reconstruction_error_zmean()` + `VAEBackend(deterministic=True)`.

**Bilinen kalan işler:**
- ~~`04_apache_bench_diagnostics/` içindeki reconstruction-error histogramı ve
  özet CSV hâlâ eski stokastik skorla üretilmiş durumda~~ — aynı gün
  deterministik skorla yeniden üretildi (yukarıdaki 04-diagnostics maddesi).
- `05_notebooks/` executed notebook'ları stokastik dönemin çıktılarnı gösteriyor.
- `07_final_written_report/` (Fransızca rapor) henüz güncellenmedi — ayrıca ele
  alınacak.
