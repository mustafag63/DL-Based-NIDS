# 10_final_report — Genel İndeks

Bu klasör, `09_final_report/` (Fransızca yazılı rapor) ve
`10_final_deliverables_31_temmuz/` (attack-type analizi, segmented injection,
Dense v1 karşılaştırması, apache_bench tanı script'leri, notebook'lar)
klasörlerinin **birleştirilmiş, tek final sürümüdür**. Tüm sonuçlar
inference-only'dir — hiçbir modelin yeniden eğitilmesi (retrain) yapılmadı;
sadece zaten eğitilmiş modeller (VAE clean-only `contam_0pct`, 20 seed;
Dense autoencoder v1 `full_features`, 5 seed) üzerinde değerlendirme yapıldı.

**Skorlama notu (2026-07-28):** VAE sonuçları **deterministik z_mean
skoruyla** üretilmiştir (reparametrizasyon eval'de atlanır, z = z_mean;
threshold_95 aynı kuralla val-benign üzerinde deterministik skordan yeniden
kalibre edilir). Eski tek-örnekli stokastik skorun sonuçları her `vae/`
klasörünün `_stochastic_legacy/` alt klasöründe saklıdır; gerekçe ve
sayı-sayı karşılaştırma için bkz.
[`deterministic_vs_stochastic_comparison.md`](deterministic_vs_stochastic_comparison.md)
ve [`CHANGELOG.md`](CHANGELOG.md). Dense v1 skoru zaten deterministikti,
değişmedi.

