# Context Notes

- MAX_CONCURRENT=18 + exponential(8.5s) varış modeli resmi olarak doğrulandı
  (L=11.94≈12 hedef, FAIL oranı %1.8, browsing/formfilling KS testleri temiz).
  Searching persona'sında KS-stat≈0.15 seviyesinde tutarlı (iki ayrı 15-30dk
  koşuda tekrarlanan) ama sınırlı bir timing sapması gözlemlendi. addToCart/
  alert-wait etkileşimi hipotezi test edilip çürütüldü (CART vs NOCART grupları
  arasında medyan farkı yok). Kök neden muhtemelen yüksek concurrency altında
  sayfa-yükleme/CDP gecikmesi, izole edilmedi — kabul edilebilir seviyede
  kalındığı için (proje ölçütü: birebir CICIDS uyumu değil, gerçekçi referans)
  daha fazla araştırılmadı, dataset üretimine geçildi.

- **9 Temmuz 2026 — 9 pencerelik dataset koşusu: kök neden analizi, 3 kritik
  bug düzeltmesi, ve 8/9 pencerelik başarılı toplama.**

  **İlk 4 pencerenin (8 Temmuz gecesi) değerlendirmesi:** Window 2 (5%) ve
  Window 4 (30%) sağlıklı çıktı, ama Window 1 (baseline) ve Window 3 (15%)
  Zeek capture'ının pencere başlangıcından ~28-53dk geç başlaması nedeniyle
  neredeyse boştu (9 ve 96 flow). Ayrıca Locust'un nav_log.csv'sinin
  (Selenium'un aksine) append-only/kümülatif olduğu, her pencerenin
  dosyasının önceki tüm pencerelerin verisini de içerdiği tespit edildi.
  Sonuç: tüm 4 pencere silindi, 9-noktalı seriye (0/3/5/7/12/15/17/22/30%)
  geçilmeden önce kök neden düzeltmeleri yapıldı.

  **Bulunan ve düzeltilen bug'lar:**
  1. *Zeek capture gecikmesi* — başta "rotasyon/restart" sanıldı, ama kod
     incelemesiyle çürütüldü (zeek hiç restart edilmiyordu). Asıl kök neden:
     **Pi'nin sistem saati saatlerce kaymıştı** (WiFi bağlantısının arada
     kopması + `ntp.conf`'ta `server 127.127.1.0 prefer` +
     `fudge ... time1 -63072000` şeklinde bozuk bir local-clock fallback
     satırı, dış NTP sunucusu yokken saati kendi bozuk kaynağına
     kilitliyordu). WiFi (`wlan0`) NO-CARRIER durumundaydı, `ip route`'ta
     default gateway yoktu. Düzeltme: WiFi yeniden bağlandı, bozuk fudge
     satırı `ntp.conf`'tan silindi, saat bağımsız bir kaynaktan (HTTP Date
     header) manuel senkronize edildi, ardından `System clock
     synchronized: yes` doğrulandı. Ayrıca `local.zeek`'e
     `Log::default_rotation_interval = 1 day` eklendi (ekstra güvenlik) ve
     `run_all_windows.sh`'a trafik başlar başlamaz conn.log büyümesini
     doğrulayan bir `zeek_health_check()` (30sn timeout, 2 retry) eklendi.
  2. *Locust nav_log.csv kümülatif* — `request_logger.py` dosyayı hep
     append modunda açıyor, hiç truncate etmiyordu (Selenium'un
     `NavLog.java`'sındaki `TRUNCATE_EXISTING` davranışının karşılığı
     yoktu). Düzeltme: Locust başlamadan hemen önce nav_log.csv artık
     script tarafından truncate ediliyor.
  3. *`collect_window.sh`'daki tilde-quoting hatası* — Pi'ye giden uzak
     komutlarda `$REMOTE_DIR` (`~/ids-dataset-raw/...`) tek tırnak içine
     alınmıştı, tilde uzak shell'de genişlemiyordu, dosyalar sessizce
     yanlış path'e yazılmaya çalışılıyordu. Düzeltildi (tırnaklar
     kaldırıldı, `set -e` eklendi).
  4. *ISO8601 format bozukluğu* (`...T16:39:21.3NZ` gibi geçersiz
     damgalar, macOS'un BSD `date`'inin `%3N`'i desteklememesinden) —
     artık Python ile gerçek milisaniye hassasiyetli UTC ISO8601 üretiliyor
     (`now_iso()` fonksiyonu, hem Mac hem Pi tarafında).
  5. *`actual_attack_pct` hiç hesaplanmıyordu* (hep `null`) — artık
     `collect_window.sh`, filtrelenmiş `conn.log`'daki saldırgan IP
     (192.168.10.2) flow oranından bunu hesaplayıp `window_meta.json`'a
     yazıyor.
  6. *`BENIGN_FLOWS_PER_75MIN` sabiti orantılı ölçekleniyor* (kod zaten
     `window_minutes/75.0` ile ölçekliyormuş, ek değişiklik gerekmedi) —
     ama gerçek Zeek flow sayılarıyla karşılaştırıldığında bu sabitin
     (9110) yaklaşık **2x fazla tahmin edilmiş** olduğu ortaya çıktı (bkz.
     aşağıdaki kalibrasyon notu). Şimdilik düzeltilmedi (2 sağlıklı
     pencereyle güvenilir yeniden kalibrasyon yapılamaz, Dell'e ekstra
     erişim gerektirir) — ileride ayrı bir oturumda ele alınabilir.
  7. *`Fatal Python error: init_sys_streams / OSError: Errno 9 Bad file
     descriptor`* — koşu ilk kez başlatıldığında (`nohup caffeinate -i bash
     run_all_windows.sh > ... 2>&1 &`) stdin hiç yönlendirilmemişti. İlk
     pencerenin 60dk'lık bekleme adımı sırasında terminal sekmesi kapandı,
     script'in fd 0'ı (hâlâ terminale bağlıydı) kalıcı olarak bozuldu, o
     andan itibaren her `python3 -c` çağrısı (zaman damgası üretimi,
     `collect_window.sh`'ın epoch hesaplaması) çöktü — bash ve ssh/scp
     çağrıları etkilenmedi, sadece Python. Kanıt: `master_log.txt`'teki
     zaman damgalarının tam o andan itibaren kalıcı olarak boşalması +
     `last`/`w` çıktısının aynı saniyede bir tty kapanışı göstermesi.
     Düzeltme: başlatma komutuna `< /dev/null` eklendi
     (`nohup caffeinate -i bash run_all_windows.sh < /dev/null > ... 2>&1 &`).
     tmux ile açılan gerçek bir pty kasıtlı olarak yok edilerek (window_01
     senaryosunun birebir simülasyonu) doğrulandı — düzeltme sonrası pty
     kaybı script'i hiç etkilemedi.

  **Klasör isimlendirmesi de sadeleştirildi:** eski `window_NN_<label>_<pct>pct/`
  formatı (baseline/train_b/train_c/test etiketleriyle) yerine artık
  `window_NN_<pct>pct/` (NN=01-09, artan pct sırasıyla, label yok).
  `ensure_window_dir()` fonksiyonu klasör zaten varsa script'i tamamen
  durdurur (üzerine yazmaz, sessizce atlamaz).

  **Sonuç — 9-pencerelik koşu (2. ve 3. deneme sonunda başarılı):** İlk
  deneme (7. maddedeki fd bug'ı yüzünden) window_03'te, düzeltme sonrası
  ikinci deneme de aynı bug'ın henüz `< /dev/null` eklenmemiş haliyle
  yine window_03'te çöktü; üçüncü deneme (kök neden kesinleştirilip
  düzeltildikten sonra) window_01'den window_08'e kadar (0/3/5/7/12/15/17/22%)
  **8 pencerenin tamamı `status: collected` ile eksiksiz tamamlandı**, hiç
  çökme/`collection_failed` yaşanmadı. 9. pencere (30%) bilinçli olarak
  atlandı (8 pencere yeterli görüldü, zaman kısıtı yoktu ama gerek
  duyulmadı) — Pi'den silindi, sadece 1-8 kaldı. Sonuç Mac'e
  `~/Desktop/ids-dataset-raw-backup/` altına rsync ile yedeklendi (59MB,
  8 klasör). Eski 8 Temmuz verisi `ids-dataset-raw-backup-OLD/` olarak
  ayrı saklanıyor, training set'e karışmıyor.

  **Kalibrasyon sapması notu (önemli, Faz 2'de mutlaka dikkate alınmalı):**
  `actual_attack_pct`, `target_pct`'ten sistematik ve artan oranda düşük
  çıkıyor — `BENIGN_FLOWS_PER_75MIN`'in ~2x fazla tahmin edilmesinin
  sonucu:

  | target_pct | actual_attack_pct | oran |
  |---|---|---|
  | 0  | 0.0006 | ~0 |
  | 3  | 2.82 | %94 |
  | 5  | 3.99 | %80 |
  | 7  | 5.27 | %75 |
  | 12 | 8.16 | %68 |
  | 15 | 9.23 | %62 |
  | 17 | 10.44 | %61 |
  | 22 | 12.15 | %55 |

  Gerçek kontaminasyon aralığı hedeflenen 0-30% değil, **0-12.15%**
  oldu. Faz 2'de (ve nihai raporda) etiket/x-ekseni kaynağı olarak
  `target_pct` DEĞİL, her pencerenin kendi `window_meta.json`'undaki
  `actual_attack_pct`'i kullanılmalı — aksi halde precision/recall eğrisi
  sistematik olarak kaymış görünür. Veri Faz 2 (feature extraction,
  Autoencoder) için kullanılabilir durumda; sadece yüksek-kirlilik ucu
  (gerçek ~20%+) bu 8 pencerede temsil edilmiyor, ileride ek pencerelerle
  (kalibrasyon sabiti düzeltilerek) genişletilebilir.

  **Ayrıca not edildi (dokümantasyon amaçlı, kod değişikliği değil):**
  Locust'un gerçek persona-karışımı (searching %57, formfilling %29,
  browsing %14) tasarımın hedeflediği 60/30/10 ağırlığının tam tersi
  çıkıyor — session-süresi farkından kaynaklanıyor (weight sadece
  kullanıcı sayısını belirliyor, istek hacmini değil). Selenium'da
  arrival-bazlı ağırlıklandırma olduğu için bu sorun yok. Bu, Selenium
  ile Locust'un ürettiği "normal trafik" karışımının birbirinden farklı
  olduğu anlamına geliyor, Faz 2 raporunda şeffaf kalmalı.

- **10 Temmuz 2026 — Faz 2 (feature extraction) başlangıcı: window_01_0pct'te
  capture-level anomali tespit edildi, pipeline dışında tutuldu.**

  Zeek log şeması doğrulandı (conn.log: standart 22 alan, `#fields`/`#types`
  başlığından okunuyor; dns.log de aynı formatta). `techmarket.lab`
  filtresiyle dns.log'daki mDNS/Bonjour/NetBIOS gürültüsü (companion-link,
  asquic, MAC-D771BB, WORKGROUP, __MSBROWSE__ vb.) doğrulandı ve ayıklandı.

  **Önemli düzeltme — locust_nav_log.csv kümülatif DEĞİL:** Faz 2 görev
  tanımındaki varsayımın aksine (yukarıdaki 8 Temmuz notuyla çelişiyor gibi
  görünse de, o not `request_logger.py`'nin append-modunda **açıldığı** eski
  duruma aitti), 9 Temmuz'daki 8 pencerelik koşuda her `locust_nav_log.csv`
  dosyasının `ts` aralığı incelendiğinde, dosyanın SADECE kendi penceresinin
  zaman aralığını kapsadığı görüldü (satır sayıları da pencereler arası
  ~14500-15000 civarında sabit, artmıyor). Yani 8 Temmuz'daki truncate
  düzeltmesi (`request_logger.py`'ye pencere başında truncate eklenmesi)
  gerçekten çalışıyor. Sadece Dell'in `attack_log.csv`'si hâlâ kümülatif
  (satır sayısı pencereler arası 58→121 artıyor) — bu yüzden sadece
  attack_log.csv, window_meta.json start/end ile filtreleniyor;
  locust_nav_log.csv'ye zaman filtresi uygulanmıyor.

  **window_01_0pct — capture-level anomali, Faz 2 pipeline'ından çıkarıldı
  (silinmedi):** conn.log'da 329,921 satır var — diğer pencerelerin
  (2,994-6,338 flow) 50-100 katı. İncelemede:
  - Bu flow'ların 329,237'si `192.168.10.3 → 192.168.10.1:80` (bot→Pi HTTP),
    pencereye düzgün yayılmış (5dk bucket'larda 26K-38K, tek bir patlama
    değil, sürekli).
  - conn_state'in %96.8'i `OTH` (318,693/329,237), duration'ın **%100'ü
    boş ("-")**. Diğer pencerelerde (window_02, window_04 doğrulandı) `OTH`
    state HİÇ görülmüyor, duration boş oranı %0.
  - Aynı zaman aralığında `locust_nav_log.csv`'nin ürettiği istek sayısı
    14,528 — yani conn.log flow sayısı Locust isteklerinin **~23 katı**
    (window_02'de bu oran 0.19x, window_04'te 0.25x — normalde conn.log
    Locust'tan daha AZ satır üretiyor, çünkü bazı flow'lar birleşiyor).
  - Sonuç: gerçek trafik değil, muhtemelen Zeek connection-tracking
    bozukluğu (SYN kaçırma / paket tekrarı / reassembly sorunu). Kök neden
    araştırılmadı — ayrı bir soruşturma maddesi, Faz 2'yi bloklamıyor.
  - **Karar:** window_01_0pct feature extraction'a dahil edilmedi (backup'ta
    duruyor, silinmedi). Faz 2 çıktısı `window_02_3pct` → `window_08_22pct`
    (7 pencere, 32,708 flow) üzerinden üretildi. Bu, 0% baseline'ın
    autoencoder eğitim setinde eksik olduğu anlamına geliyor — ileride
    window_01'in Zeek loglarının yeniden capture edilmesi (veya kök neden
    bulunup düzeltilmesi) gerekebilir.

  **Feature matrix (pilot + tam koşu):** conn.log flow-bazlı, `id.orig_h`/
  `id.resp_h` sadece lab IP'leri (192.168.10.1/.2/.3) ile sınırlandı (IPv6
  link-local + mDNS/LLMNR multicast gürültüsü atıldı). `is_attack` etiketi
  `id.orig_h == 192.168.10.2` (Dell) ile flow-bazlı üretildi; pencere bazında
  ortalaması `actual_attack_pct`'e çok yakın çıktı (ör. window_02: %2.81 flow
  vs %2.82 actual; window_05'te en büyük sapma, %7.37 vs %8.16). `proto`/
  `service`/`conn_state` OneHotEncoder, sayısal alanlar StandardScaler ile
  **tüm 7 pencere birleştirildikten sonra tek seferde (global fit)** işlendi
  — pencereler arası conn_state kategori seti farklı olduğundan (ör. `SF`
  sadece bazı pencerelerde var) kolonların hizalı kalması için. `missed_bytes`
  7 pencerenin tamamında sabit 0 bulundu, sıfır-varyans nedeniyle feature
  listesinden çıkarıldı. Çıktı: `~/Desktop/ids-dataset-features/
  features_all_windows.{csv,parquet}` (32,708 satır × 23 kolon) ve
  `feature_extraction_report.md`.

- **10 Temmuz 2026 — window_01_0pct capture anomalisi tespit edildi, yeniden
  üretim planlandı.**

  Faz 2 pilot analizinde (window_01 üzerinde) window_01_0pct/zeek/conn.log'un
  diğer 7 pencereden yapısal olarak koptuğu görüldü:
  - 329,921 flow (diğerlerinde 2,851-6,400 aralığında)
  - %96.8'i conn_state=OTH (window_02/04'te OTH hiç yok, sadece SH/S0/RST*)
  - %100'ünde duration boş ("-")
  - conn.log/Locust-request oranı 22.7x (window_02'de 0.19x, window_04'te 0.25x)
  - flow'lar pencereye düzgün yayılmış (ani patlama değil), yani kısa süreli
    bir olay değil, pencerenin tamamında süregelen bir capture arızası

  Kök neden henüz belirlenmedi (muhtemelen Zeek connection-tracking/capture
  katmanında bir sorun — 9 Temmuz'daki Pi saat kayması bug'ıyla aynı aile
  olabilir ama doğrulanmadı). window_01, gerçek 0% benign trafiği temsil
  etmiyor, bu haliyle Faz 2 feature extraction'a DAHİL EDİLMEDİ.

  **Karar:** window_01_0pct Pi'den/backup'tan silinmedi, ayrı tutuluyor.
  Faz 2, window_02-08 (7 pencere) ile devam ediyor. window_01'in yerini
  alacak temiz bir 0% (baseline) pencere, capture altyapısı (Zeek health
  check, saat senkronizasyonu vb.) tekrar doğrulandıktan sonra AYRI bir
  koşuyla yeniden üretilecek. Bu yeniden üretim, mevcut 7 pencerenin
  timeline'ını bozmayacak şekilde (ayrı bir window numarası/klasör olarak,
  ör. window_09_0pct) planlanmalı.

  **TODO (Faz 2 bitince veya paralel):**
  1. window_01 anomalisinin kök nedenini araştır (Pi Zeek stderr/dmesg,
     capture sırasında CPU/bellek durumu, WiFi durumu kontrol edilebilir).
  2. Kök neden bulunursa/düzeltilirse, tek pencerelik bir 0% koşusu daha
     yap (window_09_0pct veya benzeri), health-check'in bu sefer temiz
     geçtiğini doğrula.
  3. Yeni pencere geldiğinde final dataset'e eklenir, mevcut 7 pencere
     etkilenmez.

## 10 Temmuz 2026 — window_05 sapması: kök neden bulundu, actual_attack_pct'te LLMNR gürültüsü

window_05_12pct'te flow-bazlı is_attack oranı (7.37%) ile window_meta.json'daki
actual_attack_pct (8.16%) arasındaki ~0.79 puanlık sapmanın kök nedeni bulundu:

- collect_window.sh'ın actual_attack_pct hesaplaması (satır 143-152), ham
  conn.log üzerinde src==attacker_ip OR dst==attacker_ip koşuluyla flow
  sayıyor — hiçbir noise filtresi (mDNS/LLMNR/multicast) uygulamıyor.
- window_05'te, Dell makinesinin (192.168.10.2, saldırı orkestratörü) kendi
  Windows OS'undan kaynaklanan LLMNR broadcast paketleri (10.2 → 224.0.0.252,
  ağ keşif amaçlı, saldırı ile ilgisiz) o pencerede 51 adede sıçramış
  (diğer pencerelerde 1-3 arası, ihmal edilebilir seviyede).
- Bu 51 paket, collect_window.sh'ın "attack" saydığı ama gerçekte saldırı
  olmayan trafik — actual_attack_pct'i hafifçe şişiriyor.
- Faz 2 pipeline'ındaki flow-bazlı is_attack etiketi (lab-IP filtresi
  uygulandıktan sonra hesaplanan) bu gürültüyü zaten doğru şekilde
  ayıklıyor — yani DAHA DOĞRU bir ground truth.

**Sonuç/karar:** Diğer 6 pencerede (02,03,04,06,07,08) sapma ihmal edilebilir
seviyede (±0.06 puan) olduğu için, satır bazlı is_attack etiketi zaten Faz 2
feature matrix'inde kullanılıyor ve bu doğru kabul ediliyor. window_05 için
ekstra bir düzeltme YAPILMADI (etiketleme zaten doğru kaynaktan, filtrelenmiş
veriden geliyor) — sadece window_meta.json'daki actual_attack_pct'in bu
pencerede hafif şişirilmiş olduğu not edildi, raporda referans olarak
kullanılırsa bu şeffaflıkla belirtilmeli.

**TODO (ileride, opsiyonel):** collect_window.sh'a LLMNR/multicast noise
filtresi eklenirse, gelecek koşularda actual_attack_pct hesaplaması daha
sağlam olur. Faz 2/3'ü bloklamıyor.

## TODO — Akşam yapılacak: window_01 kök neden araştırması

window_01_0pct'teki Zeek capture anomalisinin (329K flow, %96.8 OTH state,
%100 boş duration, diğer pencerelerle uyuşmayan yapı) kök nedeni henüz
araştırılmadı. Akşam üzeri şunlar kontrol edilecek:
1. Zeek weird.log / reporter.log / stats.log (o zaman aralığına ait)
2. Sistem kaynak durumu (CPU/RAM/disk I/O, dmesg)
3. WiFi/network instability (9 Temmuz'daki saat kayması bug'ıyla aynı aile
   olabilir mi)
4. Zeek health check loglarının o pencerede ne söylediği
5. Capture arayüzü/donanım durumu (ethtool, link-flap)

