# V1_ARCHIVE — 18-feature baseline (pre-`concurrency_src_1s`)

**Arşivlenme tarihi:** 2026-07-30

## Bu klasör ne

Bu klasör, `concurrency_src_1s` feature'ı canonical pipeline'a entegre
edilmeden (2026-07-30, "v1→v2 rollout") ÖNCEKİ tüm sonuçları içerir: 18
modeling feature'lı VAE ve Dense v1 modelleri, ve bu modellerle üretilmiş
final-rapor çıktıları (single/pairwise/segmented attack-type
değerlendirmeleri). Ayrıca, ayrı bir yan-deney olarak test edilip **elenen**
bir hipotezin (inter-arrival-time / IAT feature'ı) tam kaydı da burada.

Hiçbir dosya silinmedi — hepsi buraya taşındı (git mv / mv), böylece eski ve
yeni sonuçlar arasındaki karşılaştırma her zaman mümkün kalıyor.

## Neden arşivlendi

`concurrency_src_1s` (bir flow'un kendi zaman damgası etrafında ±1s
içinde aynı kaynak IP'den kaç flow daha geldiği) `14_concurrency_feature_experiment/`'de
doğrulandıktan sonra, 3 aşamalı bir rollout ile hem Dense hem VAE'nin
canonical modeline eklendi (bkz. `10_final_report/CHANGELOG.md`, 2026-07-30
tarihli "AŞAMA 1/3, 2/3, 3/3" maddeleri). Bu, apache_bench recall'unu
~%2.6'dan ~%91-95'e çıkaran, mimariden bağımsız (hem Dense hem VAE'de,
hem shuffled hem contiguous-blok testlerinde tutarlı) bir iyileştirme.
18-feature modeller artık canonical değil; bu klasör onların tam kaydı.

## İçindekiler ve eski→yeni eşleme

| bu klasördeki yol | orijinal yol (artık boş/taşınmış) | yerini alan güncel yol |
|---|---|---|
| `10_final_report/01_single_attack_type/` | `10_final_report/01_single_attack_type/` (v1) | `10_final_report/01_single_attack_type/` (v2, 19 feature) |
| `10_final_report/02_pairwise_attack_type/` | `10_final_report/02_pairwise_attack_type/` (v1) | `10_final_report/02_pairwise_attack_type/` (v2) |
| `10_final_report/03_segmented_injection/` | `10_final_report/03_segmented_injection/` (v1) | `10_final_report/03_segmented_injection/` (v2) |
| `10_final_report/04_apache_bench_diagnostics/` | aynı | güncellenmedi — kısmen tarihsel (kök-neden analizi hâlâ geçerli, ama IAT bölümündeki 2364x rakamı `13_temporal_feature_experiment/`'de artefakt olduğu gösterilmiş bir ölçümdür, bkz. aşağıda) |
| `10_final_report/05_notebooks_stochastic_legacy/` | `10_final_report/05_notebooks/_stochastic_legacy/` | n/a (eski stokastik-skorlu notebook'lar, deterministik z_mean'e geçişten kalma) |
| `phase3_dense/04_phase3_models/full_features/` | `phase3_dense/04_phase3_models/full_features/` (v1, 18f, 5 seed) | `phase3_dense/04_phase3_models/full_features/` (v2, 19f, 5 seed) |
| `phase3_vae/05_contamination_sweep/04_models/contam_0pct/` | aynı yol (v1, 18f, 20 seed) | `phase3_vae/05_contamination_sweep/04_models/contam_0pct/` (v2, 19f, 5 seed) |
| `13_temporal_feature_experiment/` | proje kökü (hiç canonical olmadı) | yok — bu hipotez elendi, aşağıya bakın |

**Önemli:** Dense ve VAE model klasörleri artık AYNI İSMİ (`full_features/`,
`contam_0pct/`) taşıyor — hem burada (v1, arşiv) hem canonical pipeline'da
(v2, güncel). Karıştırmamak için: bu klasörün İÇİNDE olan her şey v1
(18 feature); `V1_ARCHIVE/` dışında proje kökünde aynı isimli yollarda
duran her şey v2 (19 feature, `concurrency_src_1s` dahil).

`phase3_vae/05_contamination_sweep/04_models/`'un contam_0pct DIŞINDAKİ
alt klasörleri (contam_1pct, contam_2pct, ... contam_15pct/20pct/22pct)
bu rollout'un kapsamı dışındaydı ve HÂLÂ 18-feature v1 halleriyle,
`04_models/` içinde canonical konumlarında duruyor — arşive taşınmadılar,
çünkü onlar için hiç bir v2 karşılığı üretilmedi.

## `13_temporal_feature_experiment/` — neden burada

Bu, ayrı bir yan-deneydi: apache_bench'i yakalamak için "kaynak IP başına
önceki flow'a göre inter-arrival time" (IAT) feature'ı denendi ve **işe
yaramadığı** doğrulandı (recall değişmedi, KS=0.375, mevcut en iyi
feature'lardan zayıf). Ayrıca bu deney, `04_apache_bench_diagnostics/`'teki
orijinal IAT analizinin ("benign medyan IAT 2.18s, apache_bench 0.92ms,
2364x fark") bir ÖLÇÜM ARTEFAKTI olduğunu ortaya çıkardı — o analiz IAT'ı
yalnızca seyrek bir test alt kümesinde diff'lemişti; tüm flow'lar üzerinde
doğru tanımla benign medyan IAT aslında 1.98ms'dir (apache_bench'in
0.92ms'inden sadece ~2x uzak). Burada tutulma sebebi: hem "bu neden işe
yaramadı" sorusuna referans olarak, hem de bu artefakt bulgusunun kaydı
olarak. Asıl işe yarayan feature (`concurrency_src_1s`, pencere-bazlı
yoğunluk) `14_concurrency_feature_experiment/`'de (proje kökünde, canonical
— arşivlenmedi) bulunuyor.

## BİLİNEN AÇIK NOKTA (v2'ye taşınmadı)

**O3 dedup-prevalence düzeltmesi v2 raporlarına henüz uygulanmadı.** V1'in
`zmean_rescore/apply_dedup_prevalence_correction.py` aşamasında eklenen
düzeltme — resampled (window_resampled_15pct/20pct) flow kopyalarının
PR-AUC/F1 hesaplarındaki prevalans'ı çarpıtmasını önleyen, dedup edilmiş
test setinden hesaplanan "hybrid panel" — v2'nin single/pairwise/segmented
raporlarında YOK. ROC-AUC/recall/FPR (davranış metrikleri, dedup'tan
etkilenmediği v1'de zaten doğrulanmış — bkz. `01_single_attack_type/vae/
dedup_sanity_check/` bu klasörde) bundan etkilenmez; ama v2'nin PR-AUC/F1
sayılarını bu arşivdeki v1'in dedup-düzeltilmiş PR-AUC/F1'leriyle **birebir
karşılaştırırken bu farkı akılda tutmak gerekir** — v2 tarafında bu düzeltme
henüz bir gelecek iş kalemi.