**Prevalans notu (2026-07-28):** VAE tablolarındaki **PR-AUC ve F1**,
resampled flow kopyalarının çift sayımının prevalans'ı çarpıtmaması için
**dedup edilmiş** test setinden hesaplanır (örn. apache_bench için n=968
distinct flow); **recall/ROC-AUC/FPR** davranış metrikleri olduğundan
kanonik (dedup'suz) settedir — iki set arasında davranışsal farkın <0.02
olduğu doğrulanmıştır. Ayrıntı: her tablonun dipnotu +
[`01_single_attack_type/vae/dedup_sanity_check/`](01_single_attack_type/vae/dedup_sanity_check/results_dedup.md).

**Kapsam kısıtı:** VAE ve Dense v1 sonuçları burada kasıtlı olarak
**karşılaştırmalı/yan yana grafiklerle birleştirilmemiştir** — her model
kendi `vae/` veya `dense_v1/` alt klasöründe, kendi grafikleriyle ayrı ayrı
durur. Amaç, her analizi kendi başına net biçimde gözlemlemek.

---

## Klasör yapısı ve özetler

### [01_single_attack_type/](01_single_attack_type/) — Tekli attack-type performansı

Her attack type (apache_bench / portscan / slowloris) için, benign havuzuna
karşı ayrı ayrı değerlendirme: ROC-AUC, PR-AUC, F1, recall. `vae/` ve
`dense_v1/` alt klasörlerinin her birinde 3 ayrı PNG var (`roc_pr_<tip>.png`
— her birinde o attack type için ROC eğrisi + Precision-Recall eğrisi yan
yana), artı `results.csv`/`results.md`.

**Bulgu:** portscan ve slowloris neredeyse mükemmel tespit ediliyor
(recall ≥ 0.998), ama **apache_bench her iki modelde de neredeyse hiç
tespit edilmiyor** (VAE recall = 2.6%, Dense v1 recall = 2.6%, ROC-AUC
sırasıyla 0.67 / 0.72 — kullanılabilir bir tespit için çok düşük).
Deterministik skorun çarpıcı bir yan bulgusu: VAE'nin apache_bench
recall'ünün seed'ler arası std'si **tam 0.0000** — 20 seed'in her biri
1487 apache_bench flow'unun **aynı 39 tanesini** işaretliyor. Zafiyet
eğitim rastgeleliğinden bağımsız, yapısal bir feature-uzayı sınırı.

![VAE — apache_bench ROC & PR](01_single_attack_type/vae/roc_pr_apache_bench.png)

### [02_pairwise_attack_type/](02_pairwise_attack_type/) — İkili attack-type kombinasyonları

3 olası ikili (portscan+apache_bench, portscan+slowloris,
apache_bench+slowloris) için, hem **poolanmış (pooled) recall** (çiftin tüm
saldırı flow'ları birlikte) hem de **ayrıştırılmış (decomposed) recall**
(çift içindeki her tipin kendi flow'ları, aynı model/eşikte) ayrı ayrı grafik
olarak `vae/` ve `dense_v1/` altında.

**Bulgu:** apache_bench'in poolanmış recall'ü, iyi tespit edilen bir tiple
(portscan/slowloris) eşleştirildiğinde 34-40%'a "yükseliyormuş" gibi
görünüyor — ama bu bir yanılsama: ayrıştırılmış recall gösteriyor ki
apache_bench'in **kendi** flow'larındaki tespit oranı 2.62%'de sabit
kalıyor — tek başına değerlendirildiğindeki değerle **birebir aynı**
(deterministik skorla artık "seed gürültüsü dahilinde" kaydına bile gerek
yok; eşitlik tam). Model, karar verirken diğer flow'ların varlığından
etkilenmiyor — bu statik, flow-bazlı bir dedektör.

### [03_segmented_injection/](03_segmented_injection/) — Bloklu (contiguous) enjeksiyon

Aynı test flow'ları, karışık sırada değil, her attack type'ın tek bir
bitişik blok halinde göründüğü bir akışa yeniden sıralanmış
(benign → apache_bench → benign → slowloris → benign → portscan → benign).
`vae/` ve `dense_v1/` her birinde: pozisyona göre reconstruction error
grafiği (`error_plot.png`) + blok bazlı recall/F1 tablosu (`block_recall_f1.md`).

**Bulgu:** Blok bazlı recall'ler (VAE: 0.026 / 1.00 / 0.998), karışık test
setindeki değerlerle (0.026 / 1.00 / 0.998) birebir aynı —
saldırının karışık mı yoksa bitişik blok halinde mi geldiği modelin
davranışını değiştirmiyor, çünkü model sequence-state taşımıyor.

**Ek bulgu (benign gap FPR'leri, denetim O6):** Benign segmentlerin FPR'si
%3.2–%9.3 arasında değişiyor — bu **örnekleme gürültüsü değil, sistematik
bir kompozisyon etkisi**: benign havuzu ts sırasına göre bölündüğü ve
window'lar zamanda ardışık olduğu için her gap farklı window'ların
benign'ini içeriyor, window başına benign FPR ise keskin biçimde farklı
(window_06: 0.100, window_07: 0.115; diğerleri 0.029–0.053). n≈1705'lik
gap'lerde binom std ~0.005'tir ve deterministik skor gürültüyü tamamen
kaldırdığı hâlde desen aynen korunmuştur. Kanıt tablosu:
[`03_segmented_injection/vae/segment_window_composition.md`](03_segmented_injection/vae/segment_window_composition.md).

### [04_apache_bench_diagnostics/](04_apache_bench_diagnostics/) — apache_bench neden kaçırılıyor?

apache_bench'in neden benign'den ayırt edilemediğini araştıran tanı
analizi: feature bazında KS testi + etki büyüklüğü (mean-shift-in-std),
reconstruction error histogramı, ve bir **temporal (zamansal) hipotez
testi** — flow'lar arası varış süresi (inter-arrival time, IAT).

**Bulgu:** apache_bench'in tekil-flow feature'ları (byte/paket/süre)
istatistiksel olarak ayrışıyor (KS ≈ 0.62-0.76) ama etki büyüklüğü küçük
(~0.4-0.7 benign standart sapması — yani hâlâ benign'in normal aralığı
içinde). IAT feature'ı ise medyan bazında **~2364x** daha kısa çıkıyor
(apache_bench: 0.00092s, benign: 2.18s) — çok daha büyük bir etki
büyüklüğü, ama KS istatistiği açısından en iyi tekil-flow feature'lardan
daha yüksek değil. **Bu bulgu retrain ile doğrulanmamıştır** — bir
zamansal/hız feature'ı eklenip modelin yeniden eğitilmesi gerekir, bu
diagnostik yalnızca istatistiksel ayrışabilirliği gösterir.

![VAE reconstruction error — benign vs apache_bench vs diğerleri](04_apache_bench_diagnostics/vae_reconstruction_error_hist.png)

![IAT — benign vs apache_bench](04_apache_bench_diagnostics/iat_apache_bench_vs_benign_hist.png)

### [05_notebooks/](05_notebooks/) — Gözlemlenebilir Jupyter notebook'ları

Yukarıdaki 4 script ailesinin (attack-type analizi, segmented injection,
Dense v1 karşılaştırması, apache_bench diagnostics) mantığını hücre hücre,
ara çıktı/grafiklerle yeniden üreten, tamamı çalıştırılmış (executed)
notebook'lar:

- `01_attack_type_analysis.ipynb`
- `02_segmented_injection.ipynb`
- `03_dense_v1_comparison.ipynb`
- `04_apache_bench_diagnostics.ipynb`

### [06_scripts/](06_scripts/) — Kaynak script referans kopyaları

Bu raporun tüm sonuçlarını üreten script'lerin referans kopyaları
(alt klasörler orijinal konumlarını yansıtır): `06_attack_type_analysis/`,
`07_segmented_injection/`, `08_dense_v1_comparison/`,
`apache_bench_diagnostics/`, `dependencies/` (paylaşılan yardımcı
fonksiyonlar), `report_generation/` (bu final raporun grafiklerini üreten
script'ler), `zmean_rescore/` (deterministik z_mean yeniden-skorlama:
tabloları üreten `run_zmean_rescore.py` + grafikleri üreten
`regenerate_plots_deterministic.py`).

### [07_final_written_report/](07_final_written_report/) — Yazılı final rapor (Fransızca)

`rapport_final_attack_type_analysis.{md,pdf}` — Gérard için hazırlanmış
teknik rapor. **Güncel sürüm**, apache_bench için yeni bir "Diagnostic
complémentaire" bölümü (bölüm 6) içerir: KS/etki-büyüklüğü analizi,
reconstruction error doğrulaması, ve IAT hipotez testi (~2364x bulgusu,
retrain ile doğrulanmadığı notu dahil).

---

## Genel sonuç

Her iki mimari de (VAE ve Dense v1) apache_bench'i neredeyse tamamen
kaçırıyor — bu, mimariye özgü bir kusur değil, **mevcut 18 feature'lık
setin bir sınırlaması**. apache_bench'in tekil flow'ları benign HTTP
trafiğinden ayırt edilemeyecek kadar sıradan görünüyor; onu asıl anormal
kılan şey, flow'lar-arası tekrar sıklığı (bkz. `04_apache_bench_diagnostics/`
IAT bulgusu) — ki bu, tek-flow bazlı reconstruction error mimarisinin
doğası gereği göremediği bir sinyal. Sıradaki adım, zamansal/eşzamanlılık
feature'ları eklenip modelin yeniden eğitilmesi ve bu hipotezin
doğrulanmasıdır.

## Kaynak / orijinal klasörler hakkında not

Bu klasör `09_final_report/` ve `10_final_deliverables_31_temmuz/`
içeriğini birleştirir; onaylandıktan sonra o iki klasör silinecektir. Bu
birleştirme sırasında hiçbir orijinal script değiştirilmedi — sadece
kopyalandı ve (görsel kalite standardını tutturmak için) bazı PNG'ler daha
büyük fontlar ve daha açıklayıcı başlıklarla, aynı istatistiksel mantık
yeniden çalıştırılarak yeniden üretildi.