Kök neden bulunursa/düzeltilirse, temiz bir 0% baseline pencere yeniden
üretilecek (window_09_0pct veya benzeri isimle, mevcut 7 pencerenin
timeline'ını bozmadan).

Bu araştırma tamamlanana kadar Faz 2, window_01 olmadan (7 pencere ile)
teknik olarak kullanılabilir durumda ama eksik/geçici sayılmalı.

## 10 Temmuz 2026 — 3 yeni feature eklendi + benign-only scaler fit düzeltmesi (leakage fix)

**Metodolojik düzeltme (önemli, gizlenmemeli):** `faz2_feature_extraction.py`
ilk yazıldığında `StandardScaler`, `conn_all[NUMERIC_COLS]` üzerinde TÜM
veriye (benign + attack birlikte) fit ediliyordu — bu, anomaly-detection
autoencoder standardına aykırıydı (model normal trafiğin dağılımını
öğrenmeli, attack istatistikleriyle kirlenmemeli) ve önceki bir turda
"zaten böyle yapılıyor" varsayımıyla konuşulmuştu ama kodda hiç
uygulanmamıştı. Bugün gerçek anlamda düzeltildi: scaler artık SADECE
`is_attack == 0` satırlara `fit()` ediliyor, tüm satırlara (`benign` +
`attack`) `transform()` uygulanıyor. Eski (global-fit) değerlerle
karşılaştırma:

| kolon | global mean/std | benign-only mean/std | mean farkı | std farkı |
|---|---|---|---|---|
| duration | 30.43 / 214.05 | 32.79 / 223.06 | %7.7 | %4.2 |
| orig_bytes | 1356.09 / 6831.06 | 1468.43 / 7112.40 | %8.3 | %4.1 |
| resp_bytes | 8.63 / 764.80 | 9.38 / 797.53 | %8.7 | %4.3 |
| orig_pkts | 19.60 / 79.00 | 21.03 / 82.22 | %7.3 | %4.1 |
| orig_ip_bytes | 2377.98 / 10910.21 | 2567.86 / 11357.42 | %8.0 | %4.1 |
| resp_pkts | 0.06 / 0.24 | 0.03 / 0.16 | %-59.6 | %-34.2 |
| resp_ip_bytes | 3.04 / 23.27 | 1.61 / 22.99 | %-47.0 | %-1.2 |

`resp_pkts`/`resp_ip_bytes` en çok etkilenen kolonlar (attack trafiği —
özellikle Slowloris/portscan'in çoğunlukla yanıt almayan flow'ları —
global istatistikleri belirgin şekilde çekiyordu). `OneHotEncoder`
(kategorik: `proto`/`service`/`conn_state`) hâlâ global fit — bu, kategori
kelime dağarcığının hem benign hem attack state'lerini kapsaması gerektiği
için kasıtlı, sayısal scaler'daki leakage sorunuyla aynı kategoride değil.

**3 yeni türetilmiş feature eklendi:**
- `bytes_per_sec = orig_bytes / duration`, `pkts_per_sec = orig_pkts / duration`
  — duration==0 olan 636 flow'da (585 S0 + 51 OTH, hiç kurulmamış
  bağlantılar — S0 çoğunlukla portscan hedeflerinin yanıt vermediği
  portlar, OTH ise window_05'teki LLMNR broadcast gürültüsüyle aynı aile)
  0 atandı, sıfıra bölme yok.
- `byte_ratio = orig_bytes / (resp_bytes + 1)` — benign flow'larda medyan
  834, attack flow'larda medyan 11 (~76x fark) — Slowloris/portscan gibi
  "az veri gönder, çok az/yanıt alma" saldırılarını güçlü şekilde ayırt
  ediyor, beklenen doğrultuda.

**Sonuç:** `features_all_windows.{csv,parquet}` yeniden üretildi (23→26
sütun, satır sayısı aynı: 32,708), `by_window/` 7 dosya da aynı global-fit'ten
(artık benign-only) yeniden filtrelendi. Eski (global-fit, leakage'lı) hali
git history'de duruyor.

## 10 Temmuz 2026 (öğleden sonra) — window_01 başarıyla yeniden üretildi

Sabahki kök neden analizinde bulunan önlemler (NIC checksum offloading
kapatıldı, sürekli Zeek PID izleme eklendi, reporter.log post-hoc kontrolü
eklendi) uygulandıktan sonra window_01_0pct yeniden koşuldu (13:13-14:14
UTC+3, 60 dakika). Sonuç: 567 flow, %96.5 SF / %2.1 S0, OTH state YOK,
zeek restart izi YOK, actual_attack_pct=0.000000. Eski bozuk veri
window_01_0pct_BROKEN_20260709/ olarak arşivde kalıyor (silinmedi, kanıt
olarak saklanıyor).

Ayrıca bulunan/düzeltilen yan bug: run_all_windows.sh içindeki
COLLECT_SCRIPT değişkeni eski path'i (~/Desktop/collect_window.sh)
gösteriyordu, script IDS-Analysis/ altına taşındıktan sonra
güncellenmemişti - düzeltildi (~/Desktop/IDS-Analysis/collect_window.sh).

**Sonuç:** Artık 8/8 pencere (window_01-08) sağlıklı ve kullanılabilir
durumda. Faz 2 feature extraction'a window_01 dahil edilebilir.

## 10 Temmuz 2026 — window_01, Faz 2 feature extraction'a dahil edildi

window_01_0pct'in yeniden koşulan temiz verisi (547 flow, 0% OTH) artık
faz2_feature_extraction.py pipeline'ına dahil edildi. Scaler/encoder
8 pencerenin tamamındaki benign veriye yeniden fit edildi (7-pencere
fit'inden istatistiksel olarak farklı, beklenen davranış).

Güncel toplam: 33.255 satır × 27 kolon, 8/8 pencere (window_01-08).
window_01 katkısı: 547 satır, is_attack oranı 0.0 (baseline doğrulandı).

features_all_windows.csv/parquet ve by_window/ klasörü güncellendi.
faz2_feature_extraction.py'nin kod yorumları İngilizce'ye çevrildi (rapor/
context.md Türkçe kalmaya devam ediyor).

Faz 2 artık TAMAMLANDI - 8 sağlıklı pencere, doğru metodoloji (benign-only
scaler fit, leakage-free), 9 feature (temel 6 + bytes_per_sec + pkts_per_sec
+ byte_ratio). Sıradaki adım: Faz 3 (Autoencoder mimarisi).

## TODO — IP-Bazlı Zaman-Penceresi Agregasyonu (Faz 3 sonrası, 2. iterasyon)

Karar: IP-bazlı zaman-penceresi agregasyon feature'ları (conn_count_60s,
unique_dst_ports_60s, unique_dst_ips_60s, failed_conn_ratio_60s - port
scan/DoS gibi zaman içindeki davranış örüntüsüyle ortaya çıkan saldırıları
yakalamak için) ŞİMDİ eklenmeyecek. Gérard'ın "önce minimal end-to-end
pipeline" direktifine uygun olarak, sıra şöyle:

1. Checksum-offloading düzeltmesiyle yeniden capture edilen 8 pencereyle
   Faz 2 finalize edilir (mevcut ~26 kolon feature set).
2. Faz 3: minimal Autoencoder bu feature setiyle eğitilir, reconstruction
   error dağılımı (benign vs attack) incelenir.
3. Sonuç yorumlanır: model hangi saldırı türlerini (Slowloris'in düşük
   byte_ratio'su gibi tek-flow sinyalleriyle görünen türler) yakalıyor,
   hangilerini (port scan gibi zaman-dağıtık örüntüler) kaçırıyor.
4. EĞER port scan/DoS gibi dağıtık saldırılar zayıf tespit ediliyorsa →
   IP-bazlı agregasyon feature'ları eklenir (rolling window, pencere
   sınırları karışmadan hesaplanmalı - window_meta.json start/end'e göre
   her pencere kendi içinde ayrı hesaplanmalı), model 2. iterasyon olarak
   yeniden eğitilir, sonuçlar karşılaştırılır.

Bu sıralama tercih edildi çünkü: (a) Gérard'ın yönergesiyle uyumlu, (b)
agregasyonun gerçekten gerekli olup olmadığı somut kanıtla belirlenir
(kör kör eklemek yerine), (c) raporda "iteratif iyileştirme" anlatısı
güçlü bir metodoloji hikayesi sağlar.

### GÜNCELLEME (13 Temmuz 2026) — Yukarıdaki TODO uygulandı, sonuç KISMEN
doğrulandı — %100 recall rakamı iki farklı mekanizmadan geliyor, biri
bu lab'a özgü bir artefakt

Motivasyon: `attack_type_breakdown_evaluation.py` sonucu, mevcut 18
kolonluk feature setiyle autoencoder'ın apache_bench'i **%0 recall**
ile tamamen kaçırdığını gösterdi (portscan/slowloris ~%99-100).
Yukarıdaki TODO'nun 4. maddesi tetiklendi: `faz2_feature_extraction.py`'ye
`conn_count_60s`, `unique_dst_ports_60s`, `unique_dst_ips_60s`,
`failed_conn_ratio_60s` eklendi (src IP + window_id bazlı, 60s geriye
bakan rolling window, pencere sınırları karışmadan), 10 model
`04_phase3_models_v2/`'de yeniden eğitildi (eski `04_phase3_models/`
korunuyor).

**İlk sonuç (headline):** apache_bench recall **%0 → %100** (5 seed'in
TAMAMINDA, iki varyantta da, std=0), portscan/slowloris zaten
mükemmeldi ve bozulmadı, benign false-positive oranı hafifçe arttı
(~%2 → ~%3). Pencere bazlı kırılım (window_02'den window_08'e, N=21'den
190'a) da recall'ün her pencerede %100 olduğunu gösterdi.

**Ama bu %100 rakamı derinlemesine incelendiğinde (`analysis/
rolling_feature_overlap_check.py`) İKİ FARKLI, birbirinden bağımsız
mekanizmadan geldiği ortaya çıktı — biri gerçek/genellenebilir, diğeri
bu lab'ın saldırı-sırası tasarımına özgü bir artefakt:**

**(a) Yüksek-N pencerelerde (window_05 ve üstü, N≥92): GERÇEK sinyal.**
`conn_count_60s` TEK BAŞINA (portscan'in katkısı olmadan bile) benign'i
aşıyor — aynı kaynaktan 60 saniyede çok sayıda bağlantı, davranışsal
olarak gerçekten anormal ve prensipte genellenebilir bir örüntü.

**(b) Düşük-N pencerelerde (window_02-04, N=21-51): ARTEFAKT —
"portscan-miras etkisi".** Bu pencerelerde ayrım **tamamen**
`unique_dst_ports_60s`'e dayanıyor, `conn_count_60s` kendi başına
apache_bench'i benign'den **DAHA SAKİN** gösteriyor:

| pencere | apache_bench conn_count_60s (mean) | benign conn_count_60s (mean) | apache_bench benign'e göre |
|---|---|---|---|
| window_02 (N=21) | 32.0 | 112.2 | **DAHA DÜŞÜK** |
| window_03 (N=36) | 53.5 | 106.1 | **DAHA DÜŞÜK** |
| window_04 (N=51) | 76.0 | 113.5 | **DAHA DÜŞÜK** |
| window_05 (N=92) | 137.5 | 105.9 | daha yüksek |
| window_06 (N=119) | 178.0 | 112.9 | daha yüksek |
| window_07 (N=138) | 206.5 | 113.4 | daha yüksek |
| window_08 (N=190) | 284.5 | 106.1 | daha yüksek |

`unique_dst_ports_60s`'in neden hâlâ ayırt ettiği: `attack_orchestrator.py`
HER saldırı setinde portscan'i apache_bench'ten ~0.4 saniye önce, AYNI
kaynak IP'den çalıştırıyor (madde 3, 596-597. satırlar). 60 saniyelik
rolling window, apache_bench anında hâlâ az önce biten portscan'in
taradığı port sayısını (`unique_dst_ports_60s` = pencerenin N'i, birebir
sabit) "miras" alıyor — apache_bench'in KENDİSİ sadece port 80'e istek
atıyor, port çeşitliliği tamamen komşu portscan'den geliyor. Ayrıca
benign'in port çeşitliliği hep ≤3 (bu lab'da sadece 80/HTTP, 53/DNS,
22/SSH servisleri var — yapısal bir sınır, Selenium/Locust tasarımı
değil), bu da ayrımı suni şekilde "temiz" gösteriyor.

**Pratik sonuç — açıkça yazılmalı:** Gerçek dünyada biri, önceden
portscan yapmadan, tek başına düşük-hacimli bir apache_bench-tarzı yük
testi/DoS başlatırsa, bu sinyal (unique_dst_ports_60s'in portscan-miras
katkısı) tamamen kaybolur ve saldırı muhtemelen yine kaçırılır. **"%100
recall" rakamı "model apache_bench'i her koşulda yakalıyor" şeklinde
OKUNMAMALI.** Doğru çerçeve: yüksek-hacimli floodlar genellenebilir
şekilde yakalanıyor; izole/düşük-hacimli apache_bench'in yakalanması bu
lab'ın saldırı sırasına özgü bir artefakta dayanıyor, garantili değil.

**İlişkili ama FARKLI bir sınırlama — "kaynak-IP confound'u":** Bu lab'da
sadece 2 makine trafik üretiyor ve rolleri hiç karışmıyor (192.168.10.2
SADECE saldırgan, 192.168.10.3 SADECE benign, bkz. 558/571. satırlar).
Bu yüzden src-IP bazlı HERHANGİ bir rolling agregasyon feature'ı, saf
davranışı değil kısmen "hangi makine bu" bilgisini de taşıyabilir —
saldırgan makinenin "boşta" (saldırı yokken) referans trafiği veri
setinde hiç yok. Bu, yukarıdaki "portscan-miras etkisi"nden AYRI bir
sorun: portscan-miras etkisi TEK bir saldırı IÇİNDEKİ komşu komutların
birbirini kirletmesiyken, kaynak-IP confound'u genel olarak "sadece 2
makine var" yapısal sınırının bir sonucu.

**Yeni TODO — izole apache_bench testi (henüz yapılmadı):** Rolling
feature'ların gerçek genellenebilirliğini netleştirmek için,
apache_bench'in portscan OLMADAN, TEK BAŞINA çalıştırıldığı bir senaryo
(yeni capture veya sentetik/simüle veri) test edilmeli. Beklenti:
(a) yukarıdaki tabloya göre yüksek-N'de conn_count_60s'in tek başına
yeterli olacağı, (b) düşük-N'de ayrımın önemli ölçüde zayıflayacağı
(unique_dst_ports_60s artık miras alacak bir portscan bulamayacağı için).

**Script:** `IDS-Project/analysis/rolling_feature_overlap_check.py`
(salt-okunur; ayrıca `attack_type_breakdown_v1_vs_v2_comparison.py` ve
`attack_type_v2_per_window_breakdown.py` ile birlikte okunmalı).

**Genel özet güncellemesi:** Faz 3 v2 aggregate recall **%100**
(5 seed, iki varyant) — **ama bkz. yukarıdaki nüans**: bu rakamın
düşük-N bileşeni, bu lab'ın sabit saldırı-sırası tasarımına (portscan
→ apache_bench → slowloris, hep aynı IP'den, ~0.4s arayla) özgü bir
artefakta dayanıyor, genel bir "model apache_bench'i her zaman yakalar"
iddiası olarak okunmamalı.

## 10 Temmuz 2026 (akşam) — window_02-08 checksum-offloading düzeltmesiyle başarıyla yeniden capture edildi

Öğleden sonra bulunan checksum-offloading sorunu (window_02-08'in 9 Temmuz'da
NIC checksum offloading açıkken capture edilmiş olması - yanıt tarafı
trafiğinin Zeek tarafından neredeyse hiç kaydedilmemesi, %61 SH + %38 S0
conn_state, gerçek resp_bytes'in ~235x düşük görünmesi) için 7 pencere
(window_02-08) checksum offloading kapalıyken yeniden koşuldu (14:43-22:01,
~7 saat 20 dakika, 7/7 pencere collect_window.sh ile başarıyla toplandı,
hiç hata yok).

Sonuç doğrulandı (window_02 örneği): conn_state dağılımı %61 SH+%38 S0'dan
%97.2 SF'ye düzeldi (4018/4135 flow). actual_attack_pct=3.077% (target=3%
ile tutarlı). Flow sayısı 2.994'ten 4.135'e çıktı (artık HTTP keep-alive
doğru tanınıyor, önceki düşük sayı parçalanmış/yarım-kalmış bağlantılardan
kaynaklanıyordu).

Koşu sırasında ~3 saatlik bir gecikme gözlemlendi (window_03'ün "bekleniyor"
adımı beklenenden uzun sürdü) - araştırıldı, gerçek bir sorun DEĞİL: sadece
UTC log zaman damgaları ile yerel saat (+3) karşılaştırılırken analiz
hatası yapılmıştı, koşu aslında hiç kesintiye uğramadı, Selenium/Locust/Dell
hepsi planlandığı gibi (BUILD SUCCESS, exit code 0, %0 fail) tamamlandı.

Eski (checksum-offload-açık) window_02-08 verisi silinmedi, arşivde duruyor:
window_0X_*_BROKEN_checksum_20260709/ (hem Mac hem Pi'de).

**Sonuç: Artık 8/8 pencere (window_01-08) hem window_01 restart sorunundan
hem de checksum-offloading sorunundan arınmış, tutarlı bir standartla
toplanmış durumda.**

Sıradaki adım: Faz 2 feature extraction'ı bu 8 sağlıklı pencereyle (checksum
düzeltmesi sonrası window_02-08 + zaten sağlıklı olan window_01) baştan
çalıştırmak - mevcut features_all_windows.csv/parquet, önceki (bozuk)
window_02-08 verisine dayandığı için GEÇERSİZ, yeniden üretilmesi gerekiyor.

**Güncelleme (2026-07-11):** Yukarıdaki "Eski (checksum-offload-açık)
window_02-08 verisi silinmedi, arşivde duruyor" notu artık GEÇERSİZ.
Kullanıcı onayıyla 8 BROKEN klasörün tamamı (window_01_0pct_BROKEN_20260709
+ window_02-08_*_BROKEN_checksum_20260709) hem Mac'te
(~/Desktop/ids-dataset-raw-backup/) hem Pi'de (~/ids-dataset-raw/) silindi
(~119M toplam, du -sh kanıtı ve silme-sonrası ls doğrulaması ile). Sadece
8 sağlıklı window_01-08 klasörü kaldı.

## 11 Temmuz 2026 — Faz 2 sonrası EDA bulguları ve aksiyonlar

**1. conn_state naive baseline (autoencoder karşılaştırma referansı):**
EDA'da conn_state_SF'nin benign'de %99.9, attack'ta %33.4 olduğu görüldü.
Tek kural test edildi: "conn_state != SF ise attack tahmin et"
(36.705 flow, tüm 8 pencere, kod değişikliği yok — sadece analiz):
- TP=2576, FP=24, TN=32811, FN=1294
- precision=%99.08, recall=%66.56, f1=0.796, accuracy=%96.41

Yani sadece tek bir kategorik kolonla (conn_state) attack flow'ların
%66.6'sı, yalnızca 24 benign flow'u (32.835'te) yanlış işaretleyerek
yakalanabiliyor. **Faz 3 TODO:** Autoencoder sonuçları geldiğinde bu
naive baseline'la karşılaştırılmalı — eğer autoencoder'ın recall/precision'ı
bu basit kuralı anlamlı şekilde geçemiyorsa, model esasen conn_state
one-hot'una "kısayoldan" dayanıyor demektir, diğer feature'ların (byte
hacimleri, oran feature'ları) katkısı sorgulanmalı.

**2. byte_ratio notu DÜZELTMESİ — eski not GEÇERSİZ:**
276. satırdaki (10 Temmuz, "3 yeni feature eklendi") bölümünde "benign
medyan 834, attack medyan 11 (~76x fark)" notu vardı. Bu not, o anki
feature extraction koşusu HENÜZ window_01 restart-fix'i (322. satır) VE
window_02-08 checksum-offloading fix'i (384. satır) UYGULANMADAN ÖNCE
hesaplanmıştı — yani bozuk (checksum offloading açık) veriye dayanıyordu.
O bug, yanıt tarafı trafiğinin Zeek tarafından neredeyse hiç kaydedilmemesine
ve resp_bytes'in gerçek değerin ~235x altında görünmesine yol açıyordu
(389. satır) — bu da orig_bytes/(resp_bytes+1) formülünü resp_bytes'in
yapay olarak neredeyse sıfır olduğu flow'larda şişiriyordu.

**Formül değişmedi** (`byte_ratio = orig_bytes / (resp_bytes + 1)`,
faz2_feature_extraction.py'de hâlâ aynı) — fark tamamen veri kalitesinden
kaynaklanıyor (resp_bytes artık doğru kaydediliyor).

**Güncel doğru sayılar (11 Temmuz EDA raporu, checksum-fix sonrası 8
pencere, 36.705 flow):** benign medyan **0.060**, attack medyan **0.032**
(medyanda ayrım zayıf) — ama mean'de güçlü fark: benign mean **0.081**,
attack mean **70.25** (attack tarafında birkaç aşırı-yüksek-ratio outlier
flow, max=211, dağılımı kalın kuyruklu yapıyor). |z|>3 outlier oranı:
benign %3.64, attack **%33.44** — yani byte_ratio ayrımı medyanda değil,
attack'taki aşırı uçlarda görünüyor. 312-315. satırlardaki "834 vs 11,
~76x" rakamları artık kullanılmamalı.

**3. Redundant feature'lar düşürüldü (kod değişikliği):**
EDA korelasyon analizinde orig_ip_bytes ~ orig_bytes (r=0.996) ve
resp_ip_bytes ~ resp_bytes (r=0.99996) neredeyse birebir kopya çıktı
(ip_bytes ≈ bytes + header overhead). `faz2_feature_extraction.py`'deki
`NUMERIC_COLS` listesinden `orig_ip_bytes` ve `resp_ip_bytes` çıkarıldı
(CONN_COLS'ta ham conn.log parse için hâlâ okunuyorlar, sadece feature
setine girmiyorlar). Script yeniden çalıştırıldı:
`features_all_windows.csv/parquet` ve `by_window/` yeniden üretildi.
Kolon sayısı **24 → 22** (satır sayısı değişmedi: 36.705). Scaler artık
8 sayısal kolona (`duration, orig_bytes, resp_bytes, orig_pkts, resp_pkts,
bytes_per_sec, pkts_per_sec, byte_ratio`) fit ediliyor, one-hot/kategorik
kolonlar etkilenmedi.

**4. window_01 sapması — Faz 3 train/val split TODO:**
EDA'da window_01_0pct'in diğer 7 pencereden istatistiksel olarak
farklı olduğu görüldü (benign-only ortalama duration ~81s, diğer
pencerelerde ~34-40s; orig_bytes/orig_pkts/orig_ip_bytes'ta da benzer
sapma, CV=0.24-0.37 en yüksek feature'lar arasında). Sebep muhtemelen
düşük flow sayısı (547 vs diğerlerinde 4100-6300) + saf-benign (0%
attack) baseline karakteri — capture kalitesi sorunu DEĞİL (checksum/OTH
bug'ı bu pencerede yok, 10 Temmuz öğleden sonra ayrıca doğrulandı).

**TODO (Faz 3 planlaması için karar bekliyor, kod değişikliği YAPILMADI):**
Train/val split stratejisi belirlenirken window_01'in nasıl ele alınacağına
karar verilmeli:
- Window bazlı split yapılacaksa (örn. bazı pencereler train, bazıları
  val/test), window_01'in val/test tarafına düşmesi durumunda dağılım
  sapması nedeniyle yanıltıcı reconstruction-error sonuçları çıkabilir.
- Random/stratified (window'a bakmaksızın) split yapılacaksa bu risk
  daha düşük ama window_01'in görece küçük örneklem boyutu (547) yine de
  ağırlıklandırma sorunu yaratabilir.
Şimdilik hiçbir filtreleme/ağırlıklandırma uygulanmadı, sadece not düşüldü.

**5. Anomali sinyali beklentisi (Faz 3 karşılaştırma referansı):**
EDA'da scaled kolonlarda benign vs attack |z|>3 outlier oranı karşılaştırıldı.
Çoğu ham hacim feature'ında (duration, orig/resp_bytes, orig/resp_pkts,
bytes_per_sec) attack flow'ların outlier oranı benign'den DAHA DÜŞÜK (%0
vs %1-3) — yani attack flow'lar bu feature'larda "küçük/kısa" oldukları
için ham skalada aykırı görünmüyorlar. Buna karşılık **pkts_per_sec**
(benign %2.89 vs attack **%32.56**) ve **byte_ratio** (benign %3.64 vs
attack **%33.44**) kolonlarında attack flow'ların yaklaşık 1/3'ü benign
dağılımına göre aşırı uç değerde.

**Faz 3 beklentisi:** Autoencoder'ın reconstruction error'u özellikle bu
iki feature'da (pkts_per_sec, byte_ratio) attack flow'lar için yüksek
çıkmalı — bu, oran-bazlı türetilmiş feature'ların ham hacim feature'larına
göre daha güçlü anomali sinyali taşıdığı hipotezini destekliyor. Sonuçlar
geldiğinde bu beklentiyle karşılaştırılacak; eğer reconstruction error bu
iki feature'da beklenen şekilde yükselmiyorsa, model bu sinyali
öğrenememiş demektir ve feature ağırlıklandırma/mimari gözden geçirilmeli.

## 11 Temmuz 2026 — Faz 3 öncesi leakage/split değerlendirmesi

Autoencoder eğitimine geçmeden önce 4 diagnostik kontrol çalıştırıldı
(kod değişikliği yok, sadece analiz — sonuçlar aşağıda, karar Faz 3
planlamasında verilecek).

### 1. Near-duplicate flow tespiti — KRİTİK RİSK doğrulandı

Attack flow'ları pencere içinde `proto|service|conn_state|duration(1
ondalık)|orig_bytes(10'a yuvarlanmış)` imzasıyla gruplandı. Sonuç: **her
pencerede top-5 imza, attack flow'ların %72-97'sini kapsıyor** —
window_02'de en uç örnek (%96.8, sadece 6 benzersiz imza / 126 flow):

| window | n_attack | n_unique_sig | top5_coverage |
|---|---|---|---|
| window_02_3pct | 126 | 6 | %96.8 |
| window_03_5pct | 214 | 12 | %85.5 |
| window_04_7pct | 304 | 15 | %82.9 |
| window_05_12pct | 550 | 23 | %76.7 |
| window_06_15pct | 712 | 38 | %73.0 |
| window_07_17pct | 826 | 39 | %73.2 |
| window_08_22pct | 1138 | 49 | %72.4 |

En baskın 2 imza her pencerede sabit: `tcp|none|REJ|dur=0.0|obytes=0`
(reddedilen portscan probe'ları) ve `tcp|http|SF|dur=0.0|obytes=80`
(hızlı tamamlanan kısa HTTP flow'ları) — bunlar tek başına attack
flow'ların ~%60-67'sini oluşturuyor. **Sonuç: attack flow'ların büyük
çoğunluğu, aynı otomatik araç aynı parametrelerle tekrar tekrar
çalıştırıldığı için, gerçek anlamda near-duplicate.** Bu ham split'te
(flow-bazlı rastgele) train/val/test arasında sızıntıya yol açar —
model "yeni bir attack flow'u" değil, "bu imzayı daha önce gördüm mü"yü
öğrenmiş olabilir.

### 2. Src/dst IP ve port çeşitliliği

- **Attack:** tek src IP (192.168.10.2, Dell — doğrulandı), tek dst IP
  (192.168.10.1), **189 benzersiz dst port** (nmap'in port taraması
  nedeniyle, pencere büyüdükçe tarama port aralığı da büyüyor — bkz.
  madde 3), 2602 benzersiz src port (SYN scan'in her deneme için yeni
  ephemeral port açması).
- **Benign:** tek src IP (192.168.10.3, Selenium/Locust makinesi), tek
  dst IP, sadece **3 benzersiz dst port** (80/http, 53/dns, 22/ssh),
  15.004 benzersiz src port.
- Port çeşitliliği pencere büyüdükçe artıyor (window_02: 22 port →
  window_08: 189 port) çünkü nmap'in port aralığı target_pct'e bağlı
  ölçekleniyor (madde 3'e bakınız) — bu, `id.resp_p`'nin dolaylı olarak
  window_id/target_pct ile korele olduğu, dolayısıyla eğer gelecekte
  dst_port feature'a eklenirse bunun window-bazlı bir "sızıntı kısayolu"
  olabileceği anlamına geliyor. Şu an dst_port feature setinde değil
  (NUMERIC_COLS'ta yok), bu yüzden mevcut riske katkısı yok, ama Faz 3
  sonrası feature genişletmesinde (bkz. 358. satırdaki IP-bazlı agregasyon
  TODO'su) dikkat edilmeli.
- Genel gözlem: hem attack hem benign trafik SADECE 2 makine arasında
  (Dell→Pi, Selenium/Locust makinesi→Pi) üretildiği için IP çeşitliliği
  ikisinde de sıfıra yakın (lab ortamının doğal sınırı) — bu açıdan
  attack/benign ayrımı yapılamıyor, ayrım tamamen davranışsal (conn_state,
  timing, byte oranları) feature'lardan geliyor.

### 3. Saldırı türü dağılımı (attack_orchestrator.py komutları, attack_log.csv'den)

Dell'deki `attack_orchestrator.py`'ye doğrudan erişilemedi (192.168.10.2
şu an SSH ile ulaşılamıyor/kapalı) — bunun yerine her pencerenin
`ground_truth/attack_log.csv`'si (cumulative olduğu için window_meta.json
start/end'e göre filtrelendi) referans alındı. Her pencerede tam olarak
6 komut çalıştırılıyor (portscan×2, apache_bench×2, slowloris×2) — 3
aracın da parametreleri **aynı tek bir `N` sayısıyla** target_pct'e göre
ölçekleniyor:

| window (target_pct) | N | nmap | apache_bench | slowloris |
|---|---|---|---|---|
| window_02 (3%) | 21 | `-p 1-21` | `-n 21 -c 21` | `-s 21` |
| window_05 (12%) | 92 | `-p 1-92` | `-n 92 -c 50` | `-s 92` |
| window_08 (22%) | 190 | `-p 1-190` | `-n 190 -c 50` | `-s 190` |

Yani 3 aracın da "şiddeti" tek bir ortak parametreyle birlikte artıyor
— pencereler arası target_pct farkı, araç-spesifik bir davranış farkı
değil, üç aracın da eşzamanlı ölçeklenmesi.

**Flow → araç ilişkilendirmesi** (conn.log ts'i attack_log.csv'deki
start/end aralığına düşürülerek yapıldı, 8 pencere toplamı):

| attack_type | n_flow | conn_state | byte_ratio (mean/median) | duration (mean/median) | unique dst_port |
|---|---|---|---|---|---|
| **portscan** | 3259 | SF:1294, REJ:1260, RSTO:683, S1:22 (karışık) | 44.0 / 0.032 | 6.4s / 0.026s | 189 |
| **apache_bench** | 404 | **RSTO: 404 (%100)** | 210.0 / 210.0 | 29.0s / 29.1s | 1 |
| **slowloris** | 207 | **RSTO: 207 (%100)** | 210.1 / 210.0 | 28.4s / 28.4s | 1 |

**Önemli bulgu:** flow-feature uzayında **apache_bench ve slowloris
neredeyse ayırt edilemez** — ikisi de tek hedef porta (80), tamamen
RSTO conn_state'inde, ~28-29 saniye süren, byte_ratio≈210 olan flow'lar
üretiyor (muhtemelen HTTP keep-alive/persistent-connection davranışı
nedeniyle her iki araç da Zeek'te "uzun süre açık kalıp sonra reset
edilen tek bir TCP flow" olarak görünüyor). Buna karşılık **portscan
kesin şekilde ayrışıyor**: çok kısa süreli (medyan 0.026s), çok yüksek
pkts/sec, karışık conn_state, geniş port dağılımı.

**Sonuç — "3 araç mı, genel anormallik mi" sorusuna kanıt:** Flow
seviyesinde model muhtemelen **3 değil, ~2 ayrışabilir küme**
öğrenecek: (a) "portscan-benzeri" (kısa, yüksek hacim, port-çeşitli) ve
(b) "uzun-RSTO-benzeri" (apache_bench+slowloris birleşik, tek port, ~29s,
byte_ratio~210). apache_bench/slowloris ayrımı flow-bazlı feature setiyle
büyük olasılıkla mümkün değil; bu ayrımı yapmak isterse Faz 3 sonrası
akış (flow) ötesi zaman-serisi/agregasyon feature'ları (bkz. 358. satır
TODO'su) gerekebilir. Not: attribution zaman-aralığı çakışmasına dayalı
olduğundan (bazı komutlar art arda/örtüşerek çalışıyor olabilir) küçük
bir yanlış-atama payı olabilir, ama genel örüntü (portscan ayrışık,
ab/slowloris örtüşük) güçlü ve tutarlı.

### 3.1. DÜZELTME (13 Temmuz 2026) — "apache_bench ≈ slowloris, ayırt
edilemez" sonucu GEÇERSİZ, muhtemelen attribution hatası

Yukarıdaki (596-624. satırlar, 11 Temmuz) "apache_bench ve slowloris
neredeyse ayırt edilemez" bulgusu, `IDS-Project/analysis/` altına
yazılan 3 doğrulama script'iyle (`attack_type_separability.py`,
`attack_type_attribution_validation.py`,
`attack_type_strict_boundary_check.py`) sınandı ve **muhtemelen bir
attribution (flow → araç eşleştirme) hatasının ürünü olduğu** ortaya
çıktı — gerçek bir flow-feature örtüşmesi değil.

**Kök neden:** Orijinal eşleştirme yöntemi ("conn.log ts'i attack_log
start/end aralığına düşürülerek yapıldı") ab.exe komutunun çok kısa
[start,end] aralığının (0.09-0.36s) ötesine, ab→slowloris arasındaki dar
(~0.4-0.46s) boşluğa taşmış ve o boşlukta beliren **gerçek slowloris
flow'larını apache_bench'e yanlış atamış**. Bu, 8 pencerenin TAMAMINDA
tutarlı bir örüntü olarak doğrulandı — ab bitişinden hemen sonraki
boşlukta beliren "uzun-RSTO" (~29s) flow sayısı, o pencerenin slowloris
`-s N` parametresiyle birebir eşleşiyor:

| window | ab bitişi sonrası uzun-RSTO (>10s) flow sayısı | slowloris `-s N` |
|---|---|---|
| window_02 (3%) | 21 | 21 |
| window_03 (5%) | 36 | 36 |
| window_04 (7%) | 51 | 51 |
| window_05 (12%) | 92 | 92 |
| window_06 (15%) | 119 | 119 |
| window_07 (17%) | 138 | 138 |
| window_08 (22%) | 190 | 190 |

Yani 599-603. satırlardaki tabloda apache_bench için verilen "n_flow=404,
RSTO %100, duration 29.0s/29.1s, byte_ratio 210.0" satırı, büyük
olasılıkla gerçek apache_bench flow'ları değil, **slowloris'in kendi
flow'larının bir kopyası/karışımı**.

**Gerçek apache_bench imzası (tolerans=0, katı zaman-aralığı
containment'ı ile, ham conn.log'a karşı doğrulandı):** `conn_state=SF`
(%100), süre **~0.04-0.05s**, hedef port 80 — yani slowloris'in
(`RSTO`, ~29s) imzasından **tamamen farklı**. Bu katı (strict) kümeyle
apache_bench vs slowloris ayrışabilirlik testi tekrarlandı: **AUC =
1.0000 ± 0.0000** (n=20 stratified split, Logistic Regression, mevcut
18 modelleme kolonuyla) — yani doğru attribution yapıldığında iki araç
**trivially ayrışıyor**, tam tersi doğru: model muhtemelen 3 saldırı
türünü de (2 değil) ayrı ayrı öğrenebilir.

**İLK SINIRLAMA (yazıldığında):** Strict (tolerans=0) yöntem, düşük-N
pencerelerde (window_02-05, N=21-92) apache_bench için **sıfır flow**
buluyordu — ab.exe komutu o kadar hızlı bitiyor ki hiçbir flow'un ts'i o
dar `[start,end]` aralığına denk gelmiyordu. Strict eşleşme ilk
denemede sadece window_06/07/08'de bulunmuştu (sırasıyla 9/7/20 flow,
toplam n=36), yani "AUC=1.0" sonucu ilk aşamada yalnızca **yüksek-N
(N≥119) senaryolarda doğrulanmıştı**; düşük-N pencerelerde apache_bench'in
flow-seviyesinde ayrışabilir olup olmadığı o an için **doğrulanmamıştı**
(veri yoktu, varsayım değildi).

**Bu sınırlama aynı gün (13 Temmuz 2026) içinde kapatıldı —
`attack_type_low_n_observation.py` ile düşük-N doğrulaması:** Strict
yöntemin düşük-N'de sıfır bulmasının nedeni araştırıldı: (a) saat kayması/
timestamp hassasiyeti mi, yoksa (b) apache_bench'in düşük-N'de gerçekten
ayrı flow üretmemesi mi (davranışsal kayıp)? Her düşük-N penceresinde
(02-05), apache_bench komutunun kendi `[start,end]` aralığının **±2
saniye çevresinde** (atama yapmadan, sadece gözlem amaçlı) port 80'e giden
TÜM flow'lar listelendi. Slowloris-benzeri (RSTO, >10s) flow'lar
çıkarıldıktan sonra kalan flow'larda, yüksek-N'deki imzayla (`conn_state=
SF`, `orig_bytes=80`, `resp_bytes≈2479`, süre <0.05s) **birebir örtüşen**
bir küme bulundu, sayısı da o pencerenin `ab -n N` parametresiyle eşleşti:

| window | ab -n N | ±2s gözlem penceresinde slowloris-benzeri (çıkarıldı) | kalan, orig_bytes=80 filtresiyle apache_bench imzalı flow |
|---|---|---|---|
| window_02 (3%) #1 | 21 | 21 | 21 |
| window_02 (3%) #2 | 21 | 21 | 21 |
| window_03 (5%) #1 | 36 | 36 | 36 |
| window_03 (5%) #2 | 36 | 36 | 36 |
| window_04 (7%) #1 | 51 | 51 | 51 (ilk taramada 66 çıkmıştı, `orig_bytes=80` filtresiyle 51'e indi — bkz. not) |
| window_04 (7%) #2 | 51 | 51 | 51 |
| window_05 (12%) #1 | 92 | 92 | 92 |
| window_05 (12%) #2 | 92 | 92 | 92 |

(Not — window_04 #1'deki 66→51 anomalisi doğrulandı: `conn_state=SF`
ve süre<1s filtresiyle bulunan 66 flow'un 15'i `orig_bytes` değeri 80
DEĞİL (1291/429/864/432/0 gibi, 3 kez tekrarlanan 5'li bir grup, farklı
`resp_bytes` — 8499/9757/12293/89015 aralığında), yani port 80'i
paylaşan benign HTTP navigasyon trafiği (Locust/Selenium personası)
olduğu doğrulandı; `orig_bytes=80` filtresi uygulanınca kalan tam 51,
diğer 7 örnekte olduğu gibi N'ye eşit.)

**Sonuç:** Düşük-N'de strict eşleşmenin sıfır çıkması, apache_bench'in
flow-seviyesinde görünmez/davranışsal olarak kaybolmasından değil,
sadece attack_log.csv'nin çok dar loglanan `[start,end]` penceresinin
(ab.exe'nin process bitiş anı ile gerçek TCP flow zaman damgaları
arasındaki küçük gecikme yüzünden) gerçek flow'ları kapsamamasından
kaynaklanıyordu — flow'lar davranışsal olarak zaten vardı ve N ile
sayıca birebir örtüşüyordu, geniş bir gözlem penceresiyle (atama
yapılmadan, sadece listeleyerek) doğrulandılar. **Yüksek-N'de bulunan
apache_bench imzası (SF, ~0.04-0.05s, `orig_bytes=80`, `resp_bytes≈2479`,
port 80) TÜM 8 pencerede (02-08) tutarlı** — "sadece yüksek-N'de
doğrulandı" çekincesi artık kapanmıştır.

**Genel sonuç (madde 3'ün güncel hali):** Orijinal "apache_bench ≈
slowloris, flow-seviyesinde ayırt edilemez" bulgusu, ab→slowloris
arasındaki dar (~0.4s) boşluğun ötesine taşan bir attribution hatasından
kaynaklanıyordu (gerçek slowloris flow'ları apache_bench'e yanlış
atanmıştı). Doğru (strict, tolerans=0) attribution ile, apache_bench
(SF, ~0.04-0.05s, orig_bytes=80/resp_bytes≈2479) ve slowloris (RSTO,
~29s, byte_ratio≈210) **mevcut 18 modelleme kolonuyla trivially
ayrışıyor** (AUC=1.0000±0.0000), ve bu artık TÜM N aralığında (21'den
190'a, 8 pencerenin tamamında) doğrulanmış durumda — yalnızca yüksek-N
senaryosuna özgü bir sonuç değil. Model muhtemelen 3 saldırı türünü de
(2 değil) flow seviyesinde ayrı ayrı öğrenebilir.

**Portscan ayrışabilirliği bulgusu ETKİLENMEDİ, hâlâ geçerli:** portscan
kendi [start,end] aralığında zaten ayrı bir imzaya sahip (karışık
conn_state, geniş port dağılımı, kısa süre) ve bu doğrulama sürecinde
apache_bench/slowloris sınırındaki hatadan bağımsız olarak teyit edildi
(control test AUC=0.9967±0.0011, tolerant eşleştirmeyle).

**Script konumları:** `IDS-Project/analysis/attack_type_separability.py`,
`IDS-Project/analysis/attack_type_attribution_validation.py`,
`IDS-Project/analysis/attack_type_strict_boundary_check.py`,
`IDS-Project/analysis/attack_type_low_n_observation.py` (dördü de
salt-okunur, features_all_windows/splits/models'e dokunmuyor).

### 4. Train/val/test split stratejisi önerisi (Faz 3 için, kod yazılmadı)

Yukarıdaki 3 bulguya dayanarak:

- **Flow-bazlı tamamen rastgele split ÖNERİLMEZ.** Madde 1'deki
  near-duplicate oranları (%72-97) nedeniyle rastgele split, neredeyse
  aynı imzaya sahip flow'ları train ve val/test arasında bölüştürür —
  bu klasik bir leakage biçimi (test seti, train'de "görülmüş" bir
  örüntünün kopyasını içerir), ölçülen performansı yapay olarak şişirir.
- **Önerilen yöntem: imza-bazlı gruplama + GroupShuffleSplit (veya
  eşdeğeri).** Madde 1'deki `proto|service|conn_state|duration(1
  ondalık)|orig_bytes(round10)` imzası (veya benzeri bir gruplama
  anahtarı) `group` olarak kullanılıp `sklearn.model_selection.
  GroupShuffleSplit` ile bölünmeli — aynı imzaya sahip TÜM flow'lar aynı
  sete (ya train ya val/test) düşmeli, asla ikisine birden değil. Bu,
  özellikle attack tarafında (madde 1'de risk doğrulandı) kritik; benign
  tarafında da aynı yöntem tutarlılık için uygulanabilir (ayrı analiz
  edilmedi ama benzer risk beklenir — Selenium/Locust'un da tekrarlayan
  session örüntüleri üretmesi muhtemel).
- **window_01_0pct (saf benign, istatistiksel sapan):** Autoencoder
  sadece benign veriyle eğitileceği için window_01'in TAMAMEN dışarıda
  bırakılması yerine, **train setine dahil edilip payının küçük
  tutulması** (547 flow, toplam benign'in ~%1.7'si — zaten payı küçük)
  makul. Ayrı bir "sapma testi" olarak window_01'in TAMAMI val/test'e
  ayrılıp reconstruction error'unun diğer 7 pencereden öğrenilen
  benign profiliyle ne kadar uyumlu çıktığı ölçülebilir — bu, modelin
  "benign genelleme" yeteneğini test eden faydalı bir ek deney olur
  (madde 4'teki sapma bulgusunun doğal bir kullanım alanı). Kesin karar
  Faz 3 mimarisi netleşince verilecek, şimdilik TODO.
- **Attack flow'ların hangi sette kullanılacağı:** Autoencoder standardına
  uygun olarak **attack flow'lar training'e hiç girmemeli** (sadece
  benign'e fit). Önerilen 3'e bölme:
  - **Train:** sadece benign flow'lar (imza-bazlı grup split'ten train
    payına düşenler).
  - **Val:** benign flow'ların bir kısmı (early stopping/hiperparametre
    için) + attack flow'ların bir kısmı (reconstruction-error eşiğini
    kalibre etmek için — eşik sadece benign'e bakılarak seçilirse
    gerçekçi olmaz, ama val'deki attack payı test'e sızmamalı, madde
    1'deki grup mantığıyla ayrılmalı).
  - **Test:** kalan benign + kalan attack flow'lar, nihai
    precision/recall/F1 raporlaması için, madde 1'deki conn_state naive
    baseline (precision %99.08, recall %66.56) ile karşılaştırılacak.
  Attack flow'ların val/test arasındaki bölünmesinde de imza-bazlı
  grup ayrımı (GroupShuffleSplit) uygulanmalı — aksi halde val'de
  görülen bir apache_bench/slowloris imzasının neredeyse birebir kopyası
  test'te tekrar çıkabilir (madde 3'teki bulgu: bu iki araç zaten kendi
  içinde çok homojen).

  > **NOT (13 Temmuz 2026):** Yukarıdaki "apache_bench/slowloris ayrımı
  > flow-bazlı feature setiyle büyük olasılıkla mümkün değil" varsayımı
  > (madde 3, 618-619. satırlar) **GEÇERSİZ** — bkz. **madde 3.1**
  > DÜZELTMESİ. Attack flow'ların GroupShuffleSplit ile grup-bazlı
  > ayrılması gerekliliği (imza homojenliği nedeniyle) hâlâ geçerli,
  > ama bu artık "zaten ayırt edilemeyen 2 araç" argümanına değil,
  > sadece imza tekrarına (near-duplicate) dayanıyor — 3 araç da
  > kendi içinde ayrı ayrı öğrenilebilir olabilir.

## 11 Temmuz 2026 — Faz 3 split stratejisi ve feature seti iyileştirmeleri uygulandı

Önceki bölümdeki (leakage/split değerlendirmesi) önerilerin somut
uygulaması. Yeni script: `faz3_split_dataset.py`.

### 1. İmza-bazlı gruplama + GroupShuffleSplit — UYGULANDI

`faz3_split_dataset.py` yazıldı: conn.log'u yeniden okuyup (Faz 2'yle
aynı sırada) `signature_key = window_id|proto|service|conn_state|
dur=round(duration,1)|obytes=round(orig_bytes,-1)` üretiyor,
`pd.factorize` ile `signature_id`'ye çeviriyor. `final` (features_all_
windows.parquet) ile `conn_all` arasında satır sırası hizalaması
assert'lerle doğrulandı (window_id/is_attack/ts birebir eşleşiyor).

`sklearn.model_selection.GroupShuffleSplit` ile (train_size/random_state
parametreleri script başında sabit tanımlı, ayarlanabilir):
- benign flow'lar (window_02-08) %70 train / kalan %30'un yarısı val
  yarısı test,
- attack flow'lar (train'e hiç girmiyor) %50 val / %50 test,
- benign-attack signature kümeleri arasında örtüşme kontrol edildi:
  **0 örtüşen imza** (benign_rest: 19.012 imza, attack_rest: 182 imza).

**Sonuç (window_01 hariç, madde 2'ye bakınız):**

| set | n_flow | %toplam | benign | attack | unique_signature |
|---|---|---|---|---|---|
| train | 23.220 | 63.26% | 23.220 | 0 | 13.513 |
| val | 6.334 | 17.26% | 4.308 | 2.026 | 2.943 |
| test | 6.890 | 18.77% | 5.046 | 1.844 | 2.943 |

(train oranı hedeflenen %70'ten %63.26'ya düştü çünkü window_01'in
yarısı ayrı bir kümeye - shift_test - gidiyor, train'e giren sadece
window_01'in diğer yarısı; bkz. madde 2)

**Leakage assertion:** train/val/test/window01_shift_test arasında
`signature_id` kesişimi için 6 ikili karşılaştırma yapıldı, **hepsi
boş küme** — hiçbir imza iki sette birden yok. Script bunu `assert`
ile garanti ediyor (koşum sırasında hata vermeden geçti).

Çıktı dosyaları: `IDS-Analysis/splits/{train,val,test}_indices.csv`,
her biri `row_index` (features_all_windows.parquet'teki 0-bazlı satır
sırası), `window_id`, `is_attack`, `signature_id`, `ts` kolonlarını
içeriyor — Faz 3'te `features_all_windows.parquet.iloc[row_index]` ile
doğrudan kullanılabilir.

### 2. window_01 stratified yaklaşımı — UYGULANDI

window_01_0pct'in 547 flow'u, kendi içinde signature-bazlı gruplanıp
`GroupShuffleSplit(train_size=0.5)` ile ikiye bölündü:
- **286 flow** ana train setine eklendi (410 benzersiz imzanın
  yaklaşık yarısı),
- **261 flow** `splits/window01_shift_test.csv`'ye ayrı kaydedildi —
  bu küme normal train/val/test'in TAMAMEN dışında, ana split'e hiç
  karışmıyor.

Amaç (context.md'deki önceki karara uygun): Faz 3'te modelin
reconstruction error'u önce normal test setinde, sonra ayrıca
`window01_shift_test`'te ölçülüp karşılaştırılacak — window_01'in
diğer 7 pencereden istatistiksel sapması (duration CV=0.37, bkz. 11
Temmuz EDA notu) nedeniyle bu, modelin "görmediği ama yine de benign"
bir dağılıma ne kadar genelleyebildiğini test eden ek bir deney.

### 3. Persona feature kontrolü — MÜMKÜN DEĞİL, kod değişikliği yapılmadı

`locust_nav_log.csv` (persona, session_id, timestamp, response_time_ms)
ve `selenium_nav_log.csv`/`selenium_session_log.csv` (persona,
thread_label/session_id, epoch, page) incelendi. Flow-level persona
attribution'ın neden GÜVENİLİR yapılamadığı:

- **Granularity uyuşmazlığı:** window_02 örneğinde 3.286 benign HTTP
  flow'una karşılık 14.623 locust nav-log satırı var — flow başına
  ortalama **4.45 nav-event** (HTTP keep-alive/connection-pooling
  nedeniyle tek bir TCP flow onlarca sayfa isteğini taşıyor). Yani
  conn.log FLOW (bağlantı) seviyesinde, nav_log ise REQUEST (sayfa
  görüntüleme) seviyesinde - 1:1 eşleme yok.
- **Ortak IP, port korelasyonu yok:** Hem Selenium hem Locust AYNI
  kaynak IP'den (192.168.10.3) geliyor; window_02'de 30 eşzamanlı
  Locust session'ı + yüzlerce Selenium thread'i (366 session)
  aynı anda çalışıyor. nav_log dosyaları src port bilgisi TUTMUYOR
  (sadece timestamp+persona+session_id), conn.log ise src port'u
  tutuyor ama hangi session_id/persona'ya ait olduğunu tutmuyor —
  iki log arasında ortak bir anahtar (port, cookie, vs.) yok.
- **Zaman-penceresi eşleştirmesi güvenilmez:** Onlarca persona eşzamanlı
  çalıştığı için, bir flow'un aktif olduğu zaman aralığında birden çok
  FARKLI persona'nın nav-event'i çakışabiliyor — sadece timestamp
  overlap'ine dayanan bir eşleştirme, flow'u yanlış personaya atama
  riski taşır (gürültülü/güvenilmez etiket).

**Sonuç:** `faz2_feature_extraction.py`'ye persona feature'ı EKLENMEDİ.
Bu, benign trafiğin gerçek çeşitliliğinin (persona karışımı) feature
setinde yakalanamadığı anlamına geliyor — mevcut feature seti sadece
ağ-seviyesi davranışı (byte/paket sayıları, conn_state, timing)
kullanıyor, uygulama-seviyesi (hangi sayfa, hangi kullanıcı tipi)
bilgiyi kullanmıyor. İleride bu çözülmek istenirse, Locust/Selenium
tarafında istemci local port'unun nav_log'a loglanması (kod
değişikliği - veri toplama tarafında, gelecekteki capture'lar için)
gerekir; mevcut 8 pencerenin verisiyle retroaktif olarak güvenilir
şekilde yapılamaz.

### 4. conn_state ablation planı — dokümantasyon (Faz 3'te uygulanacak, henüz YAPILMADI)

Faz 3'te autoencoder **iki kere** eğitilecek:
- **(a) Tam feature seti** (mevcut 22 kolon: 8 sayısal scaled +
  10 one-hot [proto/service/conn_state] + is_attack/actual_attack_pct/
  window_id/ts meta kolonları).
- **(b) conn_state one-hot kolonları çıkarılmış feature seti**
  (`conn_state_REJ, conn_state_RSTO, conn_state_S1, conn_state_SF`
  hariç, geri kalan 18 kolon).

İki modelin reconstruction error'unun benign/attack ayrım gücü
(AUC veya eşdeğer bir metrik) karşılaştırılacak. Amaç: madde 1'deki
naive baseline bulgusuyla (conn_state tek başına %99 precision/%66.6
recall veriyor, bkz. 11 Temmuz EDA notu) bağlantılı olarak, tam
feature setiyle eğitilen autoencoder'ın conn_state'e ne kadar
"kısayoldan" dayandığını ölçmek — eğer (b) modeli (a)'ya yakın
performans gösteriyorsa, model conn_state ötesinde gerçek sinyal
öğreniyor demektir; eğer (b) modeli çok daha kötü performans
gösteriyorsa, mevcut ayrım gücünün büyük kısmı tek bir kategorik
kolondan geliyor demektir ve bu, feature setinin zenginleştirilmesi
(örn. 358. satırdaki IP-bazlı zaman-penceresi agregasyonu TODO'su)
gerekliliğine işaret eder. Bu deney henüz kodlanmadı, Faz 3
mimarisiyle birlikte uygulanacak.

## 11 Temmuz 2026 — Faz 3 öncesi son düzeltmeler: scaler leakage fix + split stabilite testi

### 1. Scaler leakage düzeltmesi — en kritik, UYGULANDI

**Sorun:** Önceki pipeline sırası yanlıştı — `faz2_feature_extraction.py`
StandardScaler'ı TÜM 8 pencerenin benign verisine fit ediyordu, split
(`faz3_split_dataset.py`) bundan SONRA, ayrı bir script'te yapılıyordu.
Yani scaler, val/test'e düşecek benign flow'ların dağılımını da görerek
fit edilmiş oluyordu — klasik bir leakage.

**Düzeltme:** `faz2_feature_extraction.py` ve `faz3_split_dataset.py`
**tek bir pipeline'da birleştirildi** (artık sadece
`faz2_feature_extraction.py` var, `faz3_split_dataset.py` silindi — git'e
hiç commit edilmemişti, kayıp yok). Yeni sıra:
1. conn.log'lardan `conn_all` + `signature_id` üretilir (değişmedi).
2. `GroupShuffleSplit` ile train/val/test'e ayrılır (mantık aynı: train
   sadece benign, val/test benign+attack, signature-bazlı ayrık —
   önceki bölümdeki tasarım korundu).
3. **StandardScaler SADECE train split'ine fit edilir** (train zaten
   tamamen benign, çünkü split adımı bunu garanti ediyor).
4. `transform()` train+val+test+window01_shift_test'in TAMAMINA uygulanır.
5. OneHotEncoder hâlâ global fit (kasıtlı, değişmedi).

**Leakage büyüklüğü — eski vs yeni scaled değerler (aynı split'e göre
gruplanmış):**

| kolon | split | eski mean | yeni mean | eski std | yeni std |
|---|---|---|---|---|---|
| duration_scaled | train | -0.0113 | **0.0000** | 0.9533 | 1.0000 |
| orig_bytes_scaled | train | -0.0081 | **0.0000** | 0.9773 | 1.0000 |
| byte_ratio_scaled | train | 0.0224 | **0.0000** | 1.0506 | 1.0000 |
| pkts_per_sec_scaled | train | 0.0283 | **0.0000** | 1.0765 | 1.0000 |

Yeni scaler'da train mean **tam olarak 0**, std **tam olarak 1**
(matematiksel garanti — scaler zaten bu veriye fit edildi). Eski
scaler'da train alt kümesi bile tam 0/1'e oturmuyordu çünkü fit,
train+val+test benign'inin BİRLİĞİNE yapılmıştı — val/test'teki benign
flow'lar train'in istatistiklerini hafifçe kaydırıyordu. Mutlak fark
küçük görünüyor (örn. 0.01-0.03 birim) ama bu **tam olarak leakage'ın
niceliği** — model, val/test'te "görmemesi gereken" bir istatistiksel
bilgiden (o flow'ların ortalama/varyansa katkısından) hafifçe
faydalanıyordu. Düzeltme sonrası train tamamen kendi kendine yetiyor,
val/test/window01_shift_test'in scaled ortalamaları artık 0'dan
belirgin şekilde sapıyor (örn. yeni `byte_ratio_scaled`: val
mean=154.16, test mean=144.26, window01_shift_test mean=0.22) — bu
sapma BEKLENEN ve DOĞRU davranış (val/test'in benign+attack karışımı,
train'in saf-benign dağılımından farklı istatistiklere sahip olmalı).

`features_all_windows.csv/parquet`, `by_window/*` ve
`splits/{train,val,test}_indices.csv` + `splits/window01_shift_test.csv`
yeniden üretildi (tek `python3 faz2_feature_extraction.py` çalıştırması
ile, artık split+scale doğru sırada aynı script içinde).

### 2. Pencere temsiliyeti kontrolü — RİSK bulundu, kod değişikliği yapılmadı (sadece not)

Pencere x split kırılımı (resmi seed=1, aşağıda madde 3'te açıklanıyor):

| window | train (benign) | val (benign/attack) | test (benign/attack) | shift_test |
|---|---|---|---|---|
| window_01_0pct | 273 | - | - | 274 |
| window_02_3pct | 2806 | 490/49 | 682/77 | - |
| window_03_5pct | 2843 | 514/108 | 609/106 | - |
| window_04_7pct | 3266 | 631/66 | 576/238 | - |
| window_05_12pct | 3007 | 770/265 | 614/285 | - |
| window_06_15pct | 3544 | 574/358 | 889/354 | - |
| window_07_17pct | 3828 | 841/160 | 621/666 | - |
| window_08_22pct | 3707 | 789/**961** | 687/**177** | - |

**Flag: window_08'in attack flow'ları val ve test arasında ÇOK
dengesiz dağılmış** — val'de 961 attack flow'a karşılık test'te sadece
177 (yaklaşık 5.4:1 oran). window_07'de bunun neredeyse tersi bir eğilim
var (val:160, test:666, ~1:4.2 oran, test lehine). Bu, signature-bazlı
grup split'in DOĞASINDAN kaynaklanıyor — bir pencerede birkaç büyük
signature grubu (örn. tek bir nmap taramasının ürettiği onlarca
neredeyse-özdeş flow) rastgele ya val'e ya test'e düşüyor, o pencerenin
attack dağılımını tek yönde çekiyor. **Risk:** eşik kalibrasyonu (val)
ve nihai değerlendirme (test) arasında pencere-bazlı attack yoğunluğu
tutarsızlığı varsa, örn. window_08'in yüksek-attack-pct karakteri
esas olarak val'de temsil ediliyor, test'te yetersiz temsil ediliyor —
bu, test setindeki performansın window_08'in gerçek zorluk seviyesini
tam yansıtmayabileceği anlamına gelir. Kod değişikliği yapılmadı (madde
3'teki çoklu-seed sonuçlarına göre bu, TÜM seed'lerde az çok var olan
bir yapısal özellik, tek bir "düzeltme" yok) — Faz 3'te sonuç
yorumlanırken pencere-bazlı (window_id ile gruplanmış) ayrı
metrikler de raporlanması ÖNERİLİR, sadece agregat val/test metriğine
güvenilmemeli.

### 3. Çoklu-seed varyans testi — UYGULANDI, "split instabilitesi" riski doğrulandı

`GroupShuffleSplit` seed=0,1,2,3,4 için tekrarlandı:

| seed | train_n | val_n | val_attack% | test_n | test_attack% | balance_score |
|---|---|---|---|---|---|---|
| 0 | 22.476 | 7.106 | 27.60% | 6.857 | 27.84% | 0.0378 |
| **1** | **23.274** | **6.576** | **29.91%** | **6.581** | **28.92%** | **0.0285 (min)** |
| 2 | 23.526 | 6.299 | 28.13% | 6.609 | 31.74% | 0.0333 |
| 3 | 22.489 | 7.083 | 30.98% | 6.837 | 24.51% | 0.0322 |
| 4 | 22.956 | 6.645 | 30.81% | 6.828 | 26.70% | 0.0317 |

**Std (5 seed arası):** train_n std=467 (~%2 varyasyon), val_n
std=347, test_n std=135, val_attack% std=1.54 puan, test_attack% std=2.68
puan. Mutlak sayılarda büyük olmayan ama **göz ardı edilemeyecek** bir
varyans var — özellikle test_attack_pct seed'e göre %24.5-%31.7 arasında
değişiyor (~7 puanlık aralık), bu da tek bir seed'le ölçülen
precision/recall/AUC'nin şansa bağlı olarak biraz iyimser ya da
kötümser çıkabileceği anlamına geliyor.

**"Split instabilitesi" riski olarak not:** Faz 3'te nihai sonuçlar
**tek bir sayı olarak DEĞİL, birden fazla seed'in ortalama±std'si
olarak raporlanmalı** (örn. "AUC = 0.91 ± 0.02, 5 seed üzerinden").
Özellikle madde 2'deki pencere-bazlı dengesizlik (window_08 val/test
attack oranı) her seed'de farklı şekilde ortaya çıkabilir, bu yüzden
tek-seed sonuçlarına dayanan bir "model şu pencerede kötü performans
gösterdi" yorumu güvenilir olmayabilir.

**Resmi split için seçilen seed: seed=1** — 5 aday arasında en düşük
`balance_score`'a sahip (pencere başına train-fraksiyonunun genel
ortalamadan en az saptığı seed, bkz. script'teki `balance_score`
hesaplaması). `splits/{train,val,test}_indices.csv` ve
`window01_shift_test.csv` bu seed ile üretildi ve kaydedildi. Not:
"en dengeli train fraksiyonu" kriteri madde 2'deki val/test-arası
attack dağılım dengesizliğini garanti etmiyor (farklı bir metrik) —
seed=1 bu açıdan mükemmel değil (window_08 sorunu seed=1'de de var),
ama 5 aday arasında genel olarak en tutarlı pencere temsiliyetini
veriyor.

## 11 Temmuz 2026 — Faz 3: Autoencoder eğitimi ve ablation sonuçları

Yeni script: `faz3_autoencoder.py`. Mac üzerinde (Pi'de değil) çalıştırıldı.
**Not:** buradaki "seed=0..4" model ağırlık-başlatma (weight init)
seed'leri, önceki bölümdeki split seed'inden (resmi split=1, veri
bölme aşamasında kullanıldı) BAĞIMSIZ bir seed uzayı — split sabit
(seed=1, `splits/` klasöründeki dosyalar), sadece model eğitimi 5 kere
farklı ağırlık başlatmayla tekrarlandı.

### 0. Ortam kontrolü

TensorFlow kurulu değildi, kuruldu: **TensorFlow 2.21.0** (Apple
Silicon, arm64). `tensorflow-metal` 1.2.0 de kuruldu ama **uyumsuz
çıktı** — `dlopen(...libmetal_plugin.dylib...)` hata: `Library not
loaded: @rpath/_pywrap_tensorflow_internal.so` (tensorflow-metal 1.2.0,
TF 2.21.0 ile derlenmemiş/uyumsuz). `tensorflow-metal` kaldırıldı,
**CPU-only** çalışıldı — veri seti küçük (train~23K satır) ve model
küçük (3 gizli katman, ≤32 nöron) olduğu için GPU gerekmedi, her
seed'in eğitimi 2.5-6.7 saniye sürdü (CPU'da bile).

### 1. Veri yükleme

`splits/{train,val,test}_indices.csv` (resmi split, seed=1) +
`features_all_windows.csv` kullanıldı. `row_index` ile `features_all_
windows.csv`'nin ilgili satırları seçildi. Doğrulama:
- train=23.274 satır, **train'de is_attack==0 assert'i geçti** (hepsi
  benign).
- val=6.576 (benign=4.609, attack=1.967), test=6.581 (benign=4.678,
  attack=1.903) — 11 Temmuz'daki split raporuyla birebir uyumlu.
- Feature kolonları: meta kolonlar (`is_attack, actual_attack_pct,
  window_id, ts`) hariç tutuldu, tam feature setinde **18 kolon**
  (8 scaled sayısal + 10 one-hot), ablation setinde **14 kolon**
  (conn_state'in 4 one-hot kolonu çıkarıldı).

### 2. Mimari ve eğitim

`Input(N) → Dense(16, relu, L2=1e-4) → Dropout(0.15) → Dense(8, relu,
L2=1e-4, bottleneck) → Dropout(0.15) → Dense(16, relu, L2=1e-4) →
Dense(N, linear)`, loss=MSE, optimizer=Adam, batch_size=128,
max_epochs=200, `EarlyStopping(monitor=val_loss, patience=12,
restore_best_weights=True)`. **val_loss SADECE val'deki benign
flow'lardan** hesaplandı (val'deki attack flow'lar loss izlemeye hiç
girmedi, sadece sonraki eşik kalibrasyonu adımında kullanıldı — istenen
tasarım). 5 seed (0-4) ile sıfırdan eğitildi, her model
`models/{variant}/autoencoder_seed{N}.keras` olarak kaydedildi (10
model toplam, ~460K disk).

**Eğitim süresi ve epoch sayısı (full_features, 5 seed):** ortalama
4.5s ± 1.45s, ortalama 41 ± 15.6 epoch (early stopping erken devreye
giriyor, min 20 - max 64 epoch arası, seed'e bağlı varyans var ama
mutlak süre önemsiz küçük).

### 3-4. Eşik kalibrasyonu, test değerlendirmesi ve ablation — 5-seed özet

| metrik | full_features (18 kolon) | no_conn_state (14 kolon) | delta |
|---|---|---|---|
| **test AUC** | 0.9463 ± 0.0104 | 0.9341 ± 0.0126 | +0.0122 |
| pctl95 eşik: precision | 0.9353 ± 0.0181 | 0.9460 ± 0.0255 | -0.0107 |
| pctl95 eşik: recall | 0.8002 ± 0.0023 | 0.7956 ± 0.0000 | +0.0046 |
| pctl95 eşik: **F1** | **0.8624 ± 0.0068** | **0.8641 ± 0.0107** | **-0.0017** |
| pctl95 eşik: accuracy | 0.9261 ± 0.0044 | 0.9276 ± 0.0067 | -0.0015 |
| youden eşik: precision | 0.5951 ± 0.0441 | 0.6590 ± 0.1728 | -0.0639 |
| youden eşik: recall | 0.9995 ± 0.0011 | 0.9554 ± 0.0805 | +0.0441 |
| youden eşik: F1 | 0.7451 ± 0.0351 | 0.7591 ± 0.0680 | -0.0140 |

**Naive baseline (conn_state != SF, 11 Temmuz notu):** precision=0.9908,
recall=0.6656, F1=0.7963.

**Autoencoder vs naive baseline:** `full_features` + pctl95 eşiği
**F1=0.8624 > naive F1=0.7963** — autoencoder baseline'ı geçiyor,
kazanç esas olarak recall'dan geliyor (0.80 vs 0.6656), precision'da
naive'e göre biraz geriliyor (0.935 vs 0.9908, beklenir - naive kural
tek bir çok-ayırt-edici kolona dayandığı için neredeyse hiç yanlış
alarm vermiyordu). Youden eşiği çok farklı bir çalışma noktası veriyor
(precision çöküyor, recall ~1.0'a çıkıyor) - ROC-optimal nokta, dengesiz
sınıf oranında (test'te attack ~%29) precision'ı feda ediyor; Faz 3
sonrası üretim eşiği seçilirken pctl95 daha kullanışlı bir başlangıç
noktası.

**Ablation yorumu — "model conn_state'e bağımlı mı, gerçek sinyal mi
öğreniyor" sorusuna kanıt:** Fark **küçük**: test AUC'de +0.0122 (tam
feature seti lehine, ama std'lerin (0.0104/0.0126) içinde kalan bir
fark), F1'de pctl95 eşiğinde -0.0017 (yani conn_state'siz model
pctl95'te AÇIKÇA DAHA KÖTÜ DEĞİL, istatistiksel gürültü
seviyesinde). **Sonuç: model conn_state'e "kısayoldan" dayanmıyor** -
conn_state olmadan da neredeyse aynı ayrım gücünü koruyor, bu da
diğer feature'ların (özellikle 11 Temmuz EDA'sında işaret edilen
pkts_per_sec ve byte_ratio - attack flow'ların ~%33'ünün bu ikisinde
|z|>3 olduğu bulunmuştu) gerçek, bağımsız bir anomali sinyali taşıdığını
doğruluyor. Bu, conn_state naive baseline'ının (madde 3'te karşılaştırma)
sadece "kolay" bir alt küme yakaladığı, autoencoder'ın ise daha geniş bir
davranış örüntüsü öğrendiği hipotezini destekliyor.

### 5. Dosyalar

- `IDS-Analysis/models/{full_features,no_conn_state}/autoencoder_seed{0-4}.keras`
  (10 model)
- `IDS-Analysis/results/{full_features,no_conn_state}/seed{0-4}_metrics.json`
  (her seed için ayrıntılı metrik + kullanılan eşik değerleri)
- `IDS-Analysis/results/{full_features,no_conn_state}_summary.json`
  (5-seed mean±std)
- `IDS-Analysis/results/ablation_comparison.json` (iki varyantın + naive
  baseline'ın yan yana karşılaştırması)

**Hata/uyarı:** `tensorflow-metal` kurulum/uyumluluk hatası dışında
(madde 0'da açıklandı, GPU'suz devam edildi) eğitim ve değerlendirme
sırasında hiçbir hata/uyarı alınmadı, 10 model de sorunsuz eğitildi ve
kaydedildi.

**Faz 3 sonrası TODO:** Şu ana kadarki sonuçlar minimal end-to-end
pipeline'ın (context.md'nin "TODO — IP-Bazlı Zaman-Penceresi
Agregasyonu" bölümünde tarif edilen 1. adım) tamamlandığını gösteriyor
— autoencoder naive baseline'ı geçiyor ve conn_state'e aşırı bağımlı
değil. Sıradaki adım o TODO'nun 2. maddesindeki IP-bazlı zaman-penceresi
agregasyon feature'larının (conn_count_60s, unique_dst_ports_60s vb.)
eklenip eklenmeyeceğine karar vermek - mevcut sonuçlar (AUC~0.95) zaten
güçlü olduğu için bu ek karmaşıklığın gerekliliği tartışılmalı.

## 11 Temmuz 2026 — Desktop konsolidasyonu, notebook dönüşümü ve GitHub'a yayınlama

Faz 3 sonrası, proje dosyalarının Desktop'ta dağınık durması (IDS-Analysis,
ids-dataset-raw-backup, ids-dataset-features, selenium-bot, locust, çeşitli
log/rapor dosyaları ayrı ayrı Desktop kökünde) nedeniyle birkaç turluk bir
yeniden organizasyon ve temizlik süreci yürütüldü.

### Review paketleri (Faz3-Review, IDS-Project) ve konsolidasyon

Önce `Faz3-Review/` adlı bir inceleme paketi oluşturuldu (split/model/metrik
kopyaları + `00_REPORT.md`), ardından daha kapsamlı `IDS-Project/` paketi
(Faz 1-2-3'ün tamamını kapsayan, `explore_results.ipynb` adlı bir keşif
notebook'u dahil). `Faz3-Review` içeriğinin `IDS-Project` ile birebir
(md5 checksum ile doğrulanmış) çakıştığı tespit edildi — tek farkı stale bir
`context.md` kopyasıydı. Kullanıcı onayıyla `Faz3-Review` silindi.

### Desktop'ın tek klasörde toplanması: IDS-Internship → NIDS

Kullanıcı talebiyle tüm IDS-ilişkili klasörler (IDS-Analysis, IDS-Project,
ids-dataset-raw-backup, ids-dataset-features, selenium-bot, locust,
window_run_logs, log dosyaları) tek bir kök altında toplandı. İsimlendirme
birkaç kez değişti (kullanıcı Finder'dan paralel müdahalelerle bazı klasör
isimlerini kendi tercihine göre değiştirdi — örn. "veri"→"data",
"diğer"→"others"): nihai hal `~/Desktop/NIDS/` — üç alt klasör:

- `NIDS/IDS-Project/` — kanonik, temiz proje (kod + veri + Faz 1-3 çıktıları
  bir arada, kullanıcının "amacım bu dosyayı Cursor'dan açıp incelemek"
  isteğine uygun tek workspace).
- `NIDS/IDS-Analysis/` — tarihsel git repo (context.md, ANALYS-BENIGN,
  archive, captures/, pcap_to_csv.py kaldı; faz2/faz3 kodu ve canlı
  model/split/sonuç çıktıları IDS-Project'e taşındı).
- `NIDS/data/` — ham capture backup + Faz 2 feature çıktısı.

Ayrıca `~/Desktop/Docs/` klasörü: rapor PDF'leri, `.sh` orkestrasyon
script'leri (`run_all_windows.sh`, `collect_window.sh`,
`capture_multiple_runs.sh`), log dosyaları, ve `selenium-bot`/`locust`
kaynak kodu için ayrıldı (kod olmayan destekleyici materyal).

Her taşıma turunda script'lerdeki hardcoded `~/Desktop/...` path'leri
(`faz2_feature_extraction.py`, `faz3_autoencoder.py`, `.sh` dosyaları)
yeni konumlara göre güncellendi ve her seferinde path'lerin gerçekten var
olduğu + script'lerin syntax/çalışma açısından sağlam olduğu doğrulandı.

### Faz 3 script'i notebook'a dönüştürüldü

Kullanıcı "Faz 3'ü normalde ipynb şeklinde yapmıyor muyduk" diye sorunca,
`faz3_autoencoder.py` tamamen silindi, yerine `IDS-Project/
phase3_autoencoder.ipynb` geldi: model kurma, deneysel tek-model eğitimi
(kayıp eğrisi görselleştirmesiyle), tam 5-seed × 2-varyant taraması, eşik
kalibrasyonu, reconstruction error histogramı, ROC eğrisi, ablation
karşılaştırması, özet tablo — hepsi hücre hücre. Eski `explore_results.ipynb`
de silindi (yeni notebook'un yaptığı her şeyi zaten kapsıyordu, iki çakışan
notebook tutmak istenmiyordu). `faz2_feature_extraction.py`'ye dokunulmadı
(Faz 2 = "dataset öncesi", kullanıcının notebook isteği "dataset sonrası"
içindi).

**Faz 3 klasörlerinin "temiz" tutulması kararı:** kullanıcı `03_phase3_splits/`,
`04_phase3_models/`, `05_phase3_results/`'ın proje açıldığında BOŞ olmasını,
sadece notebook çalıştırıldığında dolmasını istedi. Bu klasörlerin içeriği
silindi; doğru çalıştırma sırası netleştirildi: önce
`faz2_feature_extraction.py` (veri + split üretir — leakage-free scaling
split-önce-scale gerektirdiği için split zaten Faz 2 script'inin bir
parçasıydı), sonra `phase3_autoencoder.ipynb` (split'i okuyup eğitir).
Bu akış sıfırdan iki kez uçtan uca test edildi (`nbconvert --execute`),
her seferinde hatasız ve önceki sonuçlarla birebir aynı (AUC=0.9463±0.0104)
çıktı üretildi.

### Okunabilir model dosyaları

Kullanıcı `.keras` dosyalarının (zip/binary format, editörde okunamıyor)
"kera şeklinde json şeklinde" okunabilir olmasını istedi. Her `.keras`
dosyasının yanına `.json` (mimari, `model.get_config()`'ten) ve
`_readable.txt` (katman-katman özet, `model.summary()` + aktivasyon/output
shape/parametre dökümü) üretildi — önce ayrı bir script olarak, sonra
notebook'un kalıcı bir hücresi olarak (her çalıştırmada otomatik üretilsin
diye).

### "Her şey İngilizce olacak" kuralı

Kullanıcı iki kez açıkça belirtti: bundan sonra üretilen tüm dosyalar
(script, notebook, rapor) İngilizce olacak, hafızaya kalıcı feedback olarak
kaydedildi (`~/.claude/projects/-Users-mustafa/memory/
feedback_english_only.md`). Bu kural uyarınca `phase3_autoencoder.ipynb`
tamamen İngilizce yeniden yazıldı (daha önce Türkçe yazılmıştı), ve
GitHub'a push öncesi `faz2_feature_extraction.py`'deki kalan Türkçe
metinler (docstring, print, rapor satırları) İngilizce'ye çevrildi —
her çeviri sonrası script/notebook yeniden çalıştırılıp aynı sonuçları
verdiği doğrulandı. **Bu kuralın istisnaları** (kullanıcı özellikle
belirttiğinde): PDF dokümantasyon raporu (bkz. altta) ve bu `context.md`
dosyasının kendisi — ikisi de bilinçli olarak Türkçe tutuluyor.

### GitHub'a yayınlama

`IDS-Project/` (22M, 69 dosya — kod, feature matrisi, split'ler, 10 model
+ okunabilir kopyaları, tüm sonuç JSON'ları) için git repo başlatıldı,
`.gitignore` eklendi (`.DS_Store`, `__pycache__`, `.ipynb_checkpoints`),
ve **public** bir GitHub reposuna push edildi:
**github.com/mustafag63/DL-Based-NIDS**. Repo, kullanıcının GitHub
hesabında (`mustafag63`, `gh` CLI ile önceden authenticate edilmiş) zaten
oluşturulmuştu (boş), sadece içerik push edildi. Repo tamamen İngilizce ve
kendi kendine yeten — `faz2_feature_extraction.py` sonra
`phase3_autoencoder.ipynb` çalıştırılarak pipeline sıfırdan tekrar
üretilebilir.

### PDF dokümantasyon raporları

Kullanıcı için projenin tamamını (Faz 1-2-3, dosya dosya açıklama,
kronolojik özet, güncel durum) anlatan bir PDF rapor hazırlandı.
`weasyprint` sistem kütüphanesi eksikliği nedeniyle (Homebrew'dan `pango`
gerekiyordu, kurulu değildi) kullanılamadı; `reportlab` ile doğrudan
üretildi. Önce İngilizce versiyon `IDS-Project/
NIDS_Project_Documentation.pdf` olarak kaydedildi (10 sayfa). Kullanıcı
dosyayı kendi Desktop köküne taşıdı ve "bu seferlik sadece bunu Türkçe
istiyorum" dedi — Türkçe versiyon aynı yola (`~/Desktop/
NIDS_Project_Documentation.pdf`) yazıldı. **Font sorunu:** reportlab'ın
varsayılan Helvetica fontu Türkçe genişletilmiş Latin karakterlerini
(ı, ğ, ş, ü, ö, ç) desteklemiyordu, ilk üretimde bu karakterler siyah kare
olarak çıktı. Sistemdeki Arial + Courier New TTF fontları
(`/System/Library/Fonts/Supplemental/`) `registerFont`/
`registerFontFamily` ile kaydedilip kullanılarak düzeltildi, `pdftoppm`
ile sayfalar render edilip görsel olarak doğrulandı.

### Şu anki durum (11 Temmuz 2026 sonu itibariyle)

- **Kanonik proje:** `~/Desktop/NIDS/IDS-Project/` (yerel) =
  `github.com/mustafag63/DL-Based-NIDS` (uzak, public).
- **Çalıştırma sırası:** `faz2_feature_extraction.py` → `phase3_autoencoder.ipynb`
  (Faz 3 klasörleri bilinçli olarak boş tutuluyor, her çalıştırmada
  yeniden üretiliyor).
- **`context.md`** artık `~/Desktop/context.md`'de duruyor (kullanıcı
  isteğiyle taşındı) ve Türkçe kalmaya devam ediyor — genel "her şey
  İngilizce" kuralının bilinçli istisnası.
- **`Faz3-Review`** silindi (yukarıda).
- Açık TODO'lar değişmedi: IP-bazlı zaman-penceresi agregasyon feature'ları
  (eklenip eklenmeyeceği tartışılacak), persona-seviyesi feature'lar
  (flow-level'de güvenilir attribution mümkün değil, feature setine
  girmedi), `window01_shift_test` kümesi henüz eğitilmiş modellere karşı
  değerlendirilmedi.

## 15 Temmuz 2026 — Gérard toplantısı, window_10 temiz capture, phase3_dense/
phase3_vae ayrımı, VAE sağlık kontrolü ve posterior collapse düzeltmesi

### Toplantı sonucu ve yeni görevler

Gérard mevcut ilerlemeyi (Faz 1-3, Dense autoencoder AUC≈0.9463) beğendi.
Belirlenen yeni görevler:

1. **Ek temiz (benign-only) capture** — mevcut `window_01_0pct` sadece 547
   flow içeriyordu (diğer window'lardaki 4-5k'ya kıyasla az) çünkü Zeek
   capture'ın pencere başlangıcından geç başlaması yüzünden anormal kısa
   sürmüştü (bkz. 9 Temmuz notları). Çözüm: `window_01`'i değiştirmek
   yerine, standart 60dk (50+10dk safety margin) süreyle ayrı bir temiz
   pencere daha almak.
2. **Autoencoder → VAE (Variational Autoencoder)** geçişi.
3. **Cuma'ya kadar karar verilecek açık soru:** yeni VAE train'i sadece
   temiz veriyle mi yapılsın, yoksa temiz + düşük kirlilikli window'ların
   karışımıyla mı — deneysel olarak karşılaştırılıp karar verilecek.
   Kullanıcının netleştirmesiyle: önce temiz-only VAE'nin sağlıklı ve
   doğru şekilde çalıştığı garanti altına alınacak, kirli/karışık deneyi
   ancak ondan sonra ele alınacak.

### window_10_0pct — yeni temiz capture (window_01'in yerine değil, ek olarak)

Kullanıcı kararı: yeni capture `window_01`'in yerini almayacak, ayrı bir
pencere (`window_10_0pct`, `target_pct=0`) olarak eklenecek — isim olarak
`window_09` bilinçli olarak atlandı çünkü o isim 9 Temmuz'da zaten bir kez
denenip yarım kalmıştı (karışıklık riski almamak için).

**İlk deneme — SSH/WiFi kesintisi:** `run_all_windows.sh`, `WINDOWS=(...)`
dizisi geçici olarak `("window_10_0pct:0")` yapılıp (orijinal 7 pencerelik
dizi `run_all_windows.sh.window10-active-backup` olarak yedeklenip)
başlatıldı. Health-check geçti (conn.log büyüdü), 60dk'lık bekleme adımına
girildi. Ancak bekleme sırasında (13:03 UTC civarı) Pi'ye SSH bağlantısı
tamamen koptu (`ping` %100 paket kaybı) — zeek PID izleme turları art arda
"durum okunamadı" hatası verdi. Reboot gerekti; kullanıcı kısmi/şüpheli
veriyle uğraşmak yerine **capture'ı tamamen silip sıfırdan tekrarlamayı**
tercih etti.

**Reboot sonrası temizlik ve doğrulama:**
- Mac'teki eski `run_all_windows.sh` process'i ve Selenium/Locust alt
  process'leri zaten ölmüştü, kill gerekmedi.
- `run_all_windows.sh` backup'tan orijinal 7 pencerelik haline geri
  alındı.
- Pi'de yarım kalan `window_10_0pct` klasörü silindi (reboot sonrası
  zaten yoktu).
- Pi sağlık kontrolü: `ntp.conf`'taki 9 Temmuz'un bozuk `fudge` satırı
  reboot sonrası geri gelmemiş (kalıcı düzelme doğrulandı), `wlan0`/`eth0`
  sağlıklı, default gateway var — **ama saat senkronu ilk kontrolde henüz
  `synchronized: no`** (NTP'nin oturması zaman aldı). Birkaç dakika
  beklenip tekrar kontrol edildiğinde `yes` oldu, ancak başlatma bu kez
  yanlış dizinden (`~` home) denenip `bash: run_all_windows.sh: No such
  file or directory` hatası aldı — `find` ile doğru path
  (`~/Desktop/Docs/scripts/run_all_windows.sh`) bulunup oraya `cd`
  yapılarak düzeltildi.

**İkinci deneme — başarılı:** `window_10_0pct`, `13:44:14 UTC` başlayıp
`14:44:27 UTC`'de (tam 60dk) kesintisiz tamamlandı, `status: collected`.
Sonuç: **`conn.log` = 4411 satır** (window_01'in 547'sine kıyasla ~8x
fazla, diğer window'ların 4-5k aralığına tam oturuyor), `actual_attack_pct
= 0.181694` (pratikte tamamen temiz), mid-window zeek restart izi yok.

**Yanlış konum düzeltmesi:** İlk rsync komutu yanlışlıkla eski/terk
edilmiş bir path'e (`~/Desktop/ids-dataset-raw-backup/`, 11 Temmuz
konsolidasyonundan önceki konum) kopyalama yaptı — kullanıcı fark edip
sordu, `window_10_0pct` doğru konuma (`~/Desktop/NIDS/data/
ids-dataset-raw-backup/window_10_0pct/`, diğer 8 window'la aynı seviye ve
isim formatında — `window_02_3pct` tarzı) taşındı, satır sayısı (4411)
taşıma sonrası da doğrulandı, yanlış üst klasör tamamen silindi.

### phase3_dense / phase3_vae klasör ayrımı

Mevcut Dense autoencoder çalışması kendi klasörüne taşındı, VAE için
paralel bir iskelet açıldı (git mv ile, geçmiş korunarak):
- `phase3_autoencoder.ipynb` → `phase3_dense/phase3_dense_autoencoder.ipynb`
- `03_phase3_splits/`, `04_phase3_models/`, `05_phase3_results/` →
  `phase3_dense/` altına
- `phase3_vae/03_phase3_splits/`, `04_phase3_models/`, `05_phase3_results/`
  boş (`.gitkeep`) olarak oluşturuldu

Taşıma sonrası doğrulama: `phase3_dense/` içinden `nbconvert --execute`
ile uçtan uca çalıştırıldı, sonuçlar taşıma öncesiyle birebir aynı çıktı
(`full_features` AUC=0.9463340100922982, `no_conn_state`
AUC=0.9341419580747934 — sadece `train_time_sec` gibi zamanlama alanlarında
beklenen küçük gürültü).

**Split paylaşım kararı (A vs B):** `03_phase3_splits/` klasörünün Faz 2
seviyesinde (proje kökünde) ortak/tek kaynak mı kalacağı, yoksa her
phase3 klasörüne kopyalanıp bağımsız mı tutulacağı tartışıldı. **(A)
ortak split** seçildi — split'in tanımı (hangi flow train/val/test'e
gidiyor) Faz 2 çıktısına bağlı, model mimarisinden bağımsız olduğu için;
iki kopya senkron kayması riski (Dense ve VAE'nin farklı split'lerde
train/test olup "haksız" bir kıyas üretmesi) katma değersiz görüldü.

### window_10_0pct için feature extraction (label-leakage'sız, Dense'in scaler'ıyla tutarlı)

Kullanıcı kararı: `window_01_0pct` ve `window_10_0pct` **birleştirilmeyecek**.
`window_10_0pct` = VAE'nin (sadece VAE'nin) temiz train seti. `window_01_0pct`
= train'e hiç girmeyecek, mevcut distribution-shift/sanity-check test
seti planı korunacak.

Bunun için `faz2_feature_extraction.py`'yi (ve dolayısıyla Dense'in
mevcut split'ini/AUC sonucunu) hiç bozmadan window_10'u işlemek gerekiyordu.
İki yaklaşım tartışıldı:
- **(A1)** window_10 için sıfırdan yeni bir `StandardScaler` fit etmek —
  reddedildi, çünkü VAE'nin train dağılımı val/test'in (Dense'in train'i
  üzerinden fit edilmiş scaler ile ölçeklenmiş) ölçeğinden farklı olur,
  reconstruction-error eşikleri karşılaştırılamaz hale gelir.
- **(A2) seçildi** — Dense'in donmuş `train_indices.csv`'sindeki satırlar
  + windows 01-08'in ham `conn.log`'undan aynı türetilmiş feature
  formülleriyle scaler/encoder parametreleri deterministik olarak yeniden
  üretildi (dosyaya dokunmadan), sadece `window_10`'a `transform()`
  uygulandı — bu, window_10'un feature'larının mevcut val/test ile aynı
  ölçekte kalmasını sağlıyor.

Ayrı bir script (`phase3_vae/prepare_window10.py`) yazıldı. Doğrulama:
yeniden kurulan `conn_all` (windows 01-08), Dense'in `train_indices.csv`'siyle
`ts` alanı bazında birebir eşleşti (`np.allclose` → True). Sonuç: ham
`conn.log` 4411 satır → lab-IP filtresinden sonra 4356 flow (55 satır
lab-dışı trafik elendi), `is_attack` (Dense'in tanımıyla) = 0 flow (tamamı
benign). Çıktı `phase3_vae/window10_clean_train.csv`'ye yazıldı (22 sütun,
18'i gerçek feature — `is_attack`, `actual_attack_pct`, `window_id`, `ts`
metadata/etiket, model girdisine dahil edilmedi, label leakage önlendi).

**Bilinen küçük kısıt:** `window_10`'da Dense'in `OneHotEncoder`'ının
(windows 01-08'de) hiç görmediği `proto=icmp` ve `conn_state=OTH`
kategorileri var — `handle_unknown="ignore"` ile sessizce sıfır kodlanıyor,
veri kaybı yok ama o flow'ların proto/conn_state sinyali VAE'ye ulaşmıyor.
Şimdilik ele alınmadı, VAE sonuçları yetersiz çıkarsa geri dönülecek.

### VAE mimarisi ve sağlık kontrolü

Kullanıcı kararı: VAE mimarisi Dense'e mimari olarak benzetilmeye
**zorunlu değil**, en sağlıklı/standart pratiğe göre kurulacak (Dense'in
scaler'ı sadece ölçek tutarlılığı için ödünç alındı, mimari kıyası
zorunluluğu yok).

Final mimari: Encoder `18 → Dense(16, relu) → Dense(8, relu) →
[z_mean(latent), z_log_var(latent)]`, reparameterization trick
(`z = z_mean + exp(0.5*z_log_var) * eps`), Decoder simetrik
`latent → Dense(8) → Dense(16) → Dense(18, linear)`. BatchNorm
eklenmedi (küçük veri/batch'te gürültülü istatistik riski), hafif
Dropout(0.1) sadece ilk encoder katmanında. `EarlyStopping(patience=12,
monitor=val_loss)` Dense'teki gibi kullanıldı.

`phase3_vae/phase3_vae_autoencoder.ipynb` oluşturuldu (veri yükleme →
model kurma → latent karşılaştırması → tam eğitim → loss eğrisi →
reconstruction-error histogramı → eşik kalibrasyonu → ROC/AUC/F1).

**Karşılaşılan sorun (ilk çalıştırma):** latent=6 için `z_log_var` patladı
(`exp()` taşması → inf), AUC hesabı çöktü. Standart stabilizasyon
uygulandı: `z_log_var` `[-10, 10]` aralığına `Lambda` katmanıyla clip'lendi
+ Adam optimizer'a `clipnorm=1.0` eklendi — sonrasında tüm latent'ler
sorunsuz eğitildi.

**Latent boyut karşılaştırması** (6/8/10, val AUC bazlı, tolerans=0.01):
latent=6 baz alındı, latent=8 daha düşük AUC verdiği için elendi,
latent=10 ise +0.0799 AUC (tolerans üstü, gerçek kazanç) sağladığı için
**latent=10 seçildi**.

**Kısmi posterior collapse tespiti:** latent=10'un 9 boyutu neredeyse
tamamen pasif (z_mean std ≈ 0.02-0.11), sadece 1 boyut aktif — model
fiilen ~1 boyut kullanıyordu (10 değil). Health-check'i durdurmadı ama
not edildi.

**Collapse düzeltmesi — 4 varyant karşılaştırması** (latent=10 sabit):

| Varyant | val AUC | test AUC | test F1 | Aktif boyut |
|---|---|---|---|---|
| beta=1.0 (baseline) | 0.8014 | 0.9244 | 0.8392 | 1/10 |
| beta=0.5 | 0.7228 | 0.8880 | 0.8399 | 6/10 |
| **beta=0.25 (seçildi)** | 0.8432 | 0.9372 | 0.8413 | 3/10 |
| KL-annealing (sigmoid→1.0) | 0.7251 | 0.8929 | 0.8471 | 10/10 |

Seçim kuralı: baseline AUC referans, bir varyant ancak daha fazla aktif
boyut sağlıyorsa VE AUC kaybı ≤0.03 toleransı içindeyse tercih edilebilir.
beta=0.5 (AUC kaybı tolerans dışı) ve KL-annealing (10/10 aktif boyutla
collapse'ı en agresif çözen ama AUC kaybı tolerans sınırının hemen üstünde)
elendi. **beta=0.25 seçildi** — aktif boyutu baseline'ın 3 katına
çıkarıyor (1→3) ve AUC'de kayıp yok (+0.0128 hafif iyileşme); reconstruction
loss'un dramatik düşmesi (5.97→0.645) collapse azalmasının bağımsız kanıtı.
Final mimari (latent=10, beta=0.25) kaydedildi:
`phase3_vae/04_phase3_models/vae_encoder_final.keras`,
`vae_decoder_final.keras`, test AUC=0.9372, F1=0.8413.

`phase3_vae/03_phase3_splits/` bilinçli olarak boş — VAE kendi split'ini
üretmiyor, Dense'in `val_indices.csv`/`test_indices.csv`'sini doğrudan
okuyor (train seti zaten `window10_clean_train.csv`'den, tamamı benign).
Cuma'daki karışık-train senaryosunda train kompozisyonunun nasıl
kaydedileceği (bu klasöre mi yazılacak) henüz netleştirilmedi.

### Okunabilir model dosyaları (Dense emsaliyle tutarlı)

`vae_encoder_final.keras`/`vae_decoder_final.keras` için Dense'deki
`.json` (mimari) + `_readable.txt` (katman özeti) dönüşümü notebook'un
kalıcı bir hücresi olarak eklendi (her çalıştırmada MODEL_DIR'daki
dosyalar taze yüklenip otomatik üretiliyor). `_readable.txt`'ye VAE'ye
özgü ek blok da eklendi: latent_dim=10, beta=0.25, z_mean/z_log_var
katman isimleri, reparameterization formülü — ve önemli bir not:
reparameterization mantığı `VAE2.call()` içinde Python kodu olarak
yaşıyor, `.keras` dosyasının Keras config'inde görünmüyor, yani bu
dosyalar tek başına (sınıf tanımı/notebook olmadan) tam pipeline'ı
çalıştırmıyor.

**Ek sorun:** Log-var clipping için kullanılan `Lambda` katmanı önce
`safe_mode`, sonra shape-inference eksikliği yüzünden deserialize
edilemedi — `safe_mode=False` + `Lambda(..., output_shape=lambda s: s)`
ile düzeltildi, model yeniden eğitilip kaydedildi (sonuçlar aynı kaldı).

### GitHub'a güncelleme push'u

Push öncesi kontroller: notebook'ta Türkçe metin yok (temiz), `.gitignore`
yeni dosyaları doğru yakalıyor, `window10_clean_train.csv` (1MB) mevcut
emsale (`features_all_windows.csv`, 9MB, doğrudan commit) uygun şekilde
commit edildi (LFS gerekmedi).

**Superseded model dosyaları kararı:** collapse-fix öncesi beta=1.0
baseline dosyaları (`vae_encoder_latent10.keras`,
`vae_decoder_latent10.keras`) silinmedi — deney izini/izlenebilirliği
korumak için `phase3_vae/04_phase3_models/superseded/` alt klasörüne
taşındı, `phase3_vae/README.md`'ye bu klasörün ne olduğunu açıklayan bir
not eklendi.

`phase3_vae/README.md` ayrıca oluşturuldu (Dense'in ayrı bir README'si
yoktu, sadece kök `00_REPORT.md` vardı) — standalone-yükleme uyarısını
(yukarıdaki not) içeriyor. Kök `00_REPORT.md`'ye kısa bir "Phase 3 — VAE
variant" bölümü eklendi (mimari özeti, seçim gerekçesi, test AUC/F1,
`phase3_vae/README.md`'ye referans). `00_REPORT.md`'nin klasör haritasının
hâlâ `phase3_dense/` taşımasından önceki eski yapıyı gösterdiği fark
edildi, küçük bir not eklendi ama tam yeniden yazım cuma deneyi bitince
tek seferde yapılacak.

Commit + push onaylandı, işlem tamamlandı.

### 16 Temmuz 2026 — Contamination sweep deneyi: temiz-vs-kirli train karşılaştırması tamamlandı

Cuma TODO'su (temiz-only vs. temiz+kirli-karışık train karşılaştırması)
bugün tamamlandı. Önce literatür araştırması yapıldı (Nkashama ve ark.
2024 "Deep Learning for Network Anomaly Detection under Data
Contamination"; Zong ve ark. 2018, DAGMM; Beggel ve ark. 2019; 2026
tarihli bir MDPI çalışması) — kontaminasyonun autoencoder tabanlı NIDS
performansını genel olarak düşürdüğü ama derecenin dataset/feature
representation'a bağlı olarak değiştiği (bazı çalışmalarda neredeyse
etkisiz) tespit edildi. Bu bulgu, deneyin kafaya göre değil literatüre
dayalı kurulmasını sağladı; kesin karar için kendi veride ampirik
doğrulama gerekli görüldü.

**Deney tasarımı:** Nkashama'nın leakage-free protokolü uyarlanarak
0/1/2/4/8/12% kontaminasyon seviyeleri test edildi.

**Veri hazırlığı** (`phase3_vae/05_contamination_sweep/prepare_contamination_data.py`):
- Attack havuzu window_02-08'den kuruldu (window_09 raw capture
  backup'ta hiç yoktu, sadece attacker IP flow'ları alındı): 3870 flow.
- Benign havuzu: window_10_0pct, 4356 flow.
- 3 yönlü benign split (70/15/15, seed=42): train_pool=3049,
  threshold-val=653, test=654 — flow_id bazında ayrık (assert edildi).
- Attack split: test_attack_set=73 (sabit test setinin ~%10
  contamination hedefine denk), attack_pool=3797 (train enjeksiyonu
  için) — test ile pool arasında kesişim yok (assert edildi).
- Sabit test seti: 727 flow (654 benign + 73 attack) → %10.04 gerçek
  contamination, tüm 6 seviyede aynı dosya kullanıldı.
- Scaler: ayrı bir `scaler.pkl` hiç yok; `prepare_window10.py`'deki
  desenle aynı şekilde Dense'in `train_indices.csv`'sinden
  read-only transform uygulandı (fit edilmedi, leakage-fix kuralına
  uyuldu).
- 6 kontamine train seti üretildi (hepsi aynı 3049 benign +
  attack_pool'dan bağımsız örneklenmiş attack flow'ları, seed=42+level);
  hedef/gerçek oranlar arasındaki fark en fazla ~0.01 puan
  (gerçekleşen: 0 / 1.006 / 1.993 / 3.999 / 7.996 / 12.006%).

**Eğitim** (`train_contamination_sweep.py`): 6 seviye × 5 seed = 30
model, final VAE mimarisi (latent=10, beta=0.25, z_log_var clip
[-10,10], Adam clipnorm=1.0, EarlyStopping patience=12) birebir
korunarak, tamamen unsupervised (etiket modele hiç verilmedi). Her
model için threshold_95/99, kendi held-out benign validation
split'inden hesaplandı (train'den değil).

**Değerlendirme** (`evaluate_contamination_sweep.py`): 30 model sabit
test setinde skorlandı (PR-AUC, ROC-AUC, F1, F2, benign_FPR,
attack_recall). Süreçte gerçek bir Keras bug'ı bulundu — Lambda
katmanının deserialization'ı, closure'ındaki `tf` referansını globals'tan
düşürüyor; bu, mevcut final VAE model dosyalarını
(`vae_encoder_final.keras`/`vae_decoder_final.keras`) da etkiliyor.
Hem `phase3_vae/README.md`'ye hem yeni sweep README'sine belgelendi.

**Sonuç analizi ve düzeltme:** İlk bakışta PR-AUC eğrisi "0%→8%
monoton düşüş, 12%'de anomali" gibi göründü, ama ham seed verisi
incelenince gerçek resmin farklı olduğu ortaya çıktı: contamination=8%,
seed=1 gerçek bir outlier (PR-AUC 0.478, diğer 4 seed 0.675-0.699
bandında). Latent collapse kontrolü yapıldı — seed=1'in 9/10 aktif
boyutu var (collapse değil); seed=4'ün sadece 3/10 aktif boyutu var ama
PR-AUC normal — yani collapse outlier'ı açıklamıyor, sıradan seed
varyansı olarak açık/bloklamayan bir soru şeklinde not edildi.
`results_summary.csv`'ye `median` ve `trimmed_mean` (min+max atılmış,
`scipy.stats.trim_mean`) sütunları eklendi.

Düzeltilmiş yorum: keskin düşüş 0%→4% arasında, sonrasında (4-12%)
gürültülü bir plato (~0.66-0.685); 5 seed bu platodaki ince yapıyı
çözmeye yetmiyor. PR-AUC (medyan, 5 seed): 0%=0.718, 4%=0.653,
8%=0.676, 12%=0.680. Erken "monoton düşüş" yorumu, ham veriyle
kontrol edilip düzeltildi (README.md ve 00_REPORT.md'de).

**Karar:** Hiçbir kontaminasyon seviyesi 0%'i geçemedi →
mevcut final VAE (window_10_0pct ile eğitilmiş, temiz-only) doğru/optimal
seçim olarak hem literatürle hem ampirik veriyle doğrulandı. Ana
pipeline'da hiçbir değişiklik yapılmadı; bu sweep, kararı değiştirmek
için değil, mevcut kararı gerekçelendirmek için kuruldu.

**Raporlama:** `phase3_vae/05_contamination_sweep/README.md` (TR, tam
yazım, protokol + sonuç tablosu + outlier/median notu) oluşturuldu,
`00_REPORT.md`'ye tarihli bir bölüm eklendi. Ayrıca Gérard Chalhoub'a
gönderilmek üzere Fransızca, kısa/sade iki sayfalık bir Word raporu
(`rapport_donnees_entrainement.docx`) hazırlandı — literatür özeti +
protokol + sonuç tablosu + karar, birinci tekil şahıs (je) ile yazıldı,
raporun sweep'e özgü PR-AUC'sinin (0.718) Faz 3'ün asıl test AUC'sinden
(0.9372) farklı bir ölçek olduğu ayrıca not edildi. E-posta taslağı
hazırlanıp gönderildi.

### Şu anki durum (16 Temmuz 2026 sonu itibariyle)

- **Kanonik proje:** `~/Desktop/NIDS/IDS-Project/` (yerel) =
  `github.com/mustafag63/DL-Based-NIDS` (uzak, public) — güncel.
- **Temiz train verisi:** `window_10_0pct` (4356 flow, saf benign) VAE
  için ayrılmış durumda ve KESİNLEŞMİŞ REFERANS olarak doğrulandı
  (contamination sweep sonucu); `window_01_0pct` train'e girmiyor, ayrı
  distribution-shift test seti olarak duruyor.
- **VAE final mimarisi:** latent=10, beta=0.25, test AUC=0.9372,
  F1=0.8413 — health-check tamamlandı, contamination sweep ile
  robustluk açısından da doğrulandı. Değişiklik yok.
- **Contamination sweep:** tamamlandı (30/30 model, 6 seviye × 5 seed).
  Sonuç: temiz-only (0%) en iyi PR-AUC'yi veriyor, 0%→4% keskin düşüş,
  4-12% gürültülü plato. Karar: temiz-only train'e devam.
- **Bilinen açık teknik sorun:** Keras Lambda-layer deserialization
  bug'ı (hem final VAE hem sweep modellerini etkiliyor) — belgelendi,
  henüz kalıcı çözülmedi. **[17 Temmuz'da kalıcı çözüldü, bkz. aşağı.]**
- **Bilinen açık metodolojik not:** contamination=8%/seed=1 outlier'ının
  kök nedeni (collapse değil) hâlâ açıklanamadı — bloklamayan, ileride
  bakılabilecek bir soru.
- **Rapor gönderimi:** Fransızca Word raporu + e-posta Gérard
  Chalhoub'a gönderildi (16 Temmuz).
- **Açık TODO:** VAE'nin AUC skorunun daha da iyileştirilmesi (mevcut
  0.9372 yetersiz görülüyor, sonraki bir oturumda ele alınacak).
- **Pi durumu:** capture bitti, `run_all_windows.sh` orijinal 7 pencerelik
  haline geri alındı, Pi'de artık process kalmadı (sadece standart
  `zeekctl` arka plan process'leri).
- Diğer açık TODO'lar (11 Temmuz'dan) değişmedi: IP-bazlı zaman-penceresi
  agregasyon feature'ları, persona-seviyesi feature'lar, `window01_shift_test`
  değerlendirmesi.

## 17 Temmuz 2026 — Keras Lambda-layer deserialization bug'ı kalıcı çözüldü

### Kök neden teşhisi

16 Temmuz'da contamination sweep sırasında bulunan bug (final VAE
checkpoint'lerini de etkileyen `NameError: name 'tf' is not defined`,
taze bir process'te encoder/decoder yüklenip çağrıldığında) detaylı
incelendi. Kök neden netleşti: `z_log_var`'ı `[-10, 10]`'a clip'leyen
`Lambda` katmanı deserialize edilirken, Keras'ın
`Lambda.from_config → func_load` mekanizması fonksiyonun closure'ını
kendi `python_utils` modülünün globals'ından yeniden kuruyor — o modül
hiç `tensorflow` import etmediği için `tf` referansı orada bulunmuyor.
Önceki `safe_mode=False` + `output_shape=lambda s: s` düzeltmesi ilk
(shape-inference) hatasını gidermişti ama bu ikinci, daha temel closure/
globals sorununu çözmüyordu.

### Kalıcı çözüm

- `phase3_vae_autoencoder.ipynb`'de `Lambda` katmanı tamamen kaldırıldı,
  yerine `tf.keras.utils.register_keras_serializable(package="phase3_vae")`
  ile işaretli bir `ClipLogVar` Layer alt sınıfı yazıldı (`call()` içinde
  `tf.clip_by_value(x, -10.0, 10.0)`, `compute_output_shape` input_shape'i
  aynen döndürüyor). Not: `tf.keras.saving.register_keras_serializable`
  bu ortamdaki tf/keras kombinasyonunda erişilemediği için, aynı işlevi
  gören `tf.keras.utils` varyantı kullanıldı (teyit edildi).
- `VAE2` sınıfı aynı dekoratörle işaretlendi, `input_dim`/`dropout_rate`
  self üzerinde saklanacak şekilde güncellendi, `get_config`/`from_config`
  eklendi.
- Model bu yeni implementasyonla sıfırdan yeniden eğitildi (mimari/veri
  değişmedi: latent=10, beta=0.25, aynı seed). Sonuç birebir eşleşti:
  test AUC=0.9372481..., F1=0.8413001... — tam eşleşme beklenen ve
  doğrulanan sonuç.
- Taze bir process'te, `custom_objects` olmadan, varsayılan
  `safe_mode=True` ile yeni `.keras` dosyaları başarıyla yüklenip
  çağrılarak bug'ın kapandığı kanıtlandı (tek gereklilik: `ClipLogVar`
  sınıfının o process'te önceden import edilmiş olması — bu her custom
  Keras layer için standart/beklenen davranış, workaround değil).

### Sınıf tanımlarının merkezi hale getirilmesi (model_layers.py)

`ClipLogVar` ve `VAE2` sadece notebook içinde tanımlıyken, notebook
dışında (ör. ileride bir inference script'i/API) model yüklenmeye
çalışılırsa `ValueError: Unknown layer` alınırdı. Bunu önlemek için:
- `phase3_vae/model_layers.py` oluşturuldu, iki sınıf buraya birebir
  taşındı (davranışta değişiklik yok, sadece konum).
- Notebook artık `from model_layers import ClipLogVar, VAE2` kullanıyor
  (sys.path ayarıyla).
- `phase3_vae/scripts/verify_model_loading.py` yazıldı: sadece
  `model_layers`'dan import sonrası, `custom_objects` olmadan,
  `safe_mode=True` ile encoder/decoder'ın yüklenip çalıştığını test
  ediyor. Hem repo kökünden hem tamamen ilgisiz bir dizinden (`/tmp`)
  çalıştırılarak doğrulandı.

### latest_run/ — kayıt mekanizmasının güvenli hale getirilmesi

Notebook'un model kaydeden hücresi (section 8) her çalıştırmada final
klasörün köküne sabit isimle (`vae_encoder_latent10.keras` vb.)
yazıyordu — yani gelecekteki bir yeniden çalıştırma (ör. AUC iyileştirme
denemeleri) final model dosyalarının üzerine sessizce yazabilirdi.
Düzeltme:
- Kayıt yolu `04_phase3_models/latest_run/` adında ayrı bir staging
  klasörüne yönlendirildi.
- Klasör doluysa eski dosyalar otomatik olarak çalıştırma zaman
  damgasıyla (`_run20260718-1337` gibi) aynı klasör içinde arşivleniyor
  — hiçbir çalıştırma sessizce kaybolmuyor/üzerine yazılmıyor.
- Hücre sonunda açık bir uyarı satırı var: model `latest_run/`'a
  kaydedildi, final olarak onaylamak için elle `04_phase3_models/`
  köküne veya `final_*` adıyla taşınması gerekiyor.
- Mekanizma iki kez çalıştırılarak test edildi (i. çalıştırma → oluştu,
  ii. çalıştırma → eski dosyalar timestamp'le arşivlendi, yenisi sabit
  adla kaydedildi), sonra test klasörü temizlendi.
- `04_phase3_models/latest_run/` `.gitignore`'a eklendi.
- Final dosyalara (`vae_encoder_final.keras`/`vae_decoder_final.keras`)
  ve `superseded/` klasör mantığına dokunulmadı.

### Arşivleme ve dokümantasyon

- Eski Lambda tabanlı final checkpoint'ler
  (`vae_encoder_final_lambda_bug.keras`/`vae_decoder_final_lambda_bug.keras`)
  isimlerine `_lambda_bug` eklenerek `04_phase3_models/superseded/`
  altına taşındı (silinmedi — referans/izlenebilirlik için).
- Yeniden eğitilmiş latent10 sweep dosyaları da aynı şekilde
  `superseded/` altına arşivlendi.
- `phase3_vae/README.md` ve `00_REPORT.md` güncellendi: bug artık
  "çözüldü" olarak işaretlendi, kök neden ve çözüm açıklandı;
  `model_layers.py`'nin merkezi konumu ve her yeni script'in
  `load_model`'dan önce `from model_layers import ClipLogVar, VAE2`
  yapması gerektiği not edildi; `latest_run/`'ın sadece ham/onaysız
  çıktı olduğu, final modelin her zaman `vae_encoder_final.keras`/
  `vae_decoder_final.keras` olduğu belirtildi.
- **Contamination sweep modelleri (30 model, `05_contamination_sweep/`)
  bilinçli olarak yeniden eğitilmedi** — sweep zaten kapanmış bir
  deneydi, sadece final/production model ve dokümantasyon için düzeltme
  yapıldı.

### Git durumu

Üç ilişkili değişiklik (Lambda bug fix + model_layers.py çıkarma +
latest_run/ mekanizması) tek commit'te birleştirilip
`github.com/mustafag63/DL-Based-NIDS`'e push edildi.

### İnternship raporu

`AGU-COMP-IF-4th-Week.docx`'in 5. gün (17/07/2026) satırı, yukarıdaki
işlerin özetiyle (6 madde: kök neden teşhisi, ClipLogVar çözümü,
model_layers.py çıkarma, superseded arşivleme, latest_run mekanizması,
commit+push) dolduruldu, diğer günlerle aynı formatta (Arial).

### Şu anki durum (17 Temmuz 2026 sonu itibariyle)

- **Kanonik proje:** `~/Desktop/NIDS/IDS-Project/` (yerel) =
  `github.com/mustafag63/DL-Based-NIDS` (uzak, public) — güncel.
- **VAE final mimarisi:** latent=10, beta=0.25, test AUC=0.9372,
  F1=0.8413 — değişmedi, sadece serialization yöntemi (ClipLogVar Layer)
  değişti.
- **Keras Lambda-layer deserialization bug'ı: KALICI ÇÖZÜLDÜ.**
  `ClipLogVar` Layer alt sınıfı + `model_layers.py` merkezi modülü +
  `verify_model_loading.py` doğrulama testi ile kapatıldı.
- **Kayıt mekanizması güvenli hale getirildi:** `latest_run/` staging
  klasörü final modeli kazayla üzerine yazılmaktan koruyor.
- **Açık TODO (öncelik):** VAE'nin AUC skorunun iyileştirilmesi (mevcut
  0.9372 yetersiz görülüyor, henüz nasıl yapılacağı planlanmadı) —
  bug fix zinciri kapandığı için artık önündeki tek net blokaj bu.
- **Bilinen açık metodolojik not (bloklamayan):** contamination=8%/
  seed=1 outlier'ının kök nedeni hâlâ açıklanamadı.
- Diğer açık TODO'lar (11 Temmuz'dan, 13-14 Temmuz'da ele alınıp
  kapatılmıştı) değişmedi: IP-bazlı zaman-penceresi agregasyon
  feature'ları ve persona-seviyesi feature'lar infeasible bulunup
  revert edildi/reddedildi; `window01_shift_test` değerlendirmesi
  tamamlandı (~%11 FPR, kısmi generalization — bu ölçüm Dense modeline
  aitti, VAE'ye o zaman hiç koşulmamıştı, bkz. 20 Temmuz).

## 20 Temmuz 2026 (Pazartesi) — VAE metodolojik denetim zinciri

Gérard Chalhoub ile planlanan toplantı öncesi (başlangıçta 21 Temmuz
Salı, sonradan Gérard'ın contrainte'i nedeniyle **23 Temmuz Çarşamba'ya
ertelendi**, aynı saat — mail ile teyit edildi), VAE'nin final
konfigürasyonunun (latent=10, beta=0.25, test AUC=0.9372, F1=0.8413)
metodolojik sağlamlığı sırayla denetlendi. Sabah, dokuz maddelik bir
zayıflık listesi çıkarıldı, altısı bugün ele alındı ve kapatıldı;
detaylı analiz ve tam klasör dökümü `VAE_Calisma_Raporu_20_Temmuz.pdf`
dosyasında (kullanıcının masaüstünde/outputs'ta) mevcut.

### 1. Beta seçiminde test-set sızıntısı denetimi (`06_beta_selection_audit/`)

4 beta varyantı (1.0/0.5/0.25/KL-annealing) karşılaştırılırken notebook
Cell 22/26'da test seti her varyant için ayrı ayrı skorlanmış VE seçim
kriteri val_auc değil test_auc üzerinden hesaplanmıştı — klasik test-set
sızıntısı. `rerun_beta_selection.py` ile temiz protokol (sadece
val_indices.csv, seçim val AUC + aktif boyut sayısına göre) uygulandı.
**Sonuç: kazanan yine beta=0.25, temiz test AUC/F1 eski sayılarla
(0.9372/0.8413) birebir aynı — sızıntı gerçekti ama sonucu şişirmemiş.**
Notebook Cell 22/26 bu temiz mantığa göre kalıcı olarak düzeltildi
(`nbconvert --execute` ile doğrulandı, final model artık `latest_run/`
staging'e kaydediyor, root'a doğrudan yazmıyor). `phase3_vae/README.md`
ve `00_REPORT.md`'ye not eklendi.

### 2. Tek-seed varyans ölçümü (`07_seed_variance/`)

Final konfigürasyon 10 seed (0-9) ile sıfırdan eğitilip test'te
skorlandı. **Sonuç: test AUC = 0.9197 ± 0.0149, F1 = 0.8468 ± 0.0070
(10 seed) — eski 0.9372, bu dağılımın ~1.2 std üzerinde, iyimser bir
örnekmiş.** Beklenmedik bulgu: aktif latent boyut sayısı seed'ler arası
çok tutarsız (1/10-9/10, std=3.02) ve **test AUC ile hiç korelasyon
göstermiyor** — bu, sonraki iki adımın (3, 4) çıkış noktası oldu.

### 3. Beta seçiminin çoklu-seed ile yeniden doğrulanması (`08_beta_multiseed/`)

Madde 2'deki bulguya göre "aktif boyut = iyi latent" kriteri geçersiz
çıktığı için, beta seçimi bu kriter tamamen çıkarılarak, sadece val AUC
mean±std'ye göre 5 seed ile yeniden yapıldı (20 model). **Sonuç:
beta=0.25 yine açık ara önde (val AUC 0.8181±0.0194 vs beta=0.5'in
0.7803±0.0334, Welch p=0.0689 sınırda-anlamlı), kazananın test
performansı 0.9259±0.0095 — madde 2'nin 10-seed tahminiyle örtüşüyor.
Orijinal gerekçe (aktif boyut) yanlıştı ama düzeltilmiş kriterle aynı
karara (beta=0.25) bağımsız olarak varıldı.**

### 4. Posterior collapse araştırması (`09_collapse_investigation/`)

3 bağımsız kanıt hattı: (a) PCA — 18 feature'ın içsel boyutu ~3
(%90 varyans), `proto_udp≡service_dns` gibi r=1.000 redundant kolonlar
var; (b) latent taraması (4/6/8/10/16, 5 seed) — model kendiliğinden
hep ~2.6-3.4 boyut kullanıyor, val AUC latent=4-10 arası pratik olarak
aynı; (c) free-bits denemesi (λ∈{0.25,0.5,1.0}) — aktif boyutu yapay
olarak 10/10'a zorlayabiliyor ama AUC'ye hiçbir katkısı yok. **Karar:
collapse gerçek bir sorun değil, feature uzayının doğal
düşük-boyutluluğunun beklenen sonucu. latent=10'da kalınabilir; latent=6
isteğe bağlı bir sadeleştirme (performans farkı yok, sadece parsimoni).**

### 5. Olasılıksal/KL-tabanlı skorlama denemesi (`10_probabilistic_scoring/`)

Üç skor karşılaştırıldı (5 seed): recon_prob (An&Cho, MC L=10) 0.8264±
0.0208, baseline (saf MSE) 0.8181±0.0194, elbo_score (recon+beta·KL)
0.7509±0.0383. **`elbo_score` açıkça daha kötü** — madde 4'teki bulguyu
(KL/aktif-boyut bilgisi AUC ile ilişkisiz) bağımsız bir yoldan doğruluyor.
`recon_prob` hafifçe önde ama istatistiksel olarak anlamlı değil (Welch
p=0.53, test'te 0.9312±0.0102). **Karar: baseline'da kalınabilir,
`recon_prob` düşük riskli isteğe bağlı alternatif (~3.8x yavaş ama
ihmal edilebilir, 32ms/6576 satır), `elbo_score` kesinlikle
kullanılmamalı.**

### 6. Dağılım kayması testi: window01_shift_test (`11_shift_test_eval/`)

Kayıtlı final model (yeniden eğitilmedi), window01_shift_test.csv'nin
274 benign flow'unda değerlendirildi (VAE'ye bu test ilk kez koşuldu).
**Sonuç: VAE FPR=%7.30 (train benign %4.61, test benign %4.19), Dense'in
aynı testte ölçülen %11.31±0.89'una göre belirgin şekilde daha dayanıklı
(sapma büyüklüğü Dense'in ~1/3'ü).** Kök neden: en büyük feature sapması
`duration_scaled` (+0.49 std, 11 Temmuz EDA bulgusuyla örtüşüyor); FPR
artışı esas olarak birkaç aşırı-uç flow'dan geliyor (en yüksek hata
23.3), flow'ların %92.7'si hâlâ normal görünüyor — toplu kırılma değil.
%7.30 hâlâ %5 tabanının üzerinde, üretimde izlenmesi gereken bir metrik
ama aksiyon gerektirmiyor.

### Şu anki durum (20 Temmuz 2026 sonu itibariyle)

- **VAE final mimarisi değişmedi:** latent=10, beta=0.25 — ama artık
  çoklu bağımsız kanıtla (test-leakage denetimi, çoklu-seed varyans,
  collapse analizi, skorlama karşılaştırması, dağılım kayması testi)
  desteklenen bir karar.
- **Raporlanacak doğru sayı artık tek bir AUC değil, bir aralık:**
  test AUC ≈ 0.92 ± 0.01-0.015 (10-seed ve 5-seed ölçümleri birbiriyle
  tutarlı) — eski tek-seed 0.9372 hâlâ geçerli (kayıtlı final model o
  seed'le eğitilmiş) ama artık "tipik değil, iyimser bir örnek" olarak
  biliniyor ve öyle sunulmalı.
- **04_phase3_models/ kökü ve latest_run/ mekanizması bütün gün
  boyunca dokunulmadan korundu** (her adımda md5 ile doğrulandı) —
  06-11 arası tüm klasörler saf denetim/doğrulama niteliğinde, hiçbir
  model production'a alınmadı, sadece mevcut final modelin
  güvenilirliği kanıtlandı.
- **Açık kalan 3 madde (bugün ele alınmadı):**
  1. OneHotEncoder kapsam eksikliği — window_10'daki `proto=icmp`,
     `conn_state=OTH` kategorileri Dense'in encoder'ında tanımsız,
     sessizce sıfırlanıyor; etkisi (kaç flow, ne kadar sistematik)
     henüz ölçülmedi, muhtemelen küçük ama kanıtsız. Bir sonraki
     oturumda ele alınacak (prompt hazır, henüz çalıştırılmadı).
  2. Tek-kaynaklı train seti (window_10, tek 60dk capture,
     zamansal/ortamsal çeşitlilik yok) — çözümü yeni capture koşusu,
     altyapı görevi, kod session'ında yapılamaz.
  3. Model taşınabilirlik kısıtı (`.keras` tek başına çalışmıyor,
     `model_layers.py` gerektiriyor) — hata değil, custom Keras layer
     davranışı, zaten `verify_model_loading.py` ile dokümante edilmiş.
- **Toplantı Çarşamba'ya (23 Temmuz) ertelendiği için** zaman baskısı
  azaldı, açık maddeler acele edilmeden ele alınabilir.
- **Teslim edilen dosya:** `VAE_Calisma_Raporu_20_Temmuz.pdf` (Türkçe,
  8 sayfa) — tüm 6 denetim adımının detaylı anlatımı + tam klasör
  yapısı dökümü, toplantı hazırlığı için.

## 22 Temmuz 2026 (Çarşamba) — %15/%20 contamination noktalarının
eklenmesi: canlı capture'ın altyapı arızası nedeniyle terk edilmesi,
resampling'e geçiş, split-leakage tespiti ve düzeltmesi

Gérard ile bugün yapılan toplantıda, contamination sweep'te %12'den
sonra skorlarda beklenmedik bir artış gözlemlendiği ve mevcut en yüksek
contamination noktasının (%12) bu artışın gerçek bir trend mi yoksa
gürültü mü olduğunu ayırt etmeye yetmediği konuşuldu. Pazartesiye kadar
%15 ve %20 civarında yeni contamination noktaları üretilmesi
kararlaştırıldı. (Gérard'ın notu: imzalı haftalık rapor ekte gönderildi,
bir sonraki raporda bu haftaki bulguların toplantıdaki analiz sonrası
revize edildiği belirtilmeli.)

**1. Canlı capture denemesi (başarısız, terk edildi)**

`run_all_windows.sh`'a, belirli window'ları seçerek çalıştırabilmek
için bir komut-satırı filtre parametresi eklendi (parametre verilmezse
eski davranış korunuyor, format-dışı/enjeksiyon girişimleri regex ile
reddediliyor). `window_06_15pct` (target_pct=15) ve `window_09_20pct`
(target_pct=20) için capture başlatıldı. Yol boyunca sırayla:

- İlk denemede script'in "exit 1" ile durmasına rağmen alt süreçlerin
  (Selenium/Locust/Dell orchestrator) arka planda yaşamaya devam
  ettiği fark edildi — iki ayrı süreç grubu aynı anda Nginx'e trafik
  gönderiyordu. Doğru PID'ler tespit edilip hepsi öldürüldü, temiz tek
  bir koşuyla yeniden başlatıldı.
- Dell'de W32Time servisi çalışmıyordu (zaman senkronizasyonu yoktu),
  `w32tm /register` + `Start-Service` + `/resync` ile düzeltildi,
  `time.windows.com` ile senkron doğrulandı.
- `window_06_15pct` başarıyla tamamlandı (`status: collected`).
  `window_09_20pct` klasör çakışması hatasıyla durdu (önceki yarım
  kalmış denemeden kalıntı), temizlenip yeniden başlatıldı.

**2. Kalibrasyon sapması sorunu — `target_pct` ile gerçek contamination
arasındaki fark**

19 Temmuz'daki bilinen kalibrasyon sapması (`BENIGN_FLOWS_PER_75MIN`
sabitinin ~2x fazla tahmin etmesi) nedeniyle `target_pct=15/20` ile
başlatılan window'ların gerçekte `actual_attack_pct≈9/11-12` civarına
düşeceği hatırlandı — bu, mevcut max %12.15 noktasına çok yakın kalıp
sorunun cevabını vermeyecekti. Var olan 8 noktaya (`actual_attack_pct`
vs `target_pct`) bir doygunluk eğrisi (`actual = A·target/(B+target)`,
A≈25.5, B≈24.17) oturtularak ekstrapolasyon yapıldı: gerçek ~%15 için
`target_pct≈35`, gerçek ~%20 için `target_pct≈85-90` (tavana yakın,
belirsiz bölge) gerektiği hesaplandı. Ara adımlardan sonra `target_pct=35`
ve `target_pct=60` ile devam kararı verildi (model tahmini: actual≈15.1
ve actual≈18.2) — isimlendirme çakışmasını önlemek için
`window_12_35target` ve `window_13_60target` olarak eklendi (WINDOWS
dizisine, mevcut window'lara dokunulmadan).

**3. `window_12_35target` collect hatası → whitelist bug'ı → Pi'de
Zeek capture kesintisi keşfi**

`collect_window.sh`'ın kendi içinde `run_all_windows.sh`'taki
`WINDOWS` dizisinden bağımsız, ayrı bir hardcoded whitelist olduğu
ortaya çıktı ("Unknown window..." hatası) — whitelist genel bir
`window_<2hane>_<suffix>` regex'iyle değiştirildi (tam serbestlik
verilmedi, çünkü `$WINDOW` remote SSH komutuna tırnaksız enjekte
ediliyordu — enjeksiyon riski kapatıldı).

Whitelist düzeltmesinden sonra `window_12_35target` için collect elle
tekrar çalıştırıldı, ama `actual_attack_pct=100.000000` gibi anlamsız
bir sonuç çıktı. Kök neden araştırması: Pi'de Zeek'in saat **16:00-18:00
arası neredeyse hiç trafik yakalamadığı** bulundu (log dosya boyutları
`14:00-16:00` aralığında 206-276KB iken `16:00-18:00` aralığında
1.9-2.2KB'ye düşmüş) — `window_12_35target`'ın penceresi (15:32-16:32)
tam bu kesintinin ortasına denk geliyordu. `window_13_60target`
(16:34-17:34) tamamen bu ölü bölgenin içindeydi, muhtemelen o da
etkilenecekti. Kontrol anında (~20:0x) Zeek'in tekrar normal
çalıştığı doğrulandı (`conn.log` büyüyordu), yani kesinti geçiciydi
ama kök nedeni (WiFi kopması mı, başka bir müdahale mi) aynı anda
netleştirilemedi — zaman baskısı nedeniyle bu araştırma yarıda
bırakıldı.

**4. Karar: canlı capture'dan tamamen vazgeçildi, resampling'e geçildi**

Bugünkü tüm denemeler (`window_06_15pct`, `window_09_20pct`,
`window_12_35target`, `window_13_60target`) hem Pi'den hem Mac'ten
silinip başa dönüldü. Sadece orijinal 8 sağlıklı window
(`window_01_0pct`→`window_08_22pct`, `window_06_15pct` dahil) ve
ayrı bir amaçla oluşturulmuş `window_10_0pct` korundu.

`build_synthetic_window.py` yazıldı: **gerçek** Zeek flow'larını
(hiçbir feature uydurulmadan) yeniden örnekleyerek (resampling)
istenen contamination oranında yeni window'lar üretiyor. İlk
versiyon sadece `window_01_0pct`'i (559 flow) benign havuzu, sadece
`window_05_12pct`+`window_08_22pct`'i (1,779 flow) attack havuzu
olarak kullanıyordu — bu, hedef N=4,967 için benign tarafında
with-replacement (~8-9x tekrar) gerektiriyordu, overfitting/leakage
riski yüksekti. Havuzlar tüm 7 sağlıklı window'a (`01,02,03,04,05,
07,08`) genişletildi (benign havuzu 28,126, attack havuzu 3,279 flow'a
çıktı), bu sayede **hiç with-replacement gerekmedi** ve iki window
(15pct/20pct) ayrık (disjoint) havuz dilimlerinden örneklendi (leakage
önleme, bağımsız testle 0 ortak satır doğrulandı).

**Üretilen sonuç:**
- `window_resampled_15pct`: n_total=4967, attack=745,
  **actual_attack_pct=%14.999**
- `window_resampled_20pct`: n_total=4967, attack=993,
  **actual_attack_pct=%19.992**
- `window_meta.json`'da yöntem tam şeffaflıkla belgelendi:
  `source="resampled"`, `generation_method` (Pi/Zeek kesintisi
  gerekçesi + seed=42 + without-replacement notu), her window için
  hangi kaynak window'dan kaç flow çekildiğini gösteren
  `benign_draw_counts`/`attack_draw_counts`.
- Çıktı konumu: `~/Desktop/NIDS/data/ids-dataset-raw-backup/
  window_resampled_{15,20}pct/`.

**5. Faz 2 pipeline entegrasyonu ve kritik split-leakage düzeltmesi**

`faz2_feature_extraction.py`'nin `WINDOWS` listesi hardcoded olduğu
için iki yeni window elle eklendi; `ground_truth/attack_log.csv` ve
`dns.log` okuma blokları (resampled window'larda bu dosyalar yok,
`build_synthetic_window.py` sadece `conn.log` üretiyor)
`is_file()` kontrolüyle güvenli hale getirildi (dosya yoksa
`None`/`not_applicable`, hata vermiyor). Script uçtan uca çalıştı:
`window_resampled_15pct` flow-bazlı oran %14.68, `window_resampled_20pct`
%19.55 (meta'daki `actual_attack_pct`'e yakın, fark lab-IP dışı
flow'ların elenmesinden).

Eğitim öncesi 7 maddelik bir sağlık kontrolü (`validate_phase2_output.py`)
yaptırıldı: NaN taraması, duplicate satır kontrolü, **split leakage**,
`actual_attack_pct` tutarlılığı, feature dağılım sanity check,
`StandardScaler` kapsamı, `window_id`/`source` ayırt edilebilirliği.

**Kritik bulgu (FAIL → düzeltildi):** resampled window'lardaki
flow'lar, kaynak window'larıyla (`01,02,03,04,05,07,08`) aynı `uid`'i
paylaşan **9,790** satırdan **3,551** tanesi train ile val/test
arasında bölünmüştü (örn. `window_05_12pct`'te test'e düşen bir flow,
`window_resampled_15pct`'te aynı `uid`'le train'e düşmüştü) —
klasik split leakage, val/test AUC'sini yapay olarak şişirecekti.
**Düzeltme:** post-hoc split-aware resampling — resampled
window'lardaki her satırın split'i, kaynak flow'un kaynak window'da
zaten aldığı split'e göre zorunlu override edildi (4,720 satır
etkilendi). Düzeltme sonrası leakage 3,551→0, hiçbir window aşırı
dengesiz split dağılımına düşmedi (genel oran ~%59.8/%18.1/%21.4,
düzeltme öncesine yakın), train hâlâ %100 benign (anomaly-detection
kısıtı korundu). Tüm 7 kontrol PASS, **"EĞİTİME HAZIR"** kararı
verildi.

**Sonuç — güncel contamination serisi:** 0/3/5/7/12/15/17/19.99/22%
(gerçek `actual_attack_pct` değerleriyle), artık %12'den sonrasını
(%15, %17, %20, %22) kapsayan tam bir seri mevcut.

**Yarına kalan (bilinçli olarak ertelendi):** Bu iki yeni resampled
window'un, `faz2_feature_extraction.py`'nin ürettiği ortak
train/val/test split'inden **ayrı** bir mekanizma olan contamination
sweep script'ine (kasıtlı kirli-train + çoklu-seed AUC ölçümü,
context.md'de "contamination sweep experiment" olarak geçen) dahil
edilmesi — "%12'den sonraki artış gerçek bir trend mi" sorusunun asıl
cevabı bu adımdan çıkacak.

**Ayrıca not edilmesi gereken açık nokta:** Pi'deki Zeek capture
kesintisinin (16:00-18:00) kök nedeni netleştirilmedi — WiFi kopması
mı, başka bir müdahale mi olduğu bilinmiyor, sadece geçici olduğu ve
kendiliğinden düzeldiği doğrulandı. İleride canlı capture tekrar
gerekirse önce bu araştırılmalı.

- **23 Temmuz 2026 — Contamination sweep, resampled window'larla
  %12 sonrasına genişletildi; 5-seed sonuçların yanıltıcı olduğu
  bootstrap/20-seed analiziyle ortaya çıkarıldı ve düzeltildi.**

  **Amaç:** Gérard'ın sorusu — "%12'den sonraki (daha yüksek)
  contamination oranlarında model performansı nasıl davranıyor,
  toparlanma var mı" — `05_contamination_sweep/`'teki mevcut 6 noktayı
  (0/1/2/4/8/12%, sabit benign pool + kontrollü enjeksiyon, 5 seed)
  `window_resampled_15pct`/`_20pct` (bkz. 22 Temmuz) ile genişletme
  kararı verildi.

  **1. İlk genişletme (15/20% + sonra 22/25/28/30% denemesi):**
  `prepare_contamination_data_extended.py` / `train_..._extended.py` /
  `evaluate_..._extended.py` yazıldı, aynı VAE mimarisi (latent=10,
  beta=0.25) ve threshold_95 protokolüyle 15pct/20pct için 5'er seed
  eğitildi. uid bazlı leakage kontrolü (orijinal `flow_id` yöntemi
  resampled window'larda çalışmıyordu, çıplak Zeek `uid` ile
  değiştirildi) 15%'te 20, 20%'de 15 satırlık örtüşmeyi test setinden
  train'e sızmadan önce yakaladı ve elendi (gerçek oranlar
  %14.33→hayır, ilk turda %14.999/%19.992 target, sonra leakage
  düzeltmesiyle gerçek `actual_attack_pct`≈%14.33/%19.30'a indi —
  bkz. aşağıdaki nihai tablo).

  Sonuç grafiğinde (contamination_curve.png) %20 sonrası değerlerin
  %0'a "yaklaşıyor" gibi göründüğü fark edildi (görsel olarak U şekli
  hipotezi) — eksen ölçeği zoom'lu olduğu için ilk bakışta yanıltıcıydı
  ama sayılar (PR-AUC %0=0.718 → %20=0.688) gerçekten de kısmi bir
  toparlanma öneriyordu.

  **2. %22/25/28/30 denemesi — attack havuzu yetersizliği ve
  with-replacement artefaktı:** Toplam attack havuzu 3,279 flow, 15/20%
  zaten 1,738'ini kullanmıştı (kalan 1,541). 4 yeni seviye (~5,216 flow
  gerektiriyordu) havuza sığmadığı için `build_synthetic_window.py`
  otomatik with-replacement'a düştü (`_dupN` etiketleme). Bu 4 nokta
  eğitilip sonuç eğriye eklendi (%27'de PR-AUC=0.714'e "toparlanma"),
  ama with-replacement'ın attack örneklerini tekrar kullanmasının
  (duplicate flow) modelin o örüntüyü ezberlemesine yol açabileceği
  ve bu toparlanmanın gerçek olmayabileceği fark edildi — bu 4 nokta
  `exploratory_with_replacement/` klasörüne taşındı (silinmedi), ana
  sweep'ten çıkarıldı.

  **3. Sadece %22'nin temiz (without-replacement) versiyonu:** Kalan
  1,541 flow bütçesiyle sadece tek bir yeni nokta —
  `window_resampled_22pct_clean` (n=4967, gerçek kontaminasyon
  %21.29, 18 satır test'le çakıştığı için elendi) — without-replacement
  üretildi, disjointness 15/20% ile assert'le doğrulandı. İlk 5-seed
  sonucu (std=0.001, mean=0.711) with-replacement'lı %22'ye (0.685)
  çok yakın çıktı, bu da başta "toparlanmanın with-replacement
  artefaktı olmadığı" şeklinde yorumlandı — **bu yorum daha sonra
  yanlış çıktı (bkz. madde 4)**.

  **4. Kritik bulgu — bimodal seed dağılımı (5-seed std'ler yapay
  dardı):** 15/20/22%(clean) noktalarının seed sayısı 5'ten 20'ye
  çıkarılınca (mevcut 5 seed'e dokunulmadan [5..19] eklendi), std'ler
  daralmak yerine **büyüdü** (%14.33: 0.069→0.092, %19.30: 0.029→0.071,
  %22: **0.001→0.086**, yani 86 kat). Neden: her üç noktada da
  seed'lerin ~%10-20'si düşük bir kümeye (PR-AUC ~0.40-0.55) düşüyor,
  geri kalanı sıkı bir "iyi" kümede (~0.63-0.72) — bimodal dağılım.
  İlk 5 seed'in üçünde de tesadüfen tamamının "iyi" kümeye düşmesi
  yapay olarak dar std üretmişti. **Sonuç: "%22 toparlanması gerçek,
  gürültü değil" iddiası geri çekildi** — sadece şanslı 5 seed'di.

  **5. Orijinal 6 noktanın da 20 seed'e çıkarılması + bootstrap
  anlamlılık testi:** Aynı bimodalite riskinin 0/1/2/4/8/12%'de de
  olup olmadığını kontrol etmek için onlar da [5..19] ile genişletildi
  (mevcut 5 seed'e dokunulmadan, 90 yeni model). Bulgular:
  - Bimodalite **sadece %8'den itibaren** başlıyor, %0-4% temiz/kararlı
    (kötü küme oranı: %0-4=0/20, %8=4/20, %12=4/20, %15-22=2-4/20).
  - **%12'nin "yüksek" görünmesi de şanstı**: 5-seed mean 0.683 idi
    (bir U şekli/toparlanma izlenimi veriyordu), 20-seed mean **0.634**
    çıktı — %8'in (0.639) bile altında. İlk 5 seed'in hepsi tesadüfen
    iyi kümeye düşmüştü (~%33 olasılıkla beklenen bir sapma).
  - `bootstrap_significance.py` ile her nokta için %0 baseline'a karşı
    10,000 resample'lık bootstrap CI hesaplandı: **hiçbir contamination
    seviyesinin CI'ı sıfırı kapsamıyor** — %1 dahil tüm seviyeler
    clean-only'den istatistiksel olarak anlamlı derecede kötü.

  **Nihai, doğrulanmış sonuç (9 nokta, hepsi 20 seed, bootstrap CI ile
  test edilmiş):**

  | contam. | mean PR-AUC | median | 95% CI (vs 0%) | anlamlı mı |
  |---|---|---|---|---|
  | 0% | 0.716 | 0.715 | — | — |
  | 1% | 0.697 | 0.699 | [-0.029,-0.009] | evet |
  | 2% | 0.691 | 0.690 | [-0.030,-0.018] | evet |
  | 4% | 0.676 | 0.679 | [-0.053,-0.029] | evet |
  | 8% | 0.639 | 0.667 | [-0.105,-0.052] | evet |
  | 12% | 0.634 | 0.665 | [-0.121,-0.047] | evet |
  | ~14.33% | 0.640 | 0.666 | [-0.119,-0.041] | evet |
  | ~19.30% | 0.662 | 0.686 | [-0.088,-0.027] | evet |
  | ~21.29% | 0.665 | 0.710 | [-0.090,-0.017] | evet |

  **Sonuç:** Clean-only (%0) training, %1 gibi düşük oranlar dahil,
  test edilen **her** contamination seviyesinden istatistiksel olarak
  anlamlı derecede daha iyi. "%12'den/%20'den sonra toparlanma var"
  hipotezi (hem ilk U-şekli gözlemi hem de %22-clean'in dar std'si)
  **yanlış çıktı** — düşük seed sayısının (5) şans eseri ürettiği bir
  görünüm olduğu, 20 seed + bootstrap CI ile netleşti. Ek olarak: %8
  contamination'dan itibaren VAE eğitimi **bimodal/kararsız** hale
  geliyor (seed'e göre iyi ya da kötü bir rejime yakınsıyor) — bu,
  ortalama performansın yanı sıra eğitim kararlılığının da
  contamination ile bozulduğunu gösteren ayrı bir bulgu.

  `README.md` (05_contamination_sweep/) güncellendi: eski 5-seed
  bölümü "superseded" notuyla işaretlendi, yeni bölüm bimodalite +
  anlamlılık bulgularıyla eklendi, %12/%22 toparlanma iddiaları
  retraction notuyla düzeltildi. `contamination_curve.png` artık
  std bandı yerine 95% bootstrap CI error bar'ları gösteriyor. Yeni
  script'ler: `train/evaluate_contamination_sweep_original_seedext.py`,
  `bootstrap_significance.py`, `plot_contamination_curve_with_ci.py`.

  **Bilinçli olarak bırakılan:** %16/17/18 gibi ara noktalar —
  attack havuzunda sadece ~448 temiz (kullanılmamış) flow kaldı, bu
  ancak küçük n_total (~600-700) ile without-replacement mümkün olurdu
  ki bu da veri-boyutu confound'u eklerdi (n=4967 diğer noktalarla
  karşılaştırılamaz hale gelirdi). Mevcut 9 nokta + istatistiksel
  anlamlılık testi yeterli/sağlam kabul edilip sweep burada kapatıldı.

  **Yarına kalan:** Bu nihai sonucu (özellikle %12/%22 retraction'ı ve
  bimodalite bulgusunu) Gérard'a Fransızca özetlemek — clean-only
  kararının artık daha geniş bir contamination aralığında ve
  istatistiksel olarak doğrulandığını, ayrıca yüksek contamination'da
  eğitim kararlılığının bozulduğunu raporlamak.

- **27 Temmuz 2026 — Contamination sweep sonuçları Gérard'a raporlandı;
  Cuma (31 Temmuz) toplantısına kadar yeni görev seti belirlendi.**

  **Rapor edilen sonuç:** 20-seed + bootstrap CI ile doğrulanmış nihai
  contamination sweep sonucu (9 nokta, %0-%21.29) Gérard'a özetlendi:
  clean-only (%0) training test edilen her seviyeden istatistiksel
  olarak anlamlı derecede daha iyi; %12/%22'deki görünen "toparlanma"
  düşük seed sayısının (5) yarattığı bir yanılsama olduğu için geri
  çekildi; %8'den itibaren VAE eğitiminin bimodal/kararsız hale geldiği
  ayrıca belirtildi.

  **Toplantıda belirlenen yeni görevler (Cuma'ya kadar):**
  1. **Tekli attack-type performansı** — VAE modelinin portscan,
     slowloris ve apache bench flow'larını ayrı ayrı ne kadar iyi
     tespit ettiği; her biri için AUC/PR-AUC/F1 hesaplanacak.
  2. **İkili grup performansı** — aynı analiz, 3 ikili kombinasyon
     için de yapılacak: apache bench + slowloris, slowloris +
     portscan, apache bench + portscan.
  3. **Bloklu (segmented) saldırı enjeksiyonu deneyi** — mevcut temiz
     datasete saldırı flow'ları rastgele karışık değil, ardışık
     bloklar halinde eklenip (ör. flow 0-1000 apache bench, 1000-2000
     slowloris, 2000-3000 portscan) model bu senaryoda test edilecek.
     Açık nokta: bu deneyin training tarafını da mı kapsayacağı yoksa
     sadece evaluation-side mi olacağı henüz netleşmedi.
  4. **Dense v1 ile karşılaştırma** — 1-3 arasındaki tüm analizler,
     mevcut Dense autoencoder modelinin **v1 hâliyle** (yeniden
     eğitilmeden) de tekrarlanıp VAE ile karşılaştırılacak.
  5. Tüm bulguları kapsayan detaylı bir sonuç raporu hazırlanacak.

  Toplantı sonrası mevcut evaluation pipeline'ı ve dataset label
  yapısı, attack-type bilgisinin nasıl çıkarılacağını planlamak için
  gözden geçirildi; 3 yeni deney + rapor için bir implementasyon planı
  taslağı çıkarıldı.

  **Yarına kalan:** Attack-type/ikili-grup evaluation script'inin
  yazılması (VAE clean-only model üzerinde, retrain gerekmeden), ve
  bloklu enjeksiyon deneyinin training kapsamına girip girmeyeceğinin
  netleştirilmesi.

- **28 Temmuz 2026 — Cuma'nın 4 görevi tamamlandı (tekli/ikili
  attack-type, bloklu enjeksiyon, Dense v1 karşılaştırması, kök neden
  analizi); ardından Claude Fable 5 ile bağımsız bir metodoloji
  denetimi yaptırıldı ve bulunan sorunlar tek tek düzeltildi.**

  **1. Cuma'nın 4 görevi (VAE, clean-only, 20 seed):**
  - Tekli attack-type: portscan (recall 0.989, AUC 0.998) ve slowloris
    (recall 1.000, AUC 1.000) neredeyse mükemmel; **apache_bench
    neredeyse hiç yakalanamıyor** (recall 0.033, AUC 0.582 — rastgele
    tahmine yakın). Toplu binary metrik bunu maskeliyor çünkü
    apache_bench toplam attack popülasyonunun küçük bir kısmı.
  - İkili grup: pooled recall (%33-40) yanıltıcı — decompose edilince
    apache_bench'in kendi recall'u (~%3.2-3.3) pairing ile değişmiyor,
    yükseliş tamamen portscan/slowloris'in havuzu yukarı çekmesinden.
  - Bloklu (segmented) enjeksiyon: saldırılar ardışık bloklar halinde
    dizilse de sonuçlar shuffle edilmiş sete neredeyse birebir aynı —
    VAE hafızasız/statik olduğu için beklenen bir sonuç. Benign
    segmentler arası FPR %3-9.6 dalgalanması ilk başta "örneklem
    gürültüsü" diye yorumlandı (bu yorum sonra yanlış çıktı, bkz. O6
    düzeltmesi aşağıda).
  - Dense v1 karşılaştırması: apache_bench zayıflığı Dense'te de var
    (recall 0.026, AUC 0.696 — AUC biraz daha iyi ama recall daha
    kötü). Macro-average VAE (0.674/0.551) ve Dense (0.673/0.540)
    pratikte aynı. **Sonuç: apache_bench zafiyeti mimariden bağımsız,
    feature set kaynaklı yapısal bir kısıt.**
  - Kök neden analizi (`06_diagnostics/`): tek-flow feature'larında
    apache_bench benign'e çok yakın (~0.4-0.7σ, normal aralığın
    kenarında). KS istatistiği yüksek (0.62-0.76) ama etki büyüklüğü
    küçük — çünkü apache_bench dar/düşük varyanslı bir küme, VAE'nin
    kare-hata tabanlı reconstruction error'ı bu farkı yakalamıyor.
    **Temporal hipotez testi:** apache_bench flow'ları arası medyan
    inter-arrival time 0.00092s, benign'de 2.18s — **~2364x fark**
    (KS=0.71). Tek-flow feature'ları apache_bench'i ayıramıyor ama
    flow'lar-arası zamanlama çok net ayırıyor; mevcut feature set bu
    bilgiyi hiç görmüyor. Retrain ile doğrulanmadığı notu net
    belirtildi.
  - Tüm sonuçlar `10_final_report/` altında tek, düzenli bir teslimat
    klasöründe (01-08 alt klasörleri: tekli/ikili/bloklu/diagnostics/
    notebooks/scripts/final_written_report + Türkçe DOCUMENTATION.md
    ve METRIKLER_ACIKLAMA.md) toplandı, VAE/Dense sonuçları ayrı
    tutuldu (comparison klasörü yok, kıyas okuyucuya bırakıldı),
    grafikler yüksek çözünürlük+büyük font standardına yükseltildi.

  **2. Bağımsız denetim — Claude Fable 5 (`11_fable_review/independent_audit.md`):**
  Sadece okuma/inceleme (kod/veri değiştirilmedi). Genel değerlendirme:
  ana pipeline'da (faz2 split+scaler) klasik data leakage bulunamadı;
  split-öncesi-scaler kuralı, GroupShuffleSplit, resampled-uid
  düzeltmesi doğru. Ama:
  - **K1 (kritik):** contamination sweep'in test setinde benign
    (window_10) ve attack (window_02-08) farklı capture oturumlarından
    geliyor — window-artefaktı ile attack etiketi confound olabilir.
  - **K2 (kritik):** sweep'in benign train/val/test bölmesi düz rastgele
    permütasyon, faz2'nin near-duplicate önleyici signature-grouping
    disiplini burada uygulanmamış — threshold yapay olarak iyimser
    olabilir.
  - **Orta (O1-O7):** VAE latent(10)>bottleneck(8) mimari tutarsızlığı;
    anomaly skorunun tek stokastik örnekle (seed'siz) hesaplanması;
    resampled kopyaların test setinde çift sayılması (~%31); threshold
    varsayımları (küçük val n, dağılım transferi); VAE-Dense
    karşılaştırmasının farklı train verisiyle confound'lu olması;
    segmented-injection FPR farkının "örneklem gürültüsü" değil
    sistematik window-kompozisyon farkı olması; ground truth'un
    davranışsal değil IP-bazlı tanımlanması.
  - Sorun bulunmayan noktalar da ayrıca listelendi (scaler sırası,
    split mantığı, leakage düzeltmeleri, apache_bench'in dürüstçe
    raporlanmış olması).

  **3. Düzeltmeler (retrain gerektirmeyenler önce, sonra K1/K2):**

  - **O2 — deterministik skor:** VAE anomaly skoru artık `z_mean` ile
    (stokastik örnekleme yok) hesaplanıyor; threshold_95 buna göre
    seed başına yeniden kalibre edildi. Sonuç: apache_bench ROC-AUC
    0.582→0.667 (arttı, gürültü sıralamayı bozuyormuş), recall
    0.033→0.026 (azaldı, gürültü sahte-pozitif yakalamalar
    üretiyormuş). **En çarpıcı bulgu: 20 seed'in hepsi aynı 39
    apache_bench flow'unu işaretliyor (recall std=0.0000)** —
    zafiyetin seed şanssızlığı değil, kesin bir yapısal feature-uzayı
    sınırı olduğu kanıtlandı. portscan recall 0.989→0.998; slowloris
    değişmedi. Segmented injection'daki benign FPR deseni gürültü
    kalktığı halde birebir aynı kaldı (O6'yı destekliyor). Deterministik
    sonuç ana/kanonik sonuç olarak benimsendi (eski stokastik sonuçlar
    `_stochastic_legacy/` altına taşındı, silinmedi).
  - **O3 — dedup sağlamlık kontrolü:** resampled kopyalar (attack'lerin
    %31'i) dedup edilip tekrar değerlendirildi. Davranış metrikleri
    (recall/ROC-AUC/FPR, maks fark <0.02) değişmedi — kopyalar model
    davranışını etkilemiyor. Ama prevalansa duyarlı metrikler (PR-AUC,
    F1) dedup'ta farklı çıktı (mekanik, oran kayması nedeniyle) —
    **karar: recall/ROC-AUC/FPR kanonik (dedup'suz) setten, PR-AUC/F1
    dedup setten alıntılanacak**, her tabloya bu kaynak ayrımı dipnot
    olarak eklendi. Segmented injection'da düzeltme gerekmedi (F1,
    bloklarda salt recall'un fonksiyonu, prevalansa duyarlı değil).
  - **O6 — FPR yorumu düzeltmesi:** segment-window kompozisyon tablosu
    üretildi; window_06 (FPR 0.100) ve window_07 (0.115) diğer
    window'ların (0.029-0.053) 2-4 katı FPR veriyor. Gap FPR'lerinin
    ağırlıklı-ortalama ile yeniden kurulumu ölçülen değerlerle ≤0.008
    farkla örtüştü — fark **sistematik (window kompozisyonundan)**,
    "örneklem gürültüsü" değil. Yanlış yorum VAE+Dense sonuç
    dosyalarında ve üretici script'te düzeltildi.
  - **K1/K2 — tam deconfounded sweep:** karma-benign test seti (window_10
    %70 + window_02-08 %30, window_06/07 aşırı temsili engellenerek) +
    signature-grouped benign split ile tüm 9 kontaminasyon noktası
    (0/1/2/4/8/12/~14.38/~19.27/~21.26%) 20 seed + bootstrap CI ile
    yeniden koşuldu (140 yeni model). **Sonuç: headline bulgu
    ("clean-only en iyisi") değişmedi, güçlendi** — 8/8 sıfır-dışı
    seviyede istatistiksel olarak anlamlı, deconfounded pipeline'da
    kontaminasyonun zararı v1'den daha büyük ölçülüyor (near-duplicate'ler
    v1'de bozulmayı maskeliyormuş). K1'in gerçek büyüklüğü küçük çıktı
    (v1 modeli window_02-08 benign'inde de ~aynı FPR veriyor, yani
    gerçekten saldırıyı öğrenmiş). K2'nin öngördüğü mekanizma birebir
    doğrulandı (threshold 0.090→0.122, FPR 0.042→0.026, recall
    değişmeden). Orijinal v1 sweep dosyalarına dokunulmadı, tamamen
    ayrı bir doğrulama kolu (`11_deconfounded_check/`) olarak duruyor.
  - **04_apache_bench_diagnostics güncellemesi:** reconstruction error
    histogramı deterministik skorla yeniden üretildi. Güncel medyan
    değerler: benign 0.0131, apache_bench 0.0171 (sadece ~1.3x fark,
    threshold'un ~5 kat altında), portscan+slowloris 8.81e4. Ortalama-
    medyan uçurumu (apache_bench: 5.744 vs 0.017) aynı 39 flagged
    flow'dan geliyor — std=0.0000 bulgusuyla birebir tutarlı. "Ayrım
    threshold artefaktı mı" sorusu gürültüsüz veriyle kapandı: gerçek
    bir feature-düzeyi ayrışabilirlik sınırı. IAT ve feature-KS
    analizleri VAE skoruna bağlı olmadığından dokunulmadı.

  **Bekleyen işler (bir sonraki oturuma):**
  1. `05_notebooks/` — hâlâ eski stokastik dönemden, deterministik
     skorla güncellenmesi gerekiyor.
  2. O1 — VAE mimari notu (latent=10 > bottleneck=8), belki latent≤8
     ile bir doğrulama koşumu.
  3. O4 — threshold varsayımları (küçük val n, dağılım transferi)
     rapor notu.
  4. O5 — VAE-Dense karşılaştırmasının train-verisi confound'u için
     tablolara dipnot.
  5. O7 — ground truth'un IP-bazlı (davranışsal değil) tanımlandığına
     dair tehdit modeli sınırlaması notu.
  6. **Fransızca yazılı rapor** (`07_final_written_report/`) — tüm
     düzeltmelerin (O2/O3/O6/K1/K2 + kalanlar) özetini içerecek
     şekilde güncellenecek; bilinçli olarak en sona bırakıldı.
  7. **Kapsamlı Türkçe dokümantasyon** — tüm denetim + düzeltme
     sürecini (bulgular, neden/nasıl, sonuçlar) baştan sona anlatan
     PDF; bilinçli olarak en sona bırakıldı.

  Zaman kısıtı olmadığı için (staj bitişi 31 Temmuz olsa da bu
  doğrulama çalışması için acele edilmiyor), her adım tek tek,
  doğrulanarak ilerletildi; hiçbir orijinal/kanonik dosya üzerine
  yazılmadı, her düzeltme ayrı dosya/klasörde tutulup CHANGELOG.md'de
  kronolojik olarak belgelendi.

- **29 Temmuz 2026 — Bağımsız denetimin (Fable review) kalan
  bulgularının (O1, O2 notebook'ları, O4, O5, O7) kapatılması.**
  Önceki oturumun "Bekleyen işler" listesindeki maddeler tek tek,
  aynı disiplinle (doğrulama → onay → Fransızca+Türkçe taslak
  → onay → dokümana yerleştirme + PDF yeniden üretimi + görsel
  doğrulama + CHANGELOG maddesi) işlendi.

  **1. `05_notebooks/` güncellemesi:** Dört notebook da deterministik
  z_mean skorlamaya geçirildi (37/37 hücre hatasız). Orijinal
  stokastik versiyonlar `_stochastic_legacy/` altına taşındı, hiçbiri
  silinmedi. Notebook 04'teki bozuk `DIAG_DIR` yolu da bu sırada
  düzeltildi (04_apache_bench_diagnostics'e yönlendirildi), notebook
  daha önce hiç çalışamaz durumdaymış.

  **2. O1 — VAE mimari notu (latent=10 > bottleneck=8):**
  Mimari teyit edildi (encoder 18→16→8→z_mean(10)/z_log_var(10),
  decoder 10→8→16→18). `12_latent_ablation/` altında latent=8 ile
  20-seed doğrulama koşusu yapıldı (~12dk): apache_bench/portscan/
  slowloris recall latent=8 ve latent=10 arasında **tam olarak aynı**;
  ROC-AUC farkı (+0.035) %95 CI'da sıfırı içeriyor. Aktif latent boyut
  sayısı (std(z_mean)>0.15) her iki varyantta da nominalin altında ve
  seed'e göre oynak (latent=10'da ort. 5.9/10, latent=8'de 4.4/8) —
  audit'in "±0.08 AUC farkı muhtemelen seed varyansı" öngörüsünü
  destekliyor. Sonuç: mimari özensizlik gerçek ama ölçülebilir etkisi
  yok. Fransızca ("Note d'architecture") ve Türkçe not rapora/
  DOCUMENTATION.md'ye eklendi, PDF'ler yeniden üretildi.

  **3. O4 — threshold_95'in küçük val setinden kalibrasyonu:**
  Retrain'siz analiz (`06_scripts/o4_threshold_transfer/`). Bulgular:
  threshold_95 her seed'de aynı 653 flow'luk window_10 val-benign
  setinden (95. persentil ≈ ~33. sıra istatistiği) hesaplanıyor;
  20 seed arası threshold_95 ort. 0.0903, std 0.0252, CV %27.9,
  aralık [0.043, 0.153]; tek seed içi bootstrap %95 CI genişliği
  ort. threshold'un %59.7'si — görünen oynaklığın büyük kısmı
  küçük-n persentil tahmin gürültüsü. Val→test transferi kabaca
  tutuyor ama sistematik sapmalı: val threshold'u test-benign'de
  nominal %5.00 yerine ort. %5.77±0.58 FPR veriyor (20 seed'in
  18'i >%5, yönlü sapma); tam %5 verecek threshold val'inkinden
  ort. %8 yüksek olurdu; KS(val,test-benign) ort. 0.067 (5/20 seed'de
  p<0.01) — saptanabilir ama küçük bir kayma. AUC/PR-AUC bundan
  etkilenmiyor, yalnızca thr95-bağımlı recall/F1/FPR çalışma noktası
  etkileniyor. Fransızca+Türkçe (§7.3) notlar eklendi, PDF'ler
  yeniden üretildi.

  **4. O5 — VAE/Dense v1 karşılaştırmasının train-verisi confound'u:**
  Retrain'siz doğrulama (`06_scripts/o5_train_data_confound/`). VAE
  yalnızca window_10 benign'iyle (n=3.049, 20 seed, rastgele 70/15/15
  split), Dense v1 window_01-08 ile (n=23.274, ~7,6 kat fazla, 5 seed,
  signature bazlı GroupShuffleSplit) eğitilmiş; ayrıca window_10'da
  Dense'in hiç görmediği kategorik değerler var (proto=icmp,
  conn_state∈{OTH,S0}) → VAE'nin eğitiminde bu flow'lar all-zero
  kodlanıyor. Scaler'ın kendisi confound değil (tek sefer Dense
  train'inde fit edilip iki tarafa da uygulanıyor — ortak ölçek).
  Değerlendirme tarafı (test flow'ları, 18 kolon, threshold
  konvansiyonu) elma-elma. Sonuç: macro-parite (0.674/0.551 vs
  0.673/0.540) ve "Dense'in apache_bench'te ham ayrım gücü biraz
  daha iyi" (ROC-AUC 0.696 vs 0.581/0.667) gibi ince-taneli
  karşılaştırmalar mimariye atfedilemez — ama ana bulgu (apache_bench
  her iki modelde de kaçıyor → feature-set sınırlaması) bu confound'a
  rağmen **güçleniyor**: iki farklı mimari + çok farklı eğitim
  verisiyle aynı başarısızlık deseni, ortak paydanın (18 kolon)
  suçlu olduğunu destekliyor. Fransızca (§5 sonu) + Türkçe (§7.4)
  notlar eklendi, PDF'ler yeniden üretildi.

  **5. O7 — ground truth'un IP-bazlı (davranışsal değil) tanımı:**
  Kod teyidi: `faz2_feature_extraction.py:134-136` ve VAE tarafındaki
  `prepare_window10.py` — `is_attack = (id.orig_h == "192.168.10.2")`,
  lab-only IP filtresi sonrası, hiçbir davranışsal/imza sinyali
  etikete girmiyor. Attack etiketli flow'ların %100'ü 1sn toleransla
  bir saldırı komut aralığına düşüyor (bu lab kurulumunda etiket
  pratikte temiz); IP model girdisi değil (18 feature'da yok), yani
  model IP'yi ezberlemiyor, o makineden çıkan trafiğin istatistiksel
  imzasını öğreniyor — sınırlama feature'larda değil etiket tanımında.
  Hiçbir final dokümanda bu tanım daha önce açıklanmıyordu — net
  eksiklik. Not üç parçalı: (a) etiket tanımı ve temizlik/IP-değil-
  feature nüansları, (b) kapsanmayan senaryolar (spoofing, NAT/ele
  geçirilmiş makine arkasında karışık trafik, yanal hareket) test
  edilmedi/garanti edilemez, (c) diğer bulgular bu tanım altında
  geçerli kalıyor, yalnızca "gerçek dünya deployment" okumalarının
  kapsamı netleşiyor. Fransızca (§7, O4 notunun ardına) + Türkçe
  (§7.5) eklendi, PDF'ler yeniden üretildi.

  **Sonuç:** Denetimin tüm ana maddeleri (O1-O7, K1-K2) artık rapor
  düzeyinde kapatılmış durumda. Skorlarda kötüye gidiş yok — tersine
  iki ana bulgu (clean-only training en iyisi; apache_bench zafiyeti
  feature-set kaynaklı yapısal sınır) denetim sonrası daha sağlam
  kanıtla destekleniyor. Değişiklikler pushlandı, commit henüz
  atılmadı (küçük commit'ler yerine kalan işlerle birlikte toplu
  commit planlanıyor).

  **Bekleyen işler (akşama / bir sonraki oturuma):**
  1. **Fransızca yazılı rapor** (`07_final_written_report/`) — tüm
     düzeltmelerin (O1/O2/O3/O4/O5/O6/O7/K1/K2) özetini içeren genel
     bir sentez/gözden geçirme bölümü eklenecek; bilinçli olarak en
     sona bırakıldı.
  2. **Kapsamlı Türkçe dokümantasyon** — tüm denetim + düzeltme
     sürecini (bulgular, neden/nasıl, sonuçlar) baştan sona anlatan
     ayrı bir PDF; bilinçli olarak en sona bırakıldı.
  3. Bugünkü ve önceki tüm düzeltmelerin toplu commit'i.

  Ayrıca bu oturumda AGU-COMP-IF-03 haftalık staj takip formunun
  (6. hafta dosyası, "5. Hafta" tablosu) 3. gün (29/07/2026) satırı,
  günün yapılan işlerinin özetiyle dolduruldu.

- **30 Temmuz 2026 — apache_bench zafiyetine çözüm bulundu
  (concurrency_src_1s), canonical modele 3 aşamalı entegre edildi,
  V1 arşivlendi, final rapor (İngilizce) + 2 Türkçe dokümantasyon
  PDF'i yeniden üretildi, .gitignore güncellenip pushlandı.**

  Dünkü (29 Temmuz) denetim turunun bulgusu "feature-set sınırlaması"
  hipotezini test etme günüydü — apache_bench'i yakalayacak bir
  feature bulunabilir mi? Cevap evet, ama ilk deneme değil.

  **1. `13_temporal_feature_experiment/` — IAT hipotezi, negatif
  sonuç.** Hipotez: kaynak IP başına, bir flow'un BİR ÖNCEKİ flow'a
  göre zaman farkı (inter-arrival time, IAT) eklenirse apache_bench
  yakalanır mı (`04_apache_bench_diagnostics/findings.md`'deki
  "apache_bench IAT'ı benign'den 2364× kısa" bulgusundan hareketle).
  Log1p + benign-train-fit scaler, Dense v1 mimarisi, 3 seed ile
  retrain edildi. Sonuç: **recall hiç değişmedi** (0.0262→0.0262),
  ROC-AUC hafifçe düştü (0.696→0.530), benign FPR arttı (0.0615→
  0.0695) — feature işe yaramadı. KS istatistiği tüm veri setinde
  sadece 0.375 (mevcut en iyi feature'lardan zayıf). Deneyin asıl
  değerli çıktısı yan bulgu oldu: orijinal "2364×" rakamı, IAT'ın
  yalnızca seyrek bir test alt kümesinde hesaplanmasından kaynaklanan
  bir **ölçüm artefaktıydı** — tüm flow'lar üzerinde doğru hesaplanan
  benign medyan IAT'ı aslında ~1.98ms (apache_bench'in 0.92ms'inden
  sadece ~2× uzak, 2364× değil), çünkü benign trafiğin kendisi de
  bursty. Knock-out testiyle (feature dondurulup model aynen
  değerlendirildiğinde sonuçların baseline'a dönmesi) bulgu teyit
  edildi — gerçek bir negatif sonuç, ölçüm hatası değil.

  **2. `14_concurrency_feature_experiment/` — pencere-bazlı yoğunluk,
  pozitif sonuç.** Yeni hipotez: bir flow'un BİR ÖNCEKİ flow'a göre
  farkı değil, kendi zaman damgası etrafındaki (±1s/±2s/±5s) yerel
  yoğunluk. 3 feature ailesi × 3 yarıçap = 9 ham feature:
  `concurrency_src` (aynı kaynak IP'den ±r içindeki flow sayısı),
  `concurrency_dst` (aynı hedef IP+port'a giden flow sayısı),
  `byte_ratio_var_src` (concurrency_src komşuluğunda byte_ratio
  varyansı). Retrain öncesi KS ön-testi: 9 feature'ın hepsi KS
  0.91-1.00 aralığında (13'teki IAT'ın 0.375'inden çok güçlü) —
  ama `byte_ratio_var_src_{2,5}s`'in KS=1.000 olması (kullanıcı
  tarafından) şüpheli bulundu. Winsorize (benign-train p1-p99) +
  log1p düzeltmesi sonrası KS 0.948-0.987'ye düştü (hâlâ güçlü).
  Araştırma, KS=1.0'ın asıl kaynağını ortaya çıkardı: test setindeki
  apache_bench flow'larının **%100'ü**, ±2s'lik aynı-kaynak-IP
  komşuluğunda port-80-olmayan bir flow içeriyor — yani tek saldırgan
  IP'nin kısa sürede birden fazla saldırı aracını art arda
  çalıştırması (resampled pencerelerin saldırı tiplerini zamanda iç
  içe geçirmesinin bir yan etkisi), "apache_bench kendi içinde
  tekrarlı" hipotezinden değil. 3 konfigürasyon retrain edildi (Dense
  v1 mimarisi, 3 seed): **Config A** (`concurrency_src_1s` tek başına)
  → recall 0.0262→0.9135±0.0292, ROC-AUC 0.9834, benign FPR +0.0026
  (temiz sinyal, confound'suz); **Config B** (`byte_ratio_var_src_2s`
  winsorize edilmiş, tek başına) → recall sadece 0.0332 (zayıf, KS'inin
  çoğu confound kaynaklıydı); **Config C** (üç feature'ın kombinasyonu)
  → recall 1.0000, ROC-AUC 0.9973, benign FPR baseline'ın bile altında
  (0.0592<0.0615) — en iyi ham performans ama `byte_ratio_var`
  bileşeninin confound'a bağımlı olması riski var. Knock-out ablasyonu
  C içinde: `concurrency_src_1s`'i dondurmak recall'u az düşürüyor ama
  benign FPR'ı 2 katına çıkarıyor (0.059→0.125) — yani C'deki asıl
  değeri diğer feature'ların getirdiği false-positive'leri bastırmak.
  **Config A canonical adayı olarak seçildi**: en temiz/yorumlanabilir
  sinyal, en düşük confound riski, knock-out ile gerçekten modelin
  kullandığı doğrulanmış, tek başına zaten büyük kazanç.

  **3. Config A'nın canonical modele 3 aşamalı entegrasyonu.**
  Kullanıcı onayıyla kademeli ilerlendi (her aşama sonunda durup
  rapor edildi):
  - **Aşama 1 (Dense v2):** `concurrency_src_1s`, tüm 46.495 satırlık
    veri setinde (ts+is_attack+window_id assert'iyle doğrulanmış
    hizalama) hesaplanıp Dense v1 train split'ine fit edilen scaler'la
    ölçeklendi (`build_features_v2_dense.py`,
    `02_phase2_feature_extraction/features_with_concurrency/`). Dense
    5 seed ile 19-feature üzerinde retrain edildi. Sonuç (5 seed):
    apache_bench recall **0.9092±0.0382**, ROC-AUC **0.9808±0.0076**
    — 3-seed Config A'yla (0.9135) tutarlı.
  - **Aşama 2 (VAE v2):** VAE'nin tamamen ayrı eğitim verisi kaynağı
    olan window_10 için feature hesaplanıp Dense v2'nin **AYNI
    scaler'ıyla** (refit edilmeden) ölçeklendi — mean_log/std_log
    eşleşmesi assert'le doğrulandı (eşleşmedi = dur talimatı vardı,
    eşleşti). VAE'nin benign/attack split'i, v1 ile birebir aynı
    flow_id kümelerini üretti (SEED=42, 5/5 hash kontrolü geçti).
    VAE 5 seed, latent=10, beta=0.25, **deterministik z_mean**
    skorlamayla (O2 düzeltmesi baştan uygulandı, stokastik yöntem hiç
    kullanılmadı) retrain edildi. Sonuç: apache_bench recall
    **0.9500±0.0453**, ROC-AUC **0.9836±0.0123** — VAE, Dense'i hafifçe
    geçti; iki farklı mimari + iki farklı eğitim verisi kaynağıyla
    aynı büyüklükte kazanç, feature-space fix'inin mimariye özgü
    olmadığının kanıtı.
  - **Aşama 3 (pairwise + segmented v2):** Her iki model, 3 ikili
    kombinasyon (decomposed recall dahil — apache_bench'in kendi
    recall'u pairing'e göre değişmiyor: Dense her koşulda 0.9092,
    VAE her koşulda 0.9500, per-flow karar statik) ve bloklu
    (segmented) enjeksiyon protokolüyle değerlendirildi; blok-recall
    shuffled test setiyle birebir eşleşti (`11_pairwise_segmented_v2/`).

  **4. V1_ARCHIVE oluşturulması + İngilizce final raporun v2'ye göre
  yeniden yazılması.** Eski 18-feature sonuçları (rapor klasörleri
  `01-04`, Dense v1 modelleri, VAE v1 20-seed modelleri,
  `13_temporal_feature_experiment/`, `_stochastic_legacy/` kalıntıları)
  proje kökündeki yeni `V1_ARCHIVE/`'a taşındı (silinmedi), açıklayıcı
  bir `README.md` eklendi. `_v2` son eki taşıyan rapor/model
  klasörleri, isimlerinden `_v2` kaldırılarak boşalan orijinal
  isimlerini devraldı (örn. `01_single_attack_type_v2/` →
  `01_single_attack_type/`, `phase3_dense/05_phase3_models_v2/
  full_features_v2/` → `phase3_dense/04_phase3_models/full_features/`)
  — iç boru hattı klasörleri (`01_data_v2/`, `09_dense_v2_comparison/`
  vb.) isim çakışması/altyapı gerekçesiyle `_v2` son ekini korudu.
  Taşıma sonrası her iki modelin single_attack_type sonuçları yeni
  yollardan yeniden koşturulup **aynı sayıları verdiğinden** emin
  olundu. `10_final_report/CHANGELOG.md`'ye eski→yeni yol eşleme
  tablosu eklendi. Ardından `07_final_written_report/
  rapport_final_attack_type_analysis.md` (İngilizce) sıfırdan yeniden
  yazıldı: v1/v2 ayrımı olmadan tek canonical VAE/Dense sonuç bölümü,
  Root Cause Analysis (apache_bench'in KS yüksek ama ortalama-kayması
  sadece 0.4-0.7σ olduğu için neden kaçtığı + concurrency_src_1s'in
  nasıl çözdüğü + tek-saldırgan-IP genellenebilirlik uyarısı),
  Methodology Note (IAT başarısızlığı + artefakt keşfi + concurrency
  başarısı, kısa özet, V1_ARCHIVE'a referans), Known Limitation (O3
  dedup-prevalence düzeltmesi v2'ye henüz uygulanmadı), Conclusion.
  Metin PDF üretilmeden önce kullanıcıya gösterildi, onay sonrası PDF
  üretildi (9 sayfa) ve `pdftoppm` ile sayfa sayfa görsel doğrulandı —
  bu doğrulamada bloklu-enjeksiyon grafiklerinin başlıklarında kalıntı
  "v2" ibaresi bulunup kaynak script (`evaluate_segmented_injection_v2.py`)
  düzeltilip figürler yeniden üretildi.

  **5. İki Türkçe dokümantasyon PDF'i.** Eski `DOCUMENTATION.md/html/pdf`
  ve `METRIKLER_ACIKLAMA.md/pdf` (18-feature v1) `V1_ARCHIVE/`'a
  taşındı. Yerine, **reportlab** ile (markdown+Chrome pipeline'ı değil,
  kullanıcı özellikle istedi) ve Türkçe karakterler için matplotlib'in
  bundle ettiği **DejaVuSans/-Bold/-Oblique/-BoldOblique** fontlarıyla
  (varsayılan Helvetica'da Türkçe glyph yok) iki yeni PDF üretildi:
  `Proje_Sonuclar_TR.pdf` (8 sayfa — genel özet: Faz 1-2-3, bağımsız
  denetim K1/K2/O1-O7 tablosu, apache_bench'in tam öyküsü, güncel v2
  sonuç tabloları+grafikler, O3 açık sınırlama notu) ve
  `Metrikler_Aciklama_TR.pdf` (5 sayfa — her metriğin tanım/anlam/somut
  örnek üçlüsü + `concurrency_src_1s`'in tasarım mantığı bölümü).
  Ortak stil modülü `pdf_style_tr.py` (font kaydı, paragraf/tablo/figür
  yardımcıları). **Doğrulama sürecinde bulunan grafik hatası:**
  `Proje_Sonuclar_TR.pdf`'in kullandığı ROC/PR eğrisi PNG'lerinde
  (`build_01_single_v2_{dense_only,vae_only}.py`'den) üst başlık ile
  alt-grafik başlıkları üst üste biniyordu VE kalıntı "v2" etiketi +
  yanlışlıkla yeniden oluşturulmuş bir "dense_v2" klasörü vardı; kaynak
  script'ler düzeltilip (kısaltılmış alt başlıklar, düzeltilmiş
  `tight_layout`, doğru klasör yolu) figürler yeniden üretildi, her iki
  PDF'in TÜM sayfaları tek tek `pdftoppm` render + görsel incelemeyle
  doğrulandı (ı/İ/ğ/Ğ/ş/Ş/ç/Ç/ö/Ö/ü/Ü dahil, hepsi doğru).

  **6. .gitignore güncellemesi ve commit/push.** Beklenmedik bulgu:
  `git status` oturum başında zaten tamamen temizdi — bu oturumun tüm
  içeriği (V1_ARCHIVE dahil) konuşma dışında zaten commit+push
  edilmişti (`1b81a11`, 296 dosya, +155K satır). Repo boyut envanteri
  çıkarıldı: `.git`=85M, working tree=251M, `V1_ARCHIVE/`=18M (tracked),
  CSV'ler=111M/164 dosya (en büyük tekil kategori — `concurrency_
  features_all_rows.csv` 22M, `features_v2_all_rows.csv` 12M başı
  çekiyor), model dosyaları=25M/855 dosya (bireysel ~30KB, küçük,
  gitignore'a eklenmedi), ham veri repo dışında (`../data/`). Kullanıcıya
  `.gitignore`'un yalnızca ileriye dönük çalıştığı (zaten commit+push
  edilmiş dosyaları geriye dönük etkilemediği) netleştirildi. Büyük
  regenerate-edilebilir CSV'ler + `V1_ARCHIVE/` için pattern'ler eklendi
  (kullanıcı `V1_ARCHIVE/`'ı untrack ETMEMEYİ, sadece gitignore'a
  eklemeyi seçti). `git add .gitignore && git commit -m "chore: expand
  .gitignore for v2 experiment artifacts and large CSVs" && git push` —
  commit `b3c6b1e`, push başarılı, `HEAD`/`origin/main` eşleşmesi ve
  temiz working tree doğrulandı.

  **Sonuç durumu:** `concurrency_src_1s` artık tek canonical feature
  seti (19 feature); apache_bench recall'u kalıcı olarak %2,6-3,3'ten
  %90,9-95,0'e çıktı; tüm eski (18-feature) sonuçlar `V1_ARCHIVE/`'da
  korunuyor; İngilizce final rapor + 2 Türkçe dokümantasyon PDF'i
  güncel; `.gitignore` genişletildi ve GitHub'a pushlandı. Bilinen açık
  nokta: O3 dedup-prevalence düzeltmesi güncel (19-feature) modele
  henüz yeniden uygulanmadı (PR-AUC/F1 geçici kabul edilmeli, ROC-AUC/
  recall/FPR etkilenmiyor).
