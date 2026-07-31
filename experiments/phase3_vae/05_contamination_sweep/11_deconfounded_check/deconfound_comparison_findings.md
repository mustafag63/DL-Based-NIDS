# Deconfound doğrulama kolu — K1 + K2 düzeltmeleriyle sonuç değişti mi?

**Tarih:** 2026-07-28 · **Bağlam:** `11_fable_review/independent_audit.md` bulguları
**K1** (sweep test setinde benign=window_10, attack=window_02-08 → capture-oturumu
confound'u) ve **K2** (window_10 benign'inin signature-grouping'siz düz rastgele
bölünmesi → near-duplicate sızıntısı). Yeniden veri toplama yok; mevcut veriyle,
orijinal sweep dosyalarına dokunmadan ayrı bir doğrulama kolu.

## Kurulum

| | v1 (orijinal, confound'lu) | v2 (deconfounded) |
|---|---|---|
| window_10 benign bölünmesi | düz `rng.permutation` %70/15/15 | **GroupShuffleSplit(signature_id)** (faz2 formülü; train=3126 / val=594 / test_w10=636; signature kesişimi yok) |
| test benign | %100 window_10 (653) | **%70 window_10 (636) + %30 window_02-08 (273, her window'dan eşit 39)** — eşit pay, O6'da bulunan yüksek-FPR'li window_06/07'nin aşırı temsilini önlemek için |
| test attack | window_02-08 örneklemi, %10 hedef | aynı mantık (101 flow, %10.00) |
| train/val | window_10 | window_10 (değişmedi — threshold kalibrasyonu türü aynı) |
| skorlama | (baseline burada deterministik yeniden hesaplandı) | **deterministik z_mean** (O2), threshold_95 = val-benign deterministik error %95 pctl |
| mimari/hyperparam | latent=10, beta=0.25, dropout=0.1, batch=64, epochs≤200, patience=12 | birebir aynı, retrain sadece v2 verisiyle |

Üç kol, hepsi 20 seed: **v1_0pct_det** (mevcut contam_0pct modelleri, v1 test seti,
deterministik skor — elmalar-elmalarla baseline), **v2_0pct** (yeni eğitim, v2 test),
**v2_4pct** (yeni eğitim, %4 kontaminasyon, v2 test).

## Sonuçlar (20 seed ort. ± std)

| metrik | v1_0pct (confound'lu) | v2_0pct (deconfounded) | Δ (v2−v1) | v2_4pct |
|---|---|---|---|---|
| PR-AUC | 0.7274 ± 0.0177 | **0.7516 ± 0.0281** | **+0.0243** | 0.6529 ± 0.0393 |
| ROC-AUC | 0.8864 ± 0.0329 | 0.8961 ± 0.0504 | +0.0097 | 0.8098 ± 0.0406 |
| F1 (thr95) | 0.6371 ± 0.0125 | 0.7041 ± 0.0223 | +0.0670 | 0.6507 ± 0.0564 |
| attack recall (thr95) | 0.6438 ± 0.0000 | 0.6673 ± 0.0093 | +0.0235 | 0.6342 ± 0.0583 |
| benign FPR (thr95) | 0.0422 ± 0.0045 | 0.0256 ± 0.0076 | −0.0166 | 0.0355 ± 0.0153 |
| threshold_95 | 0.0903 | 0.1215 | +0.0312 | 0.2500 |

v2 FPR'nin kaynak kırılımı: v2_0pct → window_10 benign 0.0204, window_02-08 benign
0.0375; v2_4pct → 0.0308 / 0.0463.

## Ana sonuç: **headline bulgu DEĞİŞMEDİ**

1. **v1 vs v2 0% farkı küçük ve pozitif yönde:** PR-AUC Δ = +0.024 (< 0.05 eşiği),
   ROC-AUC Δ = +0.010. Confound'lar düzeltilince clean-only performans düşmedi —
   hafifçe *yükseldi*. v1'in mutlak sayıları confound tarafından şişirilmiş **değilmiş**;
   iki iyimserlik kaynağı (K1, K2) bu veri/model kombinasyonunda pratikte küçük çıktı.
   (Dikkat: v1 ve v2 test setleri farklı — bu satır "aynı testte iki model" değil,
   "iki pipeline'ın kendi raporladığı sayı" karşılaştırmasıdır; asıl kanıt aşağıdaki
   iki mekanizma ölçümüdür.)

2. **"Clean-only, kontamine olandan iyi" v2'de de net:** v2_0pct, v2_4pct'yi aynı test
   setinde her sıralama metriğinde açık farkla geçiyor (PR-AUC 0.752 vs 0.653 = +0.099;
   ROC-AUC 0.896 vs 0.810 = +0.086; recall 0.667 vs 0.634). %4'lük küçük kontaminasyon
   bile deconfounded pipeline'da belirgin zarar veriyor — kontaminasyon eğrisinin
   niteliksel mesajı deconfound edilince de ayakta.

## Mekanizma ölçümleri (neden fark küçük çıktı)

- **K1'in gerçek büyüklüğü (doğrudan ölçüm):** v1 modellerinin, hiçbir v1 modelinin
  hiç görmediği window_02-08 benign flow'larındaki FPR'si **0.0480 ± 0.0056** — kendi
  window_10 test benign'indeki 0.0422'ye çok yakın. Yani "model window_10'u değil
  saldırıyı öğrenmiş mi?" sorusunun cevabı büyük ölçüde evet: yabancı oturumların
  benign'i, eğitim dağılımının benign'inden yalnızca marjinal daha fazla alarm
  üretiyor. K1 teorik olarak geçerli bir confound'du ama bu modellerde etkisi küçük.
  (v2_0pct'de de aynı desen: FPR_w10 0.020 vs FPR_0208 0.038 — fark var ama attack
  skorlarının çok altında.)

- **K2'nin öngördüğü mekanizma birebir doğrulandı:** grouped split ile near-duplicate'ler
  val'den ayıklanınca val-benign error dağılımı sağa kaydı ve threshold_95 0.090 →
  0.122'ye yükseldi; bunun sonucu FPR 0.042 → 0.026'ya düştü (recall düşmeden,
  hatta +0.024). Yani v1'in threshold'u gerçekten near-duplicate'lerce aşağı çekiliyormuş —
  denetimin öngördüğü yön doğru; etkisi AUC'ye değil çalışma noktasına yansıyormuş.

## Kayıtlar ve sınırlamalar

- v2 test seti küçük (909 benign + 101 attack); seed başına metrik std'leri v1'den
  büyük (PR-AUC ±0.028 vs ±0.018). Sonuç yönleri bu belirsizlikte rahatça ayrışıyor
  ama v2 mutlak sayıları ±0.03 hassasiyetle okunmalı.
- v1 ve v2'nin test attack örneklemleri farklı rastgele çekilişler; v1-v2 satır
  karşılaştırması bu yüzden yaklaşık niteliktedir. Clean-vs-4% karşılaştırması ise
  aynı v2 test setinde, birebir geçerli.
- v1_0pct recall'unun 20 seed'de tam 0.6438 ± 0.0000 çıkması, deterministik skorda
  daha önce görülen deseni tekrarlıyor (threshold-üstü küme ağırlıklardan bağımsız,
  veri tarafından belirleniyor).
- Bu kol yalnızca 0% ve 4% noktalarını kapsar; tam sweep (1/2/8/12/15/20/22%)
  v2 pipeline'la yeniden koşulmadı. Eğrinin tamamı alıntılanırken v1 sonuçları
  kullanılmaya devam edecekse, bu dokümana referansla K1/K2 sınırlaması not edilmeli.

## Dosyalar

- Veri: `01_data/` (`test_set_v2.csv` — `benign_source` kolonu ile, `val_benign_v2.csv`,
  `train_contam_{0,4}pct_v2.csv`, `manifest_v2.json`)
- Modeller: `04_models/contam_{0,4}pct_v2/seed_0..19/`
- Sonuçlar: `v2_0pct_results.csv/.md`, `v2_4pct_results.csv/.md`,
  `v1_0pct_deterministic_results.csv`, `comparison_summary.csv`
- Script'ler: `../prepare_contamination_data_v2.py`, `train_and_evaluate_v2.py`
