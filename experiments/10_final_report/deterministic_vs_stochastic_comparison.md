# Deterministik (z_mean) vs Stokastik Skorlama Karşılaştırması

**Tarih:** 2026-07-28 · **Bağlam:** `11_fable_review/independent_audit.md` bulgu **O2**'nin uygulaması.
**Kapsam:** Clean-only VAE (contam_0pct, 20 seed) — tekli, ikili ve bloklu (segmented) değerlendirmelerin tamamı yeniden skorlandı. **Retrain yok**; aynı 20 eğitilmiş model, sadece inference-zamanı skor fonksiyonu değişti.

## Ne değişti

1. **Skor:** Eski skor her flow için `z = z_mean + exp(0.5·z_log_var)·eps` ile **tek** stokastik örnek çekiyordu (`tf.random.normal`, keyfî 900_000/950_000 eval-seed offset'leri). Yeni skor `z = z_mean` kullanıyor — reparametrizasyon eval'de atlanıyor, eps yok, eval seed'i yok. Bir flow'un bir model altındaki skoru artık tek ve sabit bir sayı. (Kod: `evaluate_by_attack_type.py` → `reconstruction_error_zmean()` + `VAEBackend(deterministic=True)`; varsayılan davranış değişmedi, eski stokastik yol aynen duruyor.)
2. **Threshold (zorunlu yan değişiklik):** `threshold.json`'daki threshold_95 değerleri eğitim sırasında **stokastik** val error dağılımından kalibre edilmişti. Deterministik error'lar sistematik olarak daha küçük (eps gürültüsü yok) — örn. seed 0/7/16'da saklı stokastik threshold 0.149/0.138/0.093 iken deterministik yeniden kalibrasyon 0.090/0.075/0.073 veriyor. Saklı threshold'u aynen kullanmak FPR'yi yapay olarak düşürüp recall'u mekanik olarak kırpardı. Bu yüzden threshold_95, **aynı kural** (val-benign error'unun %95 percentile'ı) ve **aynı val seti** (`05_contamination_sweep/01_data/val_benign.csv`, 653 flow) ile deterministik skor üzerinden seed başına yeniden hesaplandı — DenseBackend'in zaten kullandığı "threshold'u val'den taze hesapla" konvansiyonunun aynısı.

**Dosya yerleşimi (2026-07-28 itibarıyla güncel):** deterministik sonuçlar ana
sonuç olarak benimsendi ve **kanonik dosya adlarını devraldı** (`results.csv/.md`,
`roc_pr_*.png`, `pooled_recall.png`, `decomposed_recall.{csv,png}`,
`block_recall_f1*.{md,csv}`, `error_plot.png`). Eski stokastik versiyonlar
silinmedi — her `vae/` klasörünün **`_stochastic_legacy/`** alt klasöründe,
orijinal adlarıyla duruyor:

| Değerlendirme | Deterministik (kanonik) | Stokastik (legacy) |
|---|---|---|
| Tekli | `01_single_attack_type/vae/results.{csv,md}` + `roc_pr_*.png` | `01_single_attack_type/vae/_stochastic_legacy/` |
| İkili | `02_pairwise_attack_type/vae/results.{csv,md}`, `results_combined.md`, `pooled_recall.png`, `decomposed_recall.{csv,png}` | `02_pairwise_attack_type/vae/_stochastic_legacy/` |
| Bloklu | `03_segmented_injection/vae/block_recall_f1*.{md,csv}`, `error_plot.png` | `03_segmented_injection/vae/_stochastic_legacy/` |

Runner'lar: `06_scripts/zmean_rescore/run_zmean_rescore.py` (tablolar + segmented) ve
`06_scripts/zmean_rescore/regenerate_plots_deterministic.py` (ROC/PR + pairwise grafikleri).

---

## Sayılar ne kadar değişti

### Tekli attack type (20 seed ort. ± std)

| attack_type | metrik | stokastik | deterministik (z_mean) | Δ |
|---|---|---|---|---|
| **apache_bench** | ROC-AUC | 0.5815 ± 0.0768 | **0.6670 ± 0.0890** | **+0.0855** |
| | PR-AUC | 0.2133 ± 0.0219 | 0.2565 ± 0.0391 | +0.0432 |
| | recall (thr95) | 0.0328 ± 0.0055 | **0.0262 ± 0.0000** | −0.0066 |
| | F1 (thr95) | 0.0507 ± 0.0081 | 0.0406 ± 0.0008 | −0.0101 |
| **portscan** | ROC-AUC | 0.9982 ± 0.0005 | 0.9988 ± 0.0005 | +0.0005 |
| | recall (thr95) | 0.9889 ± 0.0138 | 0.9983 ± 0.0077 | +0.0094 |
| **slowloris** | ROC-AUC | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0 |
| | recall (thr95) | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0 |
| (tüm gruplar) | benign FPR | 0.0565–0.0578 | 0.0577 ± 0.0058 | ≈0 |

### İkili kombinasyonlar

| pair | ROC-AUC (stok. → det.) | pooled recall (stok. → det.) |
|---|---|---|
| portscan+apache_bench | 0.7135 → **0.7725** (+0.059) | 0.3369 → 0.3355 |
| portscan+slowloris | 0.9993 → 0.9995 | 0.9953 → 0.9993 |
| apache_bench+slowloris | 0.7427 → **0.7950** (+0.052) | 0.4044 → 0.4007 |

### Bloklu (segmented) injection

| segment | stokastik | deterministik |
|---|---|---|
| benign 0 (FPR) | 0.0305 ± 0.0070 | 0.0321 ± 0.0110 |
| apache_bench (recall) | 0.0322 ± 0.0044 | **0.0262 ± 0.0000** |
| benign 2 (FPR) | 0.0336 ± 0.0078 | 0.0361 ± 0.0108 |
| slowloris (recall) | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 |
| benign 4 (FPR) | 0.0962 ± 0.0222 | 0.0933 ± 0.0239 |
| portscan (recall) | 0.9882 ± 0.0148 | 0.9983 ± 0.0077 |
| benign 6 (FPR) | 0.0696 ± 0.0088 | 0.0694 ± 0.0083 |

---

## Yorum

### 1. apache_bench: AUC yükseldi, recall düştü — ikisi de aynı nedenin iki yüzü

Stokastik eps gürültüsünün iki zıt etkisi varmış:

- **Sıralamayı bozuyordu** (AUC ↓): her flow'un error'una rastgele gürültü binince benign/attack sıralaması bulanıklaşıyor, AUC 0.5'e doğru çekiliyordu. Gürültü kalkınca modelin *gerçek* ayrım gücü ortaya çıktı: ROC-AUC 0.5815 → 0.6670 (+0.086), PR-AUC 0.213 → 0.257. Yani apache_bench, sanılandan bir miktar daha ayrılabilir — ama hâlâ zayıf (0.67 AUC, portscan/slowloris'in ~1.0'ına karşı).
- **Threshold üstüne rastgele "sahte recall" ekliyordu** (recall ↑ görünüyordu): eski 0.0328'lik recall'un ~%20'si, threshold'a yakın flow'ların eps şansıyla üstüne itilmesinden geliyordu. Deterministik skor bunu temizledi: recall 0.0262, F1 0.0406.

**En çarpıcı bulgu:** deterministik recall'un std'si **tam 0.0000** — 20 seed'in **her biri** 1487 apache_bench flow'unun **tam olarak aynı 39 tanesini** işaretliyor (seed 0/7/16'da kesişim 39/39 olarak doğrulandı). Yani apache_bench tespiti model ağırlıklarına değil, verinin kendisine bağlı sabit bir taban: 39 flow gerçekten benign error aralığının dışında, kalan ~1448'i her modelde threshold altında. Eski ±0.0055 std tamamen skorlama gürültüsüymüş. Bu, apache_bench zafiyetinin bir "şanssız seed" meselesi değil **yapısal bir feature-uzayı sınırı** olduğunu (bkz. `04_apache_bench_diagnostics/findings.md`) şimdiye kadarki en net şekilde gösteriyor.

### 2. portscan/slowloris: küçük iyileşme ya da değişim yok

Slowloris zaten her iki skorla da mükemmel (error'ları threshold'un ~10⁶ katı; gürültü fark yaratamıyor). Portscan recall'u 0.9889 → 0.9983: eski eksik %1'lik dilim de büyük oranda skorlama gürültüsüymüş. Benign FPR pratikte değişmedi (~%5.77) — threshold yeniden kalibrasyonunun doğru yapıldığının işareti (kural aynı: val-benign %95 → test FPR ≈ %5-6).

### 3. Benign FPR artık tüm gruplarda bit-aynı (0.057726)

Eskiden tekli/ikili gruplar arasında FPR %5.65–5.78 arasında oynuyordu — aynı benign seti, ama her grup koşusunda **yeni bir eps çekimi**. Deterministik skorla bir seed'in benign tahminleri sabit; grup kompozisyonundan bağımsız olarak aynı 0.0577 çıkıyor. Bu, "per-flow karar diğer flow'lardan bağımsızdır" iddiasının artık tam (gürültüsüz) doğrulaması — `results_combined_zmean.md`'de apache_bench-only recall'un solo ve her iki pair'de birebir 0.0262 çıkması da aynı şeyi gösteriyor (eski dosyada "up to seed-sampling noise" kaydıyla yaklaşık eşitti; artık kayıtsız eşit).

### 4. Bloklu injection: audit bulgusu O6 güçlendi

Benign segment FPR'leri neredeyse hiç değişmedi (0.032/0.036/0.093/0.069). Segment-4 ve 6'daki yüksek FPR skorlama gürültüsüyle **açıklanamıyor** — gürültü tamamen kalktığı hâlde desen aynen duruyor. Bu, o farkın sistematik (ts-sıralı bölmede geç window'ların benign kompozisyonu) olduğu yönündeki audit yorumunu (O6) doğrudan destekliyor; `_zmean.md` içindeki otomatik "sample-size" yorumu şablondan geliyor ve bu veriyle artık savunulamaz.

### 5. 20 seed'in artık anlamı ne

Eskiden std sütunları iki kaynağı karışık ölçüyordu: (a) eğitim/ağırlık-init varyansı + (b) skorlamanın tek-örnek MC gürültüsü. Artık (b) sıfır; **std sütunları saf eğitim varyansıdır** — "modeli yeniden eğitsem sonuç ne kadar oynar" sorusunun temiz cevabı. Sonuçları:

- Bazı std'ler **büyüdü** (apache_bench ROC-AUC 0.077 → 0.089): gürültü kalkınca seed'ler arası *gerçek* model farkları daha net görünür oldu — apache_bench sıralaması ağırlıklara hakikaten duyarlı.
- Bazı std'ler **sıfıra çöktü** (apache_bench recall, slowloris her şeyi): threshold-üstü küme her eğitimde aynı — bu metrikler veri tarafından belirleniyor, eğitim rastgeleliğinden bağımsız.
- 20 seed hâlâ gerekli ve anlamlı: modeller ağırlık olarak hâlâ farklı (seed başına ortalama error'lar 1e3–2.3e4 arasında oynuyor), sadece her modelin skoru artık gürültüsüz ölçülüyor.

## Karar için özet

İki sonuç seti de aynı niteliksel hikâyeyi anlatıyor (slowloris/portscan ≈ mükemmel, apache_bench ≈ tespit edilemiyor); hiçbir bulgu tersine dönmedi. Deterministik set lehine noktalar: tekrarlanabilir (keyfî eval-seed yok), AUC'ler modelin gerçek sıralama gücünü ölçüyor, std'lerin tek ve net bir anlamı var, apache_bench recall'undaki iyimser gürültü payı temizlendi. Stokastik set lehine tek nokta: threshold'ları eğitim zamanında saklanan orijinal kalibrasyonla birebir aynı (deterministik sette threshold aynı kuralla ama yeniden hesaplandı). Karar (hangisinin ana sonuç olacağı) size bırakıldı; hangisi seçilirse seçilsin, raporda skorlama modunun ve threshold kalibrasyon kaynağının açıkça yazılması yeterli.
