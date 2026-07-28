# Segment x window kompozisyonu — benign-gap FPR farklarının kaynağı (O6 kanıtı)

`build_segmented_injection.py` benign havuzunu **ts sırasına göre** bitişik,
yakın-eşit parçalara böler; capture window'ları zamanda ardışık olduğundan her
benign gap **farklı window'ların** benign flow'larını içerir. Aşağıdaki tablolar,
gap'ler arası FPR farkının (0.032 / 0.036 / 0.093 / 0.069) örnekleme gürültüsü
değil, bu kompozisyon farkının sistematik sonucu olduğunu gösterir.
(Skor: deterministik z_mean, 20 seed, seed başına val-benign'den yeniden
hesaplanan threshold_95 — segmented değerlendirmenin kendisiyle aynı konvansiyon.)

## 1. Segment x window kompozisyonu

| segment_id | segment_label | window_id | n | segment'in %'si |
|---|---|---|---|---|
| 0 | benign | window_02_3pct | 696 | 40.8 |
| 0 | benign | window_03_5pct | 533 | 31.3 |
| 0 | benign | window_04_7pct | 78 | 4.6 |
| 0 | benign | window_resampled_15pct | 195 | 11.4 |
| 0 | benign | window_resampled_20pct | 203 | 11.9 |
| 1 | apache_bench | window_04_7pct | 129 | 8.7 |
| 1 | apache_bench | window_05_12pct | 184 | 12.4 |
| 1 | apache_bench | window_07_17pct | 276 | 18.6 |
| 1 | apache_bench | window_08_22pct | 379 | 25.5 |
| 1 | apache_bench | window_resampled_15pct | 196 | 13.2 |
| 1 | apache_bench | window_resampled_20pct | 323 | 21.7 |
| 2 | benign | window_04_7pct | 706 | 41.4 |
| 2 | benign | window_05_12pct | 619 | 36.3 |
| 2 | benign | window_resampled_15pct | 195 | 11.4 |
| 2 | benign | window_resampled_20pct | 185 | 10.9 |
| 3 | slowloris | window_02_3pct | 14 | 1.5 |
| 3 | slowloris | window_03_5pct | 30 | 3.2 |
| 3 | slowloris | window_04_7pct | 40 | 4.3 |
| 3 | slowloris | window_05_12pct | 100 | 10.8 |
| 3 | slowloris | window_06_15pct | 125 | 13.5 |
| 3 | slowloris | window_07_17pct | 158 | 17.0 |
| 3 | slowloris | window_08_22pct | 173 | 18.6 |
| 3 | slowloris | window_resampled_15pct | 132 | 14.2 |
| 3 | slowloris | window_resampled_20pct | 157 | 16.9 |
| 4 | benign | window_05_12pct | 277 | 16.2 |
| 4 | benign | window_06_15pct | 773 | 45.3 |
| 4 | benign | window_07_17pct | 447 | 26.2 |
| 4 | benign | window_resampled_15pct | 115 | 6.7 |
| 4 | benign | window_resampled_20pct | 93 | 5.5 |
| 5 | portscan | window_02_3pct | 42 | 6.1 |
| 5 | portscan | window_04_7pct | 73 | 10.5 |
| 5 | portscan | window_05_12pct | 182 | 26.2 |
| 5 | portscan | window_06_15pct | 233 | 33.6 |
| 5 | portscan | window_07_17pct | 6 | 0.9 |
| 5 | portscan | window_08_22pct | 3 | 0.4 |
| 5 | portscan | window_resampled_15pct | 73 | 10.5 |
| 5 | portscan | window_resampled_20pct | 82 | 11.8 |
| 6 | benign | window_07_17pct | 426 | 25.0 |
| 6 | benign | window_08_22pct | 873 | 51.2 |
| 6 | benign | window_resampled_15pct | 214 | 12.5 |
| 6 | benign | window_resampled_20pct | 193 | 11.3 |

## 2. Window başına benign FPR (deterministik, 20 seed ort. ± std)

| window_id | n_benign | FPR |
|---|---|---|
| window_02_3pct | 696 | 0.0430 +/- 0.0123 |
| window_03_5pct | 533 | 0.0291 +/- 0.0122 |
| window_04_7pct | 784 | 0.0291 +/- 0.0104 |
| window_05_12pct | 896 | 0.0472 +/- 0.0127 |
| window_06_15pct | 773 | 0.1000 +/- 0.0378 |
| window_07_17pct | 873 | 0.1146 +/- 0.0315 |
| window_08_22pct | 873 | 0.0408 +/- 0.0090 |
| window_resampled_15pct | 719 | 0.0477 +/- 0.0116 |
| window_resampled_20pct | 674 | 0.0534 +/- 0.0143 |

## 3. Benign gap'ler: ölçülen FPR vs kompozisyon-ağırlıklı FPR

Her gap'in FPR'si, içerdiği window'ların (tüm-window) FPR'lerinin
flow-sayısı-ağırlıklı ortalamasıyla yeniden kurulur. Eşleşme yaklaşıktır
(gap bir window'un bitişik ts-dilimini içerir, window FPR'si ise window'un
tamamından hesaplanır; window-içi zamansal varyasyon ≤~0.008'lik artıklar
bırakır) — ama gap'ler arası sıralama ve büyüklük birebir yeniden üretilir,
yani fark 'hangi gap hangi window'ları içeriyor' sorusuna indirgenir:

| segment_id | n | FPR (ölçülen) | FPR (kompozisyon-ağırlıklı) | kompozisyon |
|---|---|---|---|---|
| 0 | 1705 | 0.0321 | 0.0398 | window_02_3pct 41%, window_03_5pct 31%, window_resampled_20pct 12%, window_resampled_15pct 11%, window_04_7pct 5% |
| 2 | 1705 | 0.0361 | 0.0404 | window_04_7pct 41%, window_05_12pct 36%, window_resampled_15pct 11%, window_resampled_20pct 11% |
| 4 | 1705 | 0.0933 | 0.0892 | window_06_15pct 45%, window_07_17pct 26%, window_05_12pct 16%, window_resampled_15pct 7%, window_resampled_20pct 5% |
| 6 | 1706 | 0.0694 | 0.0615 | window_08_22pct 51%, window_07_17pct 25%, window_resampled_15pct 13%, window_resampled_20pct 11% |

## Yorum

Window'lar arası benign FPR 0.0291–0.1146 aralığında — gap'ler arası
farkın tamamını üretecek genişlikte. n≈1705'lik bir gap'te FPR≈0.05'in binom
std'si ~0.005'tir; gözlenen 0.032→0.093 farkı örnekleme gürültüsüyle açıklanamaz.
Deterministik z_mean skoru skorlama gürültüsünü tamamen kaldırdığı hâlde desenin
aynen korunması da (bkz. `../../deterministic_vs_stochastic_comparison.md`) aynı
sonucu bağımsız olarak doğrular: **fark sistematiktir ve ts-sıralı bölünmenin
yarattığı window kompozisyonundan gelir; model 'drift' etmiyor, örneklem
gürültüsü de değil.**
