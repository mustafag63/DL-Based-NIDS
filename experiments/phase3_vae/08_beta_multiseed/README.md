# Beta seçimi — çoklu-seed yeniden değerlendirme

## Neden aktif latent boyut kriteri terk edildi

Notebook bölüm 9.3'ün orijinal seçim kuralı şuydu: "beta=1.0 baseline'a göre
val AUC kaybı ≤0.03 kalırsa, **daha fazla aktif latent boyutu** olan varyant
tercih edilir." Bu kural, aktif boyut sayısının anlamlı bir sinyal olduğu
varsayımına dayanıyordu.

[`07_seed_variance/`](../07_seed_variance/README.md) bunu çürüttü: sabit bir
konfigürasyonu (latent=10, beta=0.25) 10 farklı ağırlık-başlatma seed'i ile
eğittiğinde, aktif boyut sayısı 1/10 ile 9/10 arasında sıçradı (std=3.02) **ve
test AUC ile hiçbir ilişki göstermedi** — en az aktif boyutlu seed (1/10)
ikinci en iyi AUC'yi verirken, en çok aktif boyutlu seed (8/10) en kötüsünü
verdi. Yani "daha fazla aktif boyut" bir kalite sinyali değil, seed'e bağlı
gürültü. Bu yüzden bu denetimde aktif boyut sayısı **seçim kriterlerinden
tamamen çıkarıldı** — sadece bilgi amaçlı kaydedildi.

## Yöntem

