# Phase 3 (VAE) — Contamination Sweep

Faz 3 VAE'nin (latent=10, beta=0.25, `phase3_vae/04_phase3_models/vae_encoder_final.keras`
+ `vae_decoder_final.keras` ile aynı mimari) train setindeki kontaminasyon
oranına (kaza eseri train'e karışmış attack flow oranı) ne kadar duyarlı
olduğunu ölçen deney. Nkashama ve ark. (2024), *"Deep Learning for Network
Anomaly Detection under Data Contamination"* makalesindeki leakage-free
protokolün küçük ölçekli bir uyarlaması: 0/1/2/4/8/12% kontaminasyon
seviyelerinde ayrı ayrı VAE eğitilip hepsi **tek bir sabit test setinde**
değerlendirildi, amaç tek bir "temiz vs kirli" karşılaştırması değil,
performans-vs-kontaminasyon eğrisi.

Bu klasör `phase3_vae/`'nin mevcut baseline'ına (window_10 train, scaler,
final mimari) dokunmadan paralel bir deney olarak kuruldu.

## Metodoloji

**Flow-level ayrıklık.** Her flow `window_id::uid` (Zeek'in kendi bağlantı
kimliği, pencere içinde benzersizliği doğrulandı) ile tekilleştirildi. Dört
küme — attack pool, sabit test-attack seti, benign train havuzu, benign
threshold-val, benign test — birbirinden flow bazında tamamen ayrık; bu
`prepare_contamination_data.py` içinde assert'lerle kod seviyesinde
doğrulanıyor (bkz. "All leakage sanity-checks passed" log satırı).

**Scaler.** Ayrı bir `scaler.pkl` yok — proje genelinde zaten böyle bir
dosya hiç üretilmemiş. Mevcut desen (`phase3_vae/prepare_window10.py`)
korunarak StandardScaler + OneHotEncoder, Dense fazının
`train_indices.csv`'sinden **read-only refit** edildi (bu deneyin kendi
verisi üzerinde asla fit edilmedi) — böylece tüm flow'lar final VAE ile
aynı ölçekte.

**Veri kaynakları.**
- Attack pool: `window_02` – `window_08` (7 pencere, 3078 attacker-IP flow'u
  hariç toplam 3870 attack-labelled flow). **`window_09` ham veri
  yedeğinde hiç yok** — sadece `window_01`–`08` ve `window_10_0pct`
  yakalanmış; talimat bu ihtimali zaten öngörmüştü, deney window_02-08
  ile kuruldu.
- Benign havuzu: `window_10_0pct` (4356 benign flow, kendi içindeki ~%0.18
  attacker-IP kalıntısı hariç tutuldu — `prepare_window10.py`'daki ile
  aynı kural).

**3 yönlü benign split** (70/15/15, seed=42): train_pool=3049,
threshold-val=653, test=654.

**Attack split**: test_attack_set=73 (sabit test setinin ~%10 hedef
kontaminasyonuna denk), attack_pool=3797 (train enjeksiyonu için, seviyeler
arası bağımsız örneklendi — farklı seviyelerin train dosyaları birbirinden
örneklem olarak ayrık olmak zorunda değil, sadece attack_pool ile
test_attack_set arasında hiç kesişim olmaması garanti edildi).

**Sabit test seti**: 727 flow (654 benign + 73 attack, **%10.04**
kontaminasyon) — tüm 30 model bu aynı sette değerlendirildi.

**Kontamine train setleri**: her seviyede benign train havuzu (3049)
sabit tutulup sadece attack sayısı değişti — kontaminasyonu tek değişken
olarak izole etmek için:

| Hedef | Gerçek | benign | attack | toplam |
|---|---|---|---|---|
| 0% | 0.000% | 3049 | 0 | 3049 |
| 1% | 1.006% | 3049 | 31 | 3080 |
| 2% | 1.993% | 3049 | 62 | 3111 |
| 4% | 3.999% | 3049 | 127 | 3176 |
| 8% | 7.996% | 3049 | 265 | 3314 |
| 12% | 12.006% | 3049 | 416 | 3465 |

**Model / eğitim.** Mimari `phase3_vae_autoencoder.ipynb` bölüm 9'daki
final `VAE` sınıfıyla birebir aynı: `18 -> Dense(16, relu) -> Dropout(0.1)
-> Dense(8, relu) -> [z_mean(10), z_log_var(10)]` encoder (log-var
[-10, 10] clip'li), simetrik decoder, `beta=0.25` (sabit, anneal yok),
`Adam(clipnorm=1.0)`, `EarlyStopping(monitor=val_loss, patience=12,
restore_best_weights=True)`, batch=64, max epoch=200. Eğitim tamamen
unsupervised — attack flow'lar train setine karışsa bile modele hangi
flow'un attack olduğu hiç verilmedi, etiket sadece sonradan
değerlendirmede kullanıldı. Her kontaminasyon seviyesinde 5 farklı
weight-init seed (0-4) — 6×5 = 30 model, `04_models/contam_{X}pct/seed_{N}/`.

**Threshold.** Train'e değil, ayrı bir held-out benign validation split'ine
(653 flow, ne train'de ne test'te) göre, her modelin kendi reconstruction-error
dağılımının 95. ve 99. percentile'ı — `threshold.json`. Aynı set,
`EarlyStopping`'in `val_loss` monitörü için de kullanıldı (matches Dense/VAE
convention).

**Değerlendirme.** Her (seviye, seed) modeli sabit test setinde çalıştırıldı;
PR-AUC/ROC-AUC (threshold-free) ile F1/F2/benign-FPR/attack-recall
(threshold_95 ile) hesaplandı — `evaluate_contamination_sweep.py`,
`05_results/results_per_seed.csv` ve `results_summary.csv`.

### Karşılaşılan bir Keras kütüphane hatası (workaround uygulandı)

