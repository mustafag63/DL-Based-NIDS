# CHANGELOG — 10_final_report

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