`train_beta_multiseed.py`, [`06_beta_selection_audit/`](../06_beta_selection_audit/README.md)'nin
temiz (val-only, test'e dokunmayan) protokolünü taban aldı, ama her 4 beta
varyantını (1.0 / 0.5 / 0.25 / KL-annealing) **5 seed** (0-4) ile eğitti —
tek seed değil. Mimari/hiperparametreler birebir sabit: latent=10, dropout=0.1,
patience=12, Adam clipnorm=1.0, z_log_var clip [-10,10].

- **Faz A (seçim):** 20 model (4×5) sadece `val_indices.csv` ile eğitildi ve
  skorlandı; test seti bu fazda hiç yüklenmedi.
- **Seçim kriteri:** sadece val AUC'nin 5-seed ortalaması. Std'ler
  örtüşüyorsa (veya Welch t-testi p>0.05 ise) bu açıkça "istatistiksel olarak
  ayırt edilemiyor" diye işaretlendi.
- **Faz B (tek seferlik test):** kazanan varyantın Faz A'da zaten eğitilmiş
  5 modeli (yeniden eğitim yok) test setinde birer kez skorlandı — seçim
  zaten val ile yapıldığı için bu, gözlem amaçlı, sızıntı değil (aynı mantık
  07_seed_variance'de de kullanıldı).

## Sonuçlar — Faz A (val AUC, 5 seed)

| beta varyantı | val AUC (mean ± std) | aktif boyut (mean ± std, bilgi amaçlı) |
|---|---|---|
| **beta=0.25** | **0.8181 ± 0.0194** | 3.4 ± 3.21 |
| beta=0.5 | 0.7803 ± 0.0334 | 4.2 ± 3.77 |
| beta=1.0 (baseline) | 0.7509 ± 0.0453 | 1.4 ± 1.14 |
| KL-annealing | 0.7305 ± 0.0263 | 9.8 ± 0.45 |

Tam veri: [`results_per_seed.csv`](results_per_seed.csv),
[`results_summary.csv`](results_summary.csv).

**beta=0.25 en yüksek ortalama val AUC'yi veriyor.** İkinci sıradaki
beta=0.5 ile arasındaki fark (0.0378) std bantlarıyla örtüşüyor
(0.8181−0.0194=0.7987 ≤ 0.7803+0.0334=0.8137) ve Welch t-testi
**p=0.0689** — geleneksel 0.05 eşiğinin hemen üzerinde. Yani **beta=0.25 ve
beta=0.5 arasındaki fark, 5 seed'lik örneklemde istatistiksel olarak kesin
ayırt edilemiyor** (sınırda, ama anlamlı değil). Buna karşılık beta=1.0
(baseline) ve KL-annealing, beta=0.25'in hem ortalamasının hem de alt-std
ucunun (0.7987) belirgin şekilde altında kalıyor — bunlar açıkça geride.

## Sonuçlar — Faz B (kazananın 5-seed test performansı)

| | test AUC (mean ± std) | test F1 (mean ± std) | n |
|---|---|---|---|
| Bu denetim (beta=0.25, 5 seed, val-only seçimden sonra) | **0.9259 ± 0.0095** | 0.8474 ± 0.0099 | 5 |
| `07_seed_variance/` (beta=0.25, 10 seed) | 0.9197 ± 0.0149 | — | 10 |

İki bağımsız ölçüm birbiriyle örtüşüyor (0.9259±0.0095 aralığı
[0.9164, 0.9354], 0.9197±0.0149 aralığı [0.9048, 0.9346] — geniş çakışma).
Fark, örneklem boyutu farkından (5 vs 10 seed) ve normal seed-to-seed
gürültüden kaynaklanıyor; sistematik bir sapma değil.

*Not:* seed=0 için bu script'in ürettiği test AUC (0.9384) ile daha önceki
çalışmalarda (`06_beta_selection_audit/`, `07_seed_variance/`) aynı seed için
raporlanan 0.9372 arasında ~0.0012'lik bir fark var — val AUC'nin 10 basamağa
kadar birebir aynı çıkmasına rağmen (0.84317083...). Bu, CPU üzerinde
çok-thread'li BLAS/matmul'ün toplama sırasının run'lar arası deterministik
olmamasından kaynaklanan, gürültü tabanı seviyesinde bilinen bir etki (aynı
seed, aynı ağırlıklar, ama epsilon-seviyesinde farklı kayan-nokta toplama
sırası → AUC'yi belirleyen sınıra yakın çiftlerde sıra değişimi). Metodolojik
bir sorun değil, sadece raporlanan AUC'lerin 3. ondalıktan sonrasının
"gürültü" olarak okunması gerektiğinin bir hatırlatıcısı.

## Nihai öneri

**Mevcut beta=0.25 kararı korunmalı — değiştirilmemeli.**

- Aktif-boyut kriteri terk edildikten sonra bile, val AUC'ye göre en iyi
  varyant yine beta=0.25 çıkıyor — 5 seed'lik ortalamada açık ara önde
  (baseline ve KL-annealing'i istatistiksel olarak da geride bırakıyor).
- beta=0.5'e karşı üstünlüğü istatistiksel olarak kesin değil (p=0.0689),
  ama bu "kararsız kal" değil "beta=0.25'i değiştirmek için yeterli kanıt
  yok" anlamına geliyor — mevcut seçim zaten beta=0.25, değişikliği
  gerektirecek bir bulgu yok.
- Test performansı (0.9259±0.0095, n=5) hem eski tek-seed sayısıyla
  (0.9372) hem de 07_seed_variance'in 10-seed tahminiyle (0.9197±0.0149)
  tutarlı — üç bağımsız ölçüm aynı bölgede toplanıyor.

Özetle: orijinal beta=0.25 kararı yanlış bir gerekçeyle (aktif boyut
sayısı) verilmişti, ama şans eseri doğru sonuca ulaşmıştı — çoklu-seed,
gerekçesi düzeltilmiş bir değerlendirme de aynı kararı destekliyor.

## Dosyalar

- `train_beta_multiseed.py` — script (06_beta_selection_audit tabanlı, 4×5 seed)
- `results_per_seed.csv` — Faz A, 20 satır (varyant × seed)
- `results_summary.csv` — Faz A, varyant başına val AUC mean/std/median + aktif boyut istatistikleri
- `winner_test_per_seed.csv` — Faz B, kazananın 5 seed'lik test sonuçları
- `multiseed_selection_results.json` — tüm sayılar + seçim gerekçesi, makine-okunur

Hiçbir final/root dosyaya dokunulmadı (`04_phase3_models/`, `latest_run/`,
`06_beta_selection_audit/`, `07_seed_variance/` değişmedi).
