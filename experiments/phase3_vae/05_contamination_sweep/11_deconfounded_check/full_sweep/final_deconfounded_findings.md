# Tam deconfounded contamination sweep — final bulgular

**Tarih:** 2026-07-28 · **Bağlam:** `deconfound_comparison_findings.md`'deki 2 noktalı
doğrulamanın (K1+K2, audit) 9 noktanın tamamına genişletilmesi. Orijinal (v1) sweep
dosyalarına dokunulmadı.

## Kurulum

- **Pipeline:** v2 (deconfounded) — K1: test benign = %70 window_10 + %30 window_02-08
  (her window'dan eşit 39 flow; window_06/07 aşırı temsili engelli), K2: window_10
  benign'i signature-grouped split, O2: uçtan uca deterministik z_mean skor +
  deterministik val-benign threshold_95.
- **9 nokta:** 0/1/2/4/8/12% injection + %14.38/%19.27/%21.26 resampled (v1'in
  without-replacement disiplini korunarak mevcut `window_resampled_15pct/20pct/
  22pct_clean` window'larından; yeni sentetik veri üretilmedi; bare-uid leak filtresi
  v2 test setine karşı — benign tarafta da 30/26/29 çakışma yakalanıp train'den atıldı).
- **Her nokta 20 seed**, aynı hyperparametreler (latent=10, beta=0.25), aynı sabit v2
  test seti (909 benign + 101 attack).
- **Referans kolu `v1_det`:** orijinal sweep'in 9 seviyesinin mevcut modelleri,
  deterministik z_mean skorla v1 test setinde yeniden değerlendirildi — böylece v1-v2
  karşılaştırması skorlama-modu farkına (O2) takılmıyor; fark yalnızca pipeline'dan
  (K1+K2 + yeni eğitim) geliyor.
- **İstatistik:** her nokta vs %0 baseline, PR-AUC ortalama farkı üzerine 10.000
  resample'lık bootstrap %95 CI (`bootstrap_significance.py`'nin fonksiyonları
  import edilerek — aynı yöntem, aynı rng seed 12345).

## Ana sonuç

> **"Clean-only en iyisi" iddiası deconfounded pipeline'da 8/8 sıfır-dışı
> kontaminasyon seviyesinde istatistiksel olarak anlamlı şekilde geçerli.**
> Her seviyenin PR-AUC'si %0 baseline'dan düşük ve %95 bootstrap CI'ların hiçbiri
> 0'ı içermiyor. Confound'lar düzeltilince iddia zayıflamadı — tersine,
> kontaminasyonun zararı v1'dekinden **daha büyük** ölçülüyor (aşağıda).

## v2 (deconfounded) — 9 nokta, PR-AUC vs %0 bootstrap

| kontaminasyon | PR-AUC (ort ± std) | Δ vs %0 | %95 CI | anlamlı? |
|---|---|---|---|---|
| 0% | 0.7516 ± 0.0281 | — | — | (baseline) |
| 1% | 0.7250 ± 0.0250 | −0.0266 | [−0.0426, −0.0104] | **EVET** |
| 2% | 0.7022 ± 0.0299 | −0.0494 | [−0.0667, −0.0323] | **EVET** |
| 4% | 0.6529 ± 0.0393 | −0.0988 | [−0.1200, −0.0790] | **EVET** |
| 8% | 0.6355 ± 0.0481 | −0.1161 | [−0.1413, −0.0939] | **EVET** |
| 12% | 0.6561 ± 0.0655 | −0.0955 | [−0.1289, −0.0684] | **EVET** |
| 14.38% | 0.6010 ± 0.0972 | −0.1506 | [−0.1937, −0.1092] | **EVET** |
| 19.27% | 0.6616 ± 0.0762 | −0.0900 | [−0.1269, −0.0591] | **EVET** |
| 21.26% | 0.6433 ± 0.0866 | −0.1083 | [−0.1493, −0.0718] | **EVET** |

Eğri: `contamination_curve_deconfounded.png` (95% bootstrap CI error bar'ları,
orijinal `plot_contamination_curve_with_ci.py` formatı; bu koşumda "içi boş/anlamsız"
işaretlenecek nokta çıkmadı — hepsi dolu).

## Nokta-nokta v1_det vs v2 karşılaştırması

(v1_det = orijinal pipeline + deterministik skor, v1 test setinde; v2 = deconfounded,
v2 test setinde. Test setleri farklı olduğundan satırlar "iki pipeline'ın kendi
raporladığı sayı" karşılaştırmasıdır.)

| hedef | v1_det PR-AUC | v2 PR-AUC | Δ(v2−v1_det) | v1_det Δ vs %0 | v2 Δ vs %0 |
|---|---|---|---|---|---|
| 0% | 0.7274 | 0.7516 | +0.0243 | — | — |
| 1% | 0.7100 | 0.7250 | +0.0150 | −0.0174 ✓ | −0.0266 ✓ |
| 2% | 0.7062 | 0.7022 | −0.0039 | −0.0212 ✓ | −0.0494 ✓ |
| 4% | 0.6831 | 0.6529 | −0.0302 | −0.0443 ✓ | −0.0988 ✓ |
| 8% | 0.6494 | 0.6355 | −0.0139 | −0.0780 ✓ | −0.1161 ✓ |
| 12% | 0.6450 | 0.6561 | +0.0111 | −0.0824 ✓ | −0.0955 ✓ |
| 15% (≈14.3) | 0.6492 | 0.6010 | −0.0482 | −0.0782 ✓ | −0.1506 ✓ |
| 20% (≈19.3) | 0.6681 | 0.6616 | −0.0065 | −0.0593 ✓ | −0.0900 ✓ |
| 22% (≈21.3) | 0.6700 | 0.6433 | −0.0267 | −0.0574 ✓ | −0.1083 ✓ |

(✓ = %95 CI 0'ı dışlıyor. Tam CI'lar: `bootstrap_significance_deconfounded.csv`,
her iki kol `arm` kolonuyla.)

**Hangi noktalarda fark var, hangilerinde yok:**

- **Mutlak PR-AUC'lerde fark her noktada küçük** (|Δ| ≤ 0.048, işaret karışık):
  confound'ların v1 sayılarını sistematik şişirdiği hipotezi doğrulanmadı. En büyük
  fark %15 hedef noktasında (−0.048) — v2'nin en gürültülü noktası (std 0.097),
  CI genişliği içinde.
- **Clean'den uzaklık (Δ vs %0) v2'de her seviyede daha büyük:** örn. 4%'te −0.099 vs
  −0.044, 14.38%'de −0.151 vs −0.078. Yani deconfounding, kontaminasyonun zararını
  *daha görünür* yaptı. Mekanizması `deconfound_comparison_findings.md`'deki K2
  bulgusuyla tutarlı: grouped split near-duplicate'leri ayıklayınca clean modelin
  threshold'u/FPR'si iyileşiyor (v2 0%'da FPR 0.026 vs v1_det 0.042), kontamine
  modellerde ise FPR kontaminasyonla 0.052'ye tırmanıyor (v1_det'te ~0.041'de
  sabitti) — kontaminasyonun benign-manifold'u bozması v2'de maskelenmiyor.
- **v1'in yüksek-%'lerdeki "toparlanma" deseni v2'de zayıfladı:** v1_det'te 19.3/21.3%
  noktaları (0.668/0.670) 8-15% bandından *yüksekti*; v2'de de hafif bir tümsek var
  (19.27%: 0.662 > 14.38%: 0.601) ama hepsi clean'in belirgin altında ve anlamlı.
  Desenin tamamen kaybolmaması, bunun (with-replacement dışlandıktan sonra kalan
  kısmının) resampled window'ların farklı train kompozisyonundan (benign'i
  window_01-08'den gelir, injection noktalarının window_10 havuzundan değil)
  kaynaklanabileceğini düşündürüyor — pipeline'lar arası ortak, tasarım-kaynaklı
  bir özellik.

## Kayıtlar ve sınırlamalar

- v2 test seti küçük (1010 flow, 101 attack) — yüksek kontaminasyon noktalarında
  seed-std'leri büyük (±0.08-0.10); anlamlılık sonuçları buna rağmen net, ama tekil
  nokta ortalamaları ±0.03-0.04 hassasiyetle okunmalı.
- Anlamlılık "20 bağımsız eğitim koşusu" düzeyindedir (orijinal
  `bootstrap_significance.py`'nin kendi kaydıyla aynı) — veri-üretim süreci hakkında
  dağılımsal bir iddia değildir.
- Resampled noktaların train setleri injection noktalarından yapıca farklıdır
  (window'un kendi benign+attack karışımı vs window_10 havuzu + enjeksiyon) — bu,
  v1'den miras alınan bilinçli bir tasarım; x-ekseni üzerinde iki rejimi ayıran 12%
  çizgisi grafikte korunmuştur.
- v1_det ile v2 farklı test setleri kullanır; pipeline'lar arası satır farkları
  yaklaşıktır. Kol-içi (v2'nin kendi 9 noktası) karşılaştırmalar aynı sabit test
  setinde ve birebir geçerlidir.

## Dosyalar

- `results_all_points.csv` — v2 per-seed (9 nokta × 20 seed; FPR'nin w10/0208
  kaynak kırılımı dahil)
- `v1_deterministic_results_per_seed.csv` — v1_det referans kolu
- `bootstrap_significance_deconfounded.csv` — iki kolun Δ-vs-%0 bootstrap tabloları
- `bootstrap_point_ci_deconfounded.csv` — grafikteki error bar'ların nokta CI'ları
- `contamination_curve_deconfounded.png` — 2×2 eğri (orijinal formatla tutarlı)
- `comparison_by_level.csv` — seviye bazında v1_det/v2 ortalama metrikler
- Script'ler: `prepare_full_sweep_data.py` → `train_evaluate_full_sweep.py`
  (`training.log`) → `analyze_full_sweep.py`
- Modeller: `../04_models/contam_{0,1,2,4,8,12,15,20,22}pct_v2/seed_0..19/`