Kaydedilmiş `encoder.keras`/`decoder.keras` dosyaları yeni bir process'te
`safe_mode=False` ile yüklenirken, log-var clip'ini yapan `Lambda`
katmanının kapatması (`tf.clip_by_value`) `NameError: name 'tf' is not
defined` ile patlıyor — Keras'ın `Lambda.from_config` → `func_load`
zinciri, kapanan fonksiyonu **kendi `python_utils` modülünün globals'ı**
ile yeniden kuruyor, ki bu modül `tensorflow`'u hiç import etmiyor. Bu proje
geneline özgü bir sorun değil, bu Keras sürümünün Lambda deserialization
davranışı — **mevcut `vae_encoder_final.keras` da bağımsız olarak test
edildiğinde aynı hatayı veriyor** (bkz. `phase3_vae/README.md`'deki "does
not run standalone" uyarısı; sorun sanıldığından daha derin). Workaround:
`evaluate_contamination_sweep.py` model yüklemeden önce
`keras.src.utils.python_utils.tf = tf` ile bu modülün namespace'ine
`tf`'i enjekte ediyor — dosyaları değiştirmiyor, sadece deserialization
sırasında eksik ismi tamamlıyor.

## Sonuçlar

> **Not (2026-07-23): bu bölümdeki tablolar ve "Yorum" 5 seed'e dayanıyor,
> ARTIK GÜNCEL DEĞİL.** Tüm 6 seviye sonradan 20 seed'e çıkarıldı (bkz.
> "Orijinal 6 seviyenin de 20 seed'e çıkarılması + istatistiksel anlamlılık
> testi" bölümü, dosyanın sonuna doğru) — özellikle **%12'nin burada
> "%8'den daha iyi/toparlanma" olarak yorumlanması yanlış çıktı** (20
> seed'de %12 mean'i %8'inkinden düşük), ve %8/%12'de görülen tekil
> "kötü seed" aslında %8 ve üstünde her seviyede tekrarlanan sistematik bir
> bimodalite. Bu bölüm sadece izlenebilirlik için, ilk analiz sürecini
> göstermek amacıyla korunuyor; güncel sonuç ve yorum için dosyanın sonundaki
> bölüme bakın.

5-seed mean ± std, sabit test setinde (ESKİ, bkz. yukarıdaki not):

| Contam. | PR-AUC | ROC-AUC | F1 (thr95) | Benign FPR (thr95) | Attack Recall (thr95) |
|---|---|---|---|---|---|
| 0% | 0.718 ± 0.004 | 0.862 ± 0.013 | 0.642 ± 0.017 | 0.041 ± 0.006 | 0.644 ± 0.000 |
| 1% | 0.701 ± 0.016 | 0.818 ± 0.042 | 0.649 ± 0.024 | 0.039 ± 0.010 | 0.649 ± 0.012 |
| 2% | 0.694 ± 0.008 | 0.842 ± 0.011 | 0.630 ± 0.010 | 0.045 ± 0.003 | 0.644 ± 0.000 |
| 4% | 0.659 ± 0.044 | 0.801 ± 0.036 | 0.638 ± 0.031 | 0.039 ± 0.009 | 0.630 ± 0.019 |
| 8% | 0.641 ± 0.092 | 0.775 ± 0.036 | 0.617 ± 0.085 | 0.038 ± 0.005 | 0.600 ± 0.098 |
| 12% | 0.683 ± 0.022 | 0.805 ± 0.019 | 0.626 ± 0.014 | 0.046 ± 0.005 | 0.641 ± 0.006 |

5 seed gibi küçük bir örneklemde tek bir uçuk değer ortalamayı kolayca
çarpıtabildiği için (bkz. Yorum), `results_summary.csv` mean/std'nin
yanında **median** ve **trimmed mean** (en düşük + en yüksek değer atılıp
kalan 3 seed'in ortalaması, `scipy.stats.trim_mean(proportiontocut=0.2)`)
sütunlarını da içeriyor. PR-AUC için bu üç istatistik yan yana:

| Contam. | mean | std | median | trimmed_mean (orta 3 seed) |
|---|---|---|---|---|
| 0% | 0.718 | 0.004 | 0.719 | 0.718 |
| 1% | 0.701 | 0.016 | 0.693 | 0.700 |
| 2% | 0.694 | 0.008 | 0.697 | 0.695 |
| 4% | 0.659 | 0.044 | 0.660 | 0.670 |
| 8% | 0.641 | 0.092 | 0.675 | 0.676 |
| 12% | 0.683 | 0.022 | 0.680 | 0.685 |

Tam sayılar: `05_results/results_per_seed.csv` (30 satır), `results_summary.csv`.
Eğri: `05_results/contamination_curve.png` (PR-AUC, F1, benign FPR, attack
recall — mean çizgi + std gölgeli bant; şu an mean üzerinden çizili, yukarıdaki
outlier nedeniyle %8 noktasını okurken median/trimmed_mean sütunlarına bakmak
daha güvenilir).

### Yorum

- **%0 → %4 arası düzenli bir bozulma var**: PR-AUC 0.718'den ~0.66-0.67'ye
  (mean 0.659, trimmed 0.670), ROC-AUC 0.862'den 0.801'e düşüyor. Bu,
  Nkashama'nın temel bulgusuyla tutarlı — unsupervised bir
  reconstruction-error modeli, train setine karışan attack flow'ları da
  "normal" olarak öğrenmeye başlıyor, reconstruction error dağılımı benign
  ve attack için birbirine yaklaşıyor.
- **%8 outlier'ı doğrulandı ve teşhis edildi: `contamination=8%, seed=1`.**
  Ham PR-AUC'lar (`results_per_seed.csv`'den): seed 0/2/3/4 = 0.675 / 0.675 /
  0.679 / 0.699 (aralık 0.024), seed 1 = **0.478** — tek başına diğer
  dördünün ~0.2 puan altında (F1'de de aynı: 0.466 vs 0.64-0.67 bandı).
  Bu tek nokta 5-seed mean'i (0.641) ve std'sini (0.092, diğer seviyelerin
  4-20 katı) fena halde çarpıtıyor; median (0.675) ve trimmed mean (0.676)
  outlier'ı devre dışı bırakınca %8'i %12'ye (0.680/0.685) çok yakın bir
  yere koyuyor.
  **Kök neden araştırması:** posterior collapse şüphesiyle (aktif latent
  boyut sayısı, `z_mean` std > 0.15 eşiği, health-check'teki yöntemle)
  kontrol edildi — seed=1'in **9/10 boyutu aktif** (collapse yok, epochs=77,
  val_loss=3.73), üstelik aynı seviyedeki seed=4 çok daha az aktif boyuta
  sahip olduğu halde (3/10, epochs=13, val_loss=12.6 — gerçek bir kararsız
  koşu belirtisi) PR-AUC'u normal (0.699). Yani **collapse, düşük PR-AUC'un
  açıklaması değil** — seed=1'in çöküşü sıradan seed-to-seed eğitim
  varyansına bağlanıyor, latent-boyut patolojisiyle ilişkilendirilemedi.
  Bu deneyde kullanıcı onayıyla ek seed eğitilmeden mevcut haliyle
  raporlandı.
- **Median/trimmed mean ile düzeltilmiş resim**: 0-2% civarında ~0.70-0.72,
  sonra 4-12% aralığında ~0.66-0.685 bandında bir platoya oturuyor — outlier
  hariç bakıldığında bile 4%→8%→12% arası **kesin monoton bir düşüş değil**,
  keskin bir ilk düşüşten (%0→%4) sonra bir plato/gürültü bandı olarak
  okunmalı. 5 seed, bu platonun ince yapısını (örn. 8% gerçekten mi 12%'den
  biraz düşük) güvenilir ayırt etmek için yeterli değil.
- **Benign FPR** kontaminasyon boyunca nispeten stabil (~%3.8-4.6) —
  threshold_95'in her modelin *kendi* validation error dağılımına göre
  kalibre edilmesi, artan reconstruction error'a rağmen benign false-alarm
  oranını büyük ölçüde koruyor (thresholds kendisi de kontaminasyonla
  birlikte büyüyor: bkz. `04_models/*/seed_*/threshold.json` — thr95
  %0'da ~0.11-0.15 iken %12'de ~0.37-1.27'ye çıkıyor).
- **Attack recall** aynı sebeple daha oynak: model daha "toleranslı" hale
  geldikçe (threshold büyüdükçe) gerçek attack'ları da kaçırmaya başlıyor,
  ama %8 seviyesindeki gürültü (yukarıdaki tek kötü seed) bu metrikte de
  en büyük varyansı yaratıyor (std=0.098, diğer seviyelerin ~10 katı).
- **Sabit test setindeki attack sayısı sadece 73 flow.** Bu, `attack_recall`
  metriğinin doğası gereği gürültülü olduğu anlamına geliyor — tek bir
  flow'un yanlış sınıflandırılması bile ~%1.4'lük bir sıçrama yaratıyor.
  5-seed std'sinin `attack_recall`'da diğer metriklere kıyasla daha geniş
  çıkması (özellikle %8'de) kısmen bu küçük örneklem büyüklüğünün beklenen
  bir sonucu, sadece model instabilitesinin değil.

### Sınırlamalar / gelecek adımlar

- `window_09` capture'ı hiç alınmamış — attack pool 7 pencereyle (02-08)
  sınırlı kaldı; daha fazla pencere olsaydı özellikle %8/%12 seviyelerinde
  daha büyük/çeşitli bir attack_pool ile örnekleme varyansı azaltılabilirdi.
- Dense'in split'i signature_id bazlı `GroupShuffleSplit` kullanıyor
  (aynı saldırı-dizisinin train/val/test arasında sızmaması için); bu
  deneyde flow-level tekilleştirme yeterli görüldü (talimatta böyle
  istendi), signature-level gruplama uygulanmadı — aynı attack
  "burst"ünden birden fazla flow'un train ve test'e ayrı ayrı düşmüş
  olması mümkün, Dense'in korumasına sahip değil.
- 5 seed, özellikle yüksek kontaminasyon seviyelerinde (8-12%) varyansı
  güvenilir ölçmek için az kalabilir — %8'deki tek dengesiz koşu bunun
  somut bir örneği.

## Genişletme: ~%15 ve ~%20 seviyeleri (resampled window'lar)

2026-07-22 16:00-18:00 Pi/Zeek capture kesintisi nedeniyle kaybolan
pencerelerin yerine `build_synthetic_window.py` ile üretilen
`window_resampled_15pct` (actual_attack_pct=%14.999, n=4967) ve
`window_resampled_20pct` (actual_attack_pct=%19.992, n=4967) kullanılarak
sweep iki yeni kontaminasyon seviyesiyle genişletildi. Orijinal 0/1/2/4/8/12%
seviyelerine (`01_data/`, `02_contaminated_train_sets/train_contam_{0,1,2,4,8,12}pct.csv`,
`04_models/contam_{0,1,2,4,8,12}pct/`, `05_results/results_per_seed.csv`'nin
ilk 30 satırı) **dokunulmadı** — bu 30 satırın deney öncesi/sonrası byte-bit
aynı kaldığı doğrulandı.

**Protokol farkı (bilinçli):** orijinal 6 seviyede sabit `benign_train_pool`
(3049, window_10'dan) üstüne `attack_pool`'dan (window_02-08) örneklenen
attack flow'lar ekleniyordu. Bu iki yeni seviyede ise train set doğrudan
resampled window'un **kendi** conn.log'undan (benign+attack birlikte, doğal
~%15/%20 kontaminasyonla) üretildi — `prepare_contamination_data_extended.py`.
Geri kalan her şey (VAE mimarisi, hyperparametreler, 5 seed, held-out benign
val split'inden threshold hesaplama, sabit test seti) birebir aynı protokol.

**Kritik leakage kontrolü:** `build_synthetic_window.py`, resampled
window'ların benign/attack satırlarını `window_01,02,03,04,05,07,08`'den
havuzluyor — bu, sabit test setinin `test_attack_set`'inin geldiği
`window_02-08` ile örtüşüyor. Orijinal `flow_id = window_id::uid` tabanlı
disjointness assert'i bunu **yakalayamazdı**, çünkü resampled window'daki her
flow'a `load_window()` tarafından atanan `window_id` kaynak pencerenin değil,
`"window_resampled_15pct"` gibi resampled etiketin kendisi — string eşleşmesi
hiç oluşmuyor. Gerçek sinyal, satırın Zeek `uid`'inin kendisi (kaynaktan
bit-bit kopyalandığı için, `_dupN` soneki hariç). `prepare_contamination_data_extended.py`
bu çıplak uid'i sabit test setinin tüm uid'leriyle karşılaştırdı:

| Seviye | Kaynak window | Leak (satır) | Leak (attack) | Filtre öncesi n | Filtre sonrası n | Filtre sonrası gerçek % |
|---|---|---|---|---|---|---|
| ~15% | window_resampled_15pct | 20 | 20 | 4899 | 4879 | 14.327% |
| ~20% | window_resampled_20pct | 15 | 15 | 4891 | 4876 | 19.299% |

Yani gerçekten de test setiyle çakışan flow'lar vardı (hepsi attack tarafında,
beklenen gibi — benign satırlar window_10'dan geldiği için hiç çakışmadı);
bu satırlar sadece train'den çıkarıldı, test seti hiç değiştirilmedi
(`assert not (bare_uid ∩ test_uids)` her seviye sonrası tekrar doğrulandı).

**Eğitim:** `train_contamination_sweep_extended.py`, aynı `VAE` sınıfı
(latent=10, beta=0.25, Dense(16)→Dropout(0.1)→Dense(8)→[z_mean,z_log_var](10),
Adam clipnorm=1.0, EarlyStopping val_loss patience=12), aynı held-out
`val_benign.csv` — 2×5 = 10 yeni model, `04_models/contam_{15,20}pct/seed_{0-4}/`.

**Değerlendirme:** `evaluate_contamination_sweep_extended.py`, aynı sabit
test setinde (727 flow, değişmedi), sonuçları `results_per_seed.csv`'ye
**append** etti (orijinal 30 satır korunarak, 40 satıra çıktı),
`results_summary.csv` ve `contamination_curve.png` tüm 8 seviye
(0/1/2/4/8/12/15/20%) üzerinden yeniden hesaplandı.

### Genişletilmiş sonuçlar

5-seed mean, sabit test setinde:

| Contam. | PR-AUC mean | PR-AUC median | PR-AUC trimmed | ROC-AUC mean | F1 mean | Benign FPR mean | Attack Recall mean |
|---|---|---|---|---|---|---|---|
| 0% | 0.718 | 0.719 | 0.718 | 0.862 | 0.642 | 0.041 | 0.644 |
| 1% | 0.701 | 0.693 | 0.700 | 0.818 | 0.649 | 0.039 | 0.649 |
| 2% | 0.694 | 0.697 | 0.695 | 0.842 | 0.630 | 0.045 | 0.644 |
| 4% | 0.659 | 0.660 | 0.670 | 0.801 | 0.638 | 0.039 | 0.630 |
| 8% | 0.641 | 0.675 | 0.676 | 0.775 | 0.617 | 0.038 | 0.600 |
| 12% | 0.683 | 0.680 | 0.685 | 0.805 | 0.626 | 0.046 | 0.641 |
| **~15%** | **0.659** | **0.666** | **0.675** | **0.798** | **0.601** | **0.041** | **0.595** |
| **~20%** | **0.688** | **0.698** | **0.692** | **0.817** | **0.640** | **0.040** | **0.638** |

(15% seed=3 tek başına düşük çıktı — PR-AUC=0.545 vs diğer 4 seed'in
0.657-0.725 bandı, ~%8'deki tek-seed instabilite deseniyle tutarlı; median/
trimmed_mean bunu da kısmen düzeltiyor.)

### Yorum: %12 sonrası trend gerçek mi, clean-only hâlâ optimal mi?

- **Clean-only (%0) hâlâ açık ara en iyi**, hem PR-AUC (0.718) hem ROC-AUC
  (0.862) hem trimmed_mean (0.718) ile tüm diğer 7 kontaminasyon seviyesini
  geçiyor — %15/%20 eklenmesi bu sonucu değiştirmiyor.
- **%12'den sonra "toparlanma" var ama bu %0-2 seviyesine dönüş değil**:
  PR-AUC %8'de 0.641 (median 0.675) → %12'de 0.683 → %15'te 0.659 → %20'de
  0.688. Yani %12→%15→%20 arası **monoton değil**, ~0.66-0.69 bandında
  gürültülü bir platoda geziniyor — %4-%20 aralığının tamamı kabaca aynı
  plato (~0.64-0.69 PR-AUC, ~0.78-0.82 ROC-AUC), %0-2'nin (~0.70-0.72 /
  ~0.82-0.86) belirgin şekilde altında.
- **Sonuç: %12 sonrası gözlemlenen artış gerçek bir "daha fazla
  kontaminasyon daha iyi" trendi değil**, sadece platonun kendi
  gürültü bandı içinde bir nokta — 5 seed ile bu ince farkları (%8 vs %12
  vs %15 vs %20 arası sıralama) güvenilir şekilde ayırt etmek mümkün değil.
  Bu, orijinal 6 seviyelik sweep'in zaten vardığı "%0→%4 keskin düşüş,
  sonrası plato/gürültü" yorumunu değiştirmeden **doğruluyor ve genişletiyor**
  — plato artık %4'ten %20'ye kadar uzanıyor.
- **Metodolojik not**: %15/%20 train setleri artık sabit `benign_train_pool`
  üstüne enjeksiyon değil, kendi başına farklı bir örneklem (resampled
  window'un doğal karışımı) — yani bu iki nokta, diğer 6 noktayla birebir
  aynı "tek değişkenli" kontrolü paylaşmıyor (benign tarafı da farklı flow'lar
  içeriyor, window_10 dışından). Eğrideki %12→%15/%20 karşılaştırması bu
  yüzden hâlâ bilgilendirici ama "sadece kontaminasyon oranı değişti, her şey
  sabit" garantisi sadece 0-12% aralığı için geçerli.

## Exploratory / with-replacement deneme (%22/%25/%28/%30) — ana bulguya DAHİL EDİLMEDİ

Bir önceki genişletme turunda aynı `build_synthetic_window.py` mantığıyla 4
seviye daha eklenmişti: `window_resampled_{22,25,28,30}pct`, hepsi
`n_total=4967`, `seed=42`. Attack havuzu toplam 3,279 flow (window_01-08'den,
window_06 hariç); bu 4 seviyenin toplam ihtiyacı (1093+1242+1391+1490=5,216)
havuzu aştığı için `build_synthetic_window.py` **attack tarafında
with-replacement**'a düştü (benign tarafı without-replacement kaldı,
tekrarlanan satırlar `_dupN` ile işaretlendi). Bu 4 seviye başlangıçta ana
sweep'e dahil edilip 12 noktalı bir "U şekli" gözlemlenmişti — çukurdan
(%4-%15, PR-AUC ~0.64-0.66) sonra %19-30 aralığında düzenli bir toparlanma
(%27'de PR-AUC 0.714, %0'ın 0.718'ine çok yakın).

**Bu sonuç artık ana bulguya dahil değil — with-replacement'ın kendisi
muhtemel bir konfaunt (artefakt riski) olarak değerlendirildi**: aynı
attack flow'ların defalarca tekrarlanması (%28-30'da satırların
%0.5-0.8'i `_dup`), modelin gerçek bir "yüksek kontaminasyona dayanıklılık"
yerine, tekrarlayan/dar bir attack deseni öğrenmesinin yapay bir yan etkisi
olabilir. Bunu without-replacement bir kontrol noktasıyla (aşağıdaki
%22-clean) doğrulamadan ana eğriye karıştırmak yanıltıcı olurdu.

**Bu deneyle ilgili tüm dosyalar `exploratory_with_replacement/` altına
taşındı** (silinmedi, iz kalsın diye):
- `exploratory_with_replacement/02_contaminated_train_sets/train_contam_{22,25,28,30}pct.csv`
- `exploratory_with_replacement/04_models/contam_{22,25,28,30}pct/` (20 model)
- `exploratory_with_replacement/04_models/training_run_log_with_replacement.json`
- `exploratory_with_replacement/05_results/results_per_seed_with_replacement.csv` (20 satır)

`05_results/results_per_seed.csv`, `results_summary.csv` ve
`contamination_curve.png`'den bu 4 seviyenin satırları/noktaları çıkarıldı —
ana sweep artık bunları hiç içermiyor. `window_resampled_{22,25,28,30}pct`
ham conn.log'ları (`~/Desktop/NIDS/data/ids-dataset-raw-backup/` altında)
referans için yerinde bırakıldı, silinmedi.

## Üçüncü genişletme: ~%22 (clean, tam without-replacement)

With-replacement artefakt şüphesini test etmek için, **sadece %22** hedefi
**tam without-replacement** olarak `build_window_22pct_clean.py` ile yeniden
üretildi (`window_resampled_22pct_clean`, eski with-replacement
`window_resampled_22pct`'ten tamamen ayrı bir dosya/etiket).

**Havuz muhasebesi (adım 1, kesin sayılarla doğrulandı):** `window_resampled_15pct`
ve `window_resampled_20pct`'in without-replacement çekimi toplam
745 + 993 = **1,738** attack flow kullanmıştı (uid bazlı tam liste
çıkarıldı, `_dup` yok — ikisi de zaten without-replacement'tı). Bu, 3,279
flow'luk toplam havuzdan düşülünce **1,541 flow** hiç kullanılmamış temiz
bütçe olarak kaldı — tahmin edilen sayı script çalıştırılıp doğrulandı.
%22 hedefi `n_total=4967` ile **1,093** attack flow gerektiriyor, bu
1,541'e rahatça sığıyor (kalan pay 448).

`build_window_22pct_clean.py`:
1. Havuzu (window_01,02,03,04,05,07,08) yeniden okur.
2. `window_resampled_15pct`/`20pct`'in kullandığı **tüm** uid'leri (hem
   benign hem attack, 9,934 flow) havuzdan çıkarır.
3. Kalan temiz havuzdan (`attack=1541`, `benign=19930`) without-replacement
   örnekler (`benign_replacement=False`, `attack_replacement=False` —
   ikisi de assert ile doğrulandı).
4. Çekilen uid'lerin 15pct/20pct'in kullandıklarıyla **hiç kesişmediğini**
   assert ile doğrular ve sonucu `window_meta.json`'a
   `disjoint_from` alanı olarak yazar; `generation_method` alanına literal
   `"resampled_without_replacement"` değeri, ayrıntılı açıklama ise
   `generation_method_description`'a taşındı.

**Leakage kontrolü (sabit test setiyle, uid bazlı):** `window_resampled_22pct_clean`'in
4884 lab-IP flow'undan (1054 attack) **18 satır** (hepsi attack) sabit test
setiyle uid çakıştığı için train'den elendi → 4866 flow (1036 attack),
gerçek kontaminasyon **%21.291**. Test seti yine hiç değiştirilmedi.

**Eğitim/değerlendirme:** `train_contamination_sweep_extended.py` ve
`evaluate_contamination_sweep_extended.py` artık sadece 15/20/22(clean)
seviyelerini kapsıyor — aynı VAE mimarisi (latent=10, beta=0.25), aynı 5
seed, aynı held-out threshold protokolü. Eski with-replacement
`contam_22pct` model klasörü zaten `exploratory_with_replacement/`'a
taşınmıştı, bu yüzden %22 sıfırdan, temiz train set'iyle eğitildi (eski
sonuçların üstüne yazılmadı, tamamen ayrı bir model seti). `results_per_seed.csv`
şu an 45 satır (orijinal 30 + 15/20/22-clean × 5 seed), orijinal 30 satır
byte-bit doğrulanarak değişmedi.

### Genişletilmiş sonuçlar (9 temiz nokta) — İLK SÜRÜM, 5 seed her yerde (ARTIK GEÇERSİZ, aşağıya bkz.)

Bu tablo ilk üretildiğinde (aşağıdaki "Seed genişletmesi" bölümünden önce)
14.33/19.30/21.29% de dahil tüm noktalar 5 seed'liydi ve %21.29'da PR-AUC
std'si **0.001** gibi çarpıcı derecede dar çıkmıştı — bu, "toparlanma
gerçek ve kararlı" yorumuna yol açmıştı. **Seed sayısı 20'ye çıkarılınca bu
dar std'nin bir 5-seed örnekleme tesadüfü olduğu ortaya çıktı** (aşağıdaki
bölüme bakın) — o yüzden bu ilk tablo ve yorumu burada **sadece izlenebilirlik
için** tutuluyor, güncel sonuç bir alt bölümde.

## Seed genişletmesi: 14.33/19.30/21.29% için 5→20 seed

`train_contamination_sweep_extended.py` ve `evaluate_..._extended.py`,
**sadece** bu üç resampled nokta için (`window_resampled_15pct`,
`window_resampled_20pct`, `window_resampled_22pct_clean`) seed 5-19'u
(mevcut 0-4'e ek, hiçbiri yeniden eğitilmeden/üzerine yazılmadan) eğitecek
şekilde genişletildi — orijinal 6 seviye (0/1/2/4/8/12%) ve bu 6 seviyenin
5-seed sonuçları **hiç dokunulmadı**. `results_summary.csv`'ye artık
**`n_seeds`** sütunu eklendi: 0/1/2/4/8/12% hâlâ `n_seeds=5`, 15/20/22%
artık `n_seeds=20` — bu iki grubun std'lerini doğrudan karşılaştırırken
**bu farkı göz önünde bulundurmak gerekiyor** (20-seed std tahmini daha
güvenilir/az gürültülü bir tahmin, ama farklı n ile karşılaştırma her
zaman dikkatli yapılmalı).

### Genişletilmiş sonuçlar (9 nokta, n_seeds karışık — bkz. sütun)

| Contam. | n_seeds | PR-AUC mean | PR-AUC median | PR-AUC trimmed | PR-AUC std | ROC-AUC mean | ROC-AUC std |
|---|---|---|---|---|---|---|---|
| 0% | 5 | 0.718 | 0.719 | 0.718 | 0.004 | 0.862 | 0.013 |
| 1% | 5 | 0.701 | 0.693 | 0.700 | 0.016 | 0.818 | 0.042 |
| 2% | 5 | 0.694 | 0.697 | 0.695 | 0.008 | 0.842 | 0.011 |
| 4% | 5 | 0.659 | 0.660 | 0.670 | 0.044 | 0.801 | 0.036 |
| 8% | 5 | 0.641 | 0.675 | 0.676 | 0.092 | 0.775 | 0.036 |
| 12% | 5 | 0.683 | 0.680 | 0.685 | 0.022 | 0.805 | 0.019 |
| **~14.33%** | **20** | **0.640** | **0.666** | **0.667** | **0.092** | **0.796** | **0.045** |
| **~19.30%** | **20** | **0.662** | **0.686** | **0.680** | **0.071** | **0.817** | **0.026** |
| **~21.29%** | **20** | **0.665** | **0.710** | **0.701** | **0.086** | **0.819** | **0.032** |

### Yorum: std daraldı mı, genişledi mi? (Kısa cevap: GENİŞLEDİ — beklenenin tersi)

- **Beklentinin tam tersi bir sonuç çıktı: 20 seed'e çıkınca std KÜÇÜLMEDİ,
  BÜYÜDÜ.** 14.33%: 0.069→**0.092** (%8 ile aynı seviyeye çıktı, sweep'in
  en gürültülü noktalarından biri oldu). 19.30%: 0.029→**0.071** (2.4x).
  21.29%: **0.001→0.086** — 86 kat büyüme, sweep'teki en dramatik değişim.
  Bunun nedeni azalan güven değil, tam tersi: **5 seed, gerçekte var olan
  değişkenliği yakalamaya yetmiyordu**, 20 seed daha doğru (ve daha kötü
  görünen) bir tahmin veriyor.
- **Kök neden: her üç noktada da tutarlı bir "kötü seed" kuyruğu var,
  20 seed'le görünür hale geldi.** PR-AUC'ları sıraladığımda (ham veri,
  `results_per_seed.csv`) her seviyede seed'lerin büyük çoğunluğu sıkı bir
  "iyi" kümede (~0.63-0.72) toplanırken, azınlık bir grup çok daha düşük
  bir "kötü" kümeye düşüyor (~0.40-0.55):
  - **14.33%**: 20 seed'in **3'ü** (seed 3, 5, 9) 0.40-0.55 bandında,
    kalan 17'si 0.60-0.73 bandında.
  - **19.30%**: 20 seed'in **2'si** (seed 6, 9) 0.45-0.49 bandında,
    kalan 18'i 0.64-0.72 bandında.
  - **21.29%**: 20 seed'in **4'ü** (seed 9, 13, 16, 18) 0.45-0.55
    bandında, kalan 16'sı 0.63-0.72 bandında (bunların çoğu sıkı bir
    şekilde 0.70-0.72'de).
  Yani gerçek dağılım yaklaşık **iki kümeli (bimodal)**: seed'lerin
  ~%80-85'i "iyi" bir çözüme, ~%15-20'si "kötü" bir çözüme yakınsıyor.
  Bu, orijinal sweep'in %8 noktasında görülen tek-seed instabilitesiyle
  (seed=1, PR-AUC=0.478, diğer 4 seed 0.68-0.70) aynı fenomenin daha büyük
  örneklemde daha net görünen hâli — o zaman 5 seed'de 1/5 (%20) kötü
  çıkmıştı, şimdi 20 seed'de de kabaca aynı oran (%10-20) kötü çıkıyor.
  **Muhtemel açıklama önceki bölümde zaten vardı** (posterior-collapse-
  benzeri değil, sıradan eğitim instabilitesi — bazı seed'ler kötü bir
  yerel optimuma/erken durma noktasına takılıyor) ama bunun her
  kontaminasyon seviyesinde ~%10-20 oranında **sistematik olarak
  tekrarlanan** bir oran olması yeni ve önemli bir gözlem.
- **%22'nin "0.001 std ile inanılmaz kararlı" iddiası GERİ ÇEKİLDİ.** İlk
  5 seed (0,1,2,3,4) tesadüfen hepsi "iyi" kümeye düşmüştü (0.709-0.713) —
  bu, %20 kötü-seed oranıyla 5 bağımsız denemenin hepsinin iyi kümeye
  düşme olasılığı ~0.8^5≈%33, yani "olağanüstü" değil, makul bir tesadüf.
  Bu, önceki turda "with-replacement artefaktı değil, gerçek ve kararlı
  bir toparlanma" sonucuna varırken **std'nin ana kanıt olarak kullanılmasının
  hatalı olduğunu** gösteriyor — küçük n ile düşük std, düşük gerçek
  varyansın değil, şanslı örneklemenin işareti olabiliyormuş.
- **Median/trimmed_mean nispeten stabil kaldı** (%22: median 0.712→0.710,
  trimmed 0.712→0.701) — bunlar zaten kötü-seed kuyruğuna karşı
  dayanıklı istatistikler, o yüzden 5→20 seed geçişinde beklenen kadar
  değişmediler. Yani **nokta tahmini** (medyan bazlı "toparlanma var mı"
  sorusu) hâlâ aynı yönde: %14.33/%19.30/%21.29 medyanları (0.666/0.686/
  0.710) sırayla artıyor ve çukurdaki 4-12% bandının (medyan 0.660-0.685)
  üstünde/yakınında — **medyan bazlı toparlanma sinyali hâlâ duruyor**,
  ama mean bazlı ve varyans bazlı güven çok zayıfladı.
- **Sonuç: toparlanma sinyali muhtemelen hâlâ gerçek (medyan/trimmed_mean
  tutarlı) ama "kararlı/gürültüsüz" iddiası yanlıştı.** Doğru resim:
  bu üç seviyede de model %10-20 ihtimalle kötü bir çözüme takılıyor
  (tıpkı %8'de olduğu gibi), geri kalan zamanda iyi bir çözüme yakınsıyor
  ve bu iyi-çözüm PR-AUC'u kontaminasyon arttıkça (14.33→19.30→21.29)
  kademeli yükseliyor gibi görünüyor. Bu iki ayrı olguyu (a) seed
  instabilitesinin kendisi ve (b) "iyi seed" performansındaki kontaminasyon-
  bağımlı trend, aynı ortalama içinde karışıyor — mean tek başına yanıltıcı,
  medyan/trimmed_mean + ham dağılıma bakmak gerekiyor.
- **Clean-only (%0) hâlâ tek en iyi nokta** (PR-AUC 0.718, std sadece
  0.004 — burada da düşük std var ama bu noktada henüz 20 seed'le test
  edilmedi, dolayısıyla %0'ın da benzer bir kötü-seed kuyruğu taşıyıp
  taşımadığı bilinmiyor — bu README'nin kapsamı dışında bırakıldı, ileride
  gerekirse ayrıca sorulmalı).
- **Sonraki adım için not (kullanıcının belirttiği %16/17/18 ara
  noktaları)**: bu bulgu göz önüne alınırsa, o noktalar için de en az
  ~15-20 seed düşünülmeli — 5 seed ile üretilecek bir nokta tahmini,
  burada görüldüğü gibi std'yi ciddi şekilde olduğundan düşük gösterebilir.

## Orijinal 6 seviyenin de 20 seed'e çıkarılması + istatistiksel anlamlılık testi (GÜNCEL, önceki 5-seed yorumları geçersiz kılar)

Yukarıdaki bimodalite bulgusu sadece resampled 3 noktada (14.33/19.30/
21.29%) gözlemlenmişti; orijinal 6 nokta (0/1/2/4/8/12%) hâlâ 5 seed'de
kalmıştı ve aynı fenomenin onlarda da olup olmadığı bilinmiyordu — özellikle
%8'de daha önce tek bir "kötü seed" (seed=1) zaten tespit edilmişti, bunun
izole bir olay mı yoksa sistematik bir kötü-seed oranı mı olduğu netleşmemişti.
`train_contamination_sweep_original_seedext.py` ve
`evaluate_contamination_sweep_original_seedext.py`, 0/1/2/4/8/12% için de
seed 5-19'u (mevcut 0-4'e ek, hiçbiri yeniden eğitilmeden/üzerine
yazılmadan) eğitip değerlendirdi — `results_per_seed.csv` artık **180 satır**
(9 seviye × 20 seed), **tüm 9 nokta artık eşit şekilde 20 seed'de**.

### Bimodalite orijinal noktalarda var mı? — Kısmen: sadece %8 ve üstünde

Her seviyede PR-AUC < 0.58 eşiğinin altına düşen seed sayısı (20 seed'in
kaçının "kötü kümeye" düştüğü):

| Contam. | n_seeds | kötü küme (PR-AUC<0.58) | kötü seed'lerin PR-AUC'ları |
|---|---|---|---|
| 0% | 20 | 0/20 | — |
| 1% | 20 | 0/20 | — |
| 2% | 20 | 0/20 | — |
| 4% | 20 | 0/20 | — |
| 8% | 20 | **4/20 (%20)** | 0.478, 0.551, 0.562, 0.566 |
| 12% | 20 | **4/20 (%20)** | 0.402, 0.469, 0.520, 0.550 |
| ~14.33% | 20 | 3/20 (%15) | 0.398, 0.401, 0.545 |
| ~19.30% | 20 | 2/20 (%10) | 0.451, 0.488 |
| ~21.29% | 20 | 4/20 (%20) | 0.451, 0.482, 0.540, 0.546 |

**Sonuç: bimodalite 0-4% aralığında yok (20 seed'in hepsi sıkı bir "iyi"
kümede, ~0.65-0.72), ama 8% ve üstündeki her seviyede var (~%10-20 oranında
kötü kümeye düşen seed).** Yani bu bir "resampled window'lara özgü" bir
artefakt değil — kontaminasyon oranı arttıkça VAE'nin eğitim kararlılığının
kendisi bozuluyor, bu instabilite ilk olarak %8 civarında ortaya çıkıyor ve
%22'ye kadar her seviyede benzer oranda devam ediyor. %8'de daha önce
raporlanan tek "outlier" seed (seed=1, PR-AUC=0.478) aslında bu sistematik
fenomenin 5-seed örneklemede görülen ilk işaretiymiş — izole bir olay değil.

### %12 gerçekten yüksek mi, yoksa 5 şanslı seed miydi? — Şans. %12 özel değil.

Eski 5-seed sonucunda %12 (mean 0.683) %8'den (mean 0.641) belirgin şekilde
yüksek görünüyordu ve bu "toparlanma" olarak yorumlanmıştı. 20 seed'e
çıkınca tablo tamamen değişti:

| Contam. | mean (5 seed, eski) | mean (20 seed, yeni) | median (20 seed) |
|---|---|---|---|
| 8% | 0.641 | **0.639** | 0.667 |
| 12% | 0.683 | **0.634** | 0.665 |

**%12'nin 20-seed mean'i (0.634) artık %8'inkinden (0.639) bile düşük** —
eski 5-seed'lik %12 örneklemi (seed 0-4), şansla, kötü kümeye hiç
düşmemiş 5 iyi seed'i yakalamıştı (bu, %20 kötü-seed oranıyla 5 bağımsız
denemenin hepsinin iyi kümeye düşme olasılığı ~0.8^5≈%33 — "olağanüstü"
değil, makul bir tesadüf, tıpkı %22'nin ilk 5 seed'inde görüldüğü gibi).
**%12, %8'den istatistiksel olarak farklı/daha iyi bir nokta değil** — ikisi
de aynı gürültülü platonun içinde, medyanları da (0.665 vs 0.667) neredeyse
özdeş. Önceki "%12 toparlanma" iddiası **geri çekiliyor**.

### İstatistiksel anlamlılık: her seviye %0'a karşı bootstrap CI (10,000 resample)

`bootstrap_significance.py`, her kontaminasyon seviyesinin PR-AUC
dağılımını (20 seed across) %0 (20 seed, aynı şekilde) ile karşılaştırıp
farkın %95 bootstrap güven aralığını hesaplıyor (numpy ile elle resampling,
10,000 iterasyon, `05_results/bootstrap_significance.csv`):

| Contam. | mean | median | std | diff_from_0% | 95% CI | anlamlı mı |
|---|---|---|---|---|---|---|
| 0% | 0.716 | 0.715 | 0.009 | — (baseline) | — | — |
| 1% | 0.697 | 0.699 | 0.022 | −0.018 | [−0.029, −0.009] | **evet** |
| 2% | 0.691 | 0.690 | 0.011 | −0.024 | [−0.030, −0.018] | **evet** |
| 4% | 0.676 | 0.679 | 0.027 | −0.040 | [−0.053, −0.029] | **evet** |
| 8% | 0.639 | 0.667 | 0.060 | −0.077 | [−0.105, −0.052] | **evet** |
| 12% | 0.634 | 0.665 | 0.086 | −0.081 | [−0.121, −0.047] | **evet** |
| ~14.33% | 0.640 | 0.666 | 0.092 | −0.076 | [−0.119, −0.041] | **evet** |
| ~19.30% | 0.662 | 0.686 | 0.071 | −0.054 | [−0.088, −0.027] | **evet** |
| ~21.29% | 0.665 | 0.710 | 0.086 | −0.051 | [−0.090, −0.017] | **evet** |

**Sonuç: %0'dan farklı olmayan (CI sıfırı kapsayan) hiçbir seviye yok —
train setine karışan attack flow oranı ne kadar küçük olursa olsun
(1% dahil), VAE'nin PR-AUC'u istatistiksel olarak anlamlı şekilde düşüyor.**
20 seed'lik örneklemle bile hiçbir kontaminasyon seviyesinin CI'ı 0'ı
kapsamıyor — bu, %0-2 aralığındaki görece küçük farkların (örn. %1'de
−0.018) bile 5-seed'lik eski tabloda öne sürülen "gürültü içinde
ayırt edilemez" izlenimden daha güvenilir bir sinyal olduğunu gösteriyor.
Ayrıca CI genişliği kontaminasyon arttıkça büyüyor (%1'de [−0.029,−0.009],
genişlik 0.020; %12'de [−0.121,−0.047], genişlik 0.074) — bu da yüksek
kontaminasyon seviyelerindeki artan seed-to-seed instabilitenin (bimodalite)
doğrudan bir yansıması.

`contamination_curve.png` artık mean±std gölgeli bant yerine her nokta için
%95 bootstrap CI error bar'ı gösteriyor (`plot_contamination_curve_with_ci.py`,
`05_results/bootstrap_point_ci.csv`); şu an tüm noktalar %0'dan anlamlı
şekilde farklı olduğu için hepsi dolu işaretli, ama script gelecekte
anlamlı olmayan bir nokta çıkarsa onu otomatik olarak soluk/boş işaretle
render edecek şekilde yazıldı.

### Güncellenmiş genel yorum (önceki 5-seed'e dayalı yorumları geçersiz kılar)

- **"%0→%4 keskin düşüş, sonrası plato" görüşü hâlâ geçerli** ama artık
  medyan bazında da net: 0.715→0.699→0.690→0.679 (0→1→2→4%), sonra
  4-22% aralığı ~0.65-0.71 medyan bandında gürültülü bir platoya oturuyor.
- **"%12 toparlanma" iddiası YANLIŞTI ve geri çekildi** (yukarıya bkz.) —
  5 seed'lik şanslı bir örneklemin ürünüydü, 20 seed'de %12 %8'den daha
  iyi değil.
- **8% ve üstündeki her seviyede aynı bimodal instabilite var** (~%10-20
  seed kötü kümeye düşüyor) — bu, %8-22 platosundaki tüm nokta-tahminlerinin
  (mean özellikle) düşük n'de güvenilmez olduğu, medyan/trimmed_mean'in
  bu aralıkta mean'den daha temsili olduğu anlamına geliyor.
- **Ama tüm kontaminasyon seviyeleri, %1 dahil, %0'dan istatistiksel olarak
  anlamlı şekilde kötü** — yani "toparlanma var mı" sorusunun cevabı
  netleşti: **hiçbir seviye clean-only'ye (istatistiksel olarak) geri
  dönmüyor**, sadece 8-22% arası kendi içinde ayırt edilemeyen bir platoda
  geziniyor. Clean-only (%0) hem mean hem medyan hem de anlamlılık testiyle
  açık ara en iyi nokta olmaya devam ediyor.
- **%16/17/18 ara noktaları için**: bu sonuçlar göz önüne alınırsa, o
  noktalarda da baştan 20 seed ile eğitim yapılması öneriliyor (5 seed'in
  hem std'yi olduğundan düşük gösterdiği hem de "%12 toparlanma" gibi
  yanlış bir noktasal iddiaya yol açabildiği burada iki kez gösterildi).
