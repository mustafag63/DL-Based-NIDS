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

5-seed mean ± std, sabit test setinde:

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
