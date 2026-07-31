# selenium-bot — Mimari ve İşleyiş Raporu

*Hazırlanma tarihi: 3 Temmuz 2026 — Son güncelleme: 6 Temmuz 2026*
*Proje yolu: `~/Desktop/selenium-bot/` (MacBook)*

---

## 1. Projenin Amacı — Neden Bu Sistem Var

Bu proje, bir **saldırı üretmiyor** — tam tersine, tamamen zararsız ("benign") ama gerçekçi insan davranışını taklit eden web trafiği üretiyor. Amaç: klasik ağ güvenlik araçlarının (Zeek, RITA gibi imza/kural tabanlı sistemler) bu trafiği "normal" olarak görmesini sağlamak, sonra bir Autoencoder'ın (Faz 2) bu "normal görünümlü" trafiği istatistiksel olarak nasıl ayırt edebileceğini göstermek.

Bunun işe yaraması için botların **gerçek bir insanın gezinme ritmini ve zamanlamasını** taklit etmesi gerekiyor — rastgele tıklamalar değil, CICIDS2017 adlı gerçek dünya veri setinden istatistiksel olarak türetilmiş bir davranış modeli.

---

## 2. Üst Düzey Mimari

```
┌─────────────────────────────────────────────────────────┐
│                     MacBook (Client)                      │
│                                                             │
│   App.java  /  ParallelRunner.java   ← giriş noktaları    │
│         │                                                   │
│         ▼                                                   │
│   scenarios/  (davranış — NE yapılacak)                    │
│         │                                                   │
│         ├──► pages/  (Page Object Model — NASIL tıklanacak)│
│         │                                                   │
│         └──► util/   (istatistik motoru — NE ZAMAN,        │
│                        NE KADAR, HANGİ HIZDA)               │
└──────────────────────────┬──────────────────────────────┘
                            │ HTTP (gerçek ağ, eth0)
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Raspberry Pi (Server)                     │
│   Nginx → techmarket.lab (14 sayfalık sahte e-ticaret)     │
│   Zeek  → tüm trafiği conn.log/http.log/dns.log'a yazar    │
└─────────────────────────────────────────────────────────┘
```

Üç katman net olarak ayrılmış durumda:
- **"Ne yapılacak"** (scenarios) davranıştan,
- **"Nasıl tıklanacak"** (pages) HTML detaylarından,
- **"Ne zaman/ne kadar"** (util) istatistikten

birbirinden bağımsız. Bu ayrım önemli çünkü örneğin site HTML'i değişse sadece `pages/` değişir, davranış mantığına dokunulmaz.

---

## 3. Paket Yapısı — Dosya Dosya

### `com.ids.bot` (kök paket — giriş noktaları)

| Dosya | Görevi |
|---|---|
| `App.java` | **Tek-senaryo çalıştırıcı.** `mvn exec:java -Dexec.args="browsing"` gibi çağrılır. `createDriver(userAgent)` adlı **public, paylaşılan fabrika metodunu** barındırır — hem kendisi hem `ParallelRunner` hem de testler bu metodu kullanır, böylece "ChromeDriver nasıl kurulur" mantığı tek yerde yaşar. `disableBrowserCache()` metodu CDP (Chrome DevTools Protocol) komutlarıyla tarayıcı cache'ini kapatır — bu olmadan tekrar ziyaret edilen sayfalar ağa hiç çıkmaz, log'larda görünmez (proje tarihinde bulunmuş kritik bir hataydı). |
| `ParallelRunner.java` | **Çoklu-senaryo çalıştırıcı.** `ExecutorService` (sabit 3 thread'lik havuz) ile üç botu **gerçekten aynı anda** çalıştırır. Her thread kendi izole `ChromeDriver`'ını `App.createDriver()` üzerinden alır, kendi User-Agent'ını seçer, kendi log etiketiyle (`[bot-browsing]` gibi) yazar. Bir botun çökmesi diğerlerini etkilemez (her thread kendi hata yakalamasını yapar). |

### `com.ids.bot.scenarios` (davranış katmanı)

Üç senaryo, üç farklı "kullanıcı tipi":

| Sınıf | Taklit ettiği kullanıcı | Karakteristik davranış |
|---|---|---|
| `BrowsingScenario.java` | Amaçsız gezinen ziyaretçi | En uzun oturum (ort. 8 adım), ürün detaylarına sık girer, geri döner |
| `SearchingScenario.java` | Belirli bir ürün arayan alıcı | Orta uzunlukta (ort. 5 adım), %40 ihtimalle sepete ekler |
| `FormFillingScenario.java` | İletişime geçmek isteyen ziyaretçi | En kısa (ort. 3 adım), her zaman iletişim formunu doldurup gönderir, %30 ihtimalle sonra ana sayfaya döner |

Her senaryo şu üç bileşeni birlikte kullanır:
1. **`MarkovTransitionModel`** — "Şu an X sayfasındaysam, sıradaki sayfa ne olmalı?" sorusunun cevabı, sabit/uniform rastgelelik değil, **birinci derece Markov zinciri** (yani bir önceki duruma bağlı olasılık matrisi).
2. **`SessionIntensity`** — "Bu oturum kaç adım sürecek?" sorusunun cevabı, persona'ya özel Gaussian dağılımdan örneklenir.
3. **`TimingProfile`** — "Adımlar arasında ne kadar bekleyeceğim?" sorusunun cevabı, CICIDS'ten fit edilmiş log-normal dağılımlardan gelir.

### `com.ids.bot.pages` (Page Object Model — HTML etkileşim katmanı)

| Sınıf | Görevi |
|---|---|
| `BasePage.java` | Ortak Selenium etkileşim mantığı (bekleme stratejileri, element bulma) — diğer sayfa sınıfları bunu miras alır |
| `HomePage.java` | Ana sayfa elementleri ve aksiyonları |
| `ProductsPage.java` | Ürün listesi sayfası |
| `ProductDetailPage.java` | Tekil ürün detay sayfası, sepete ekleme aksiyonu |
| `ContactPage.java` | İletişim formu — alan doldurma ve gönderme |

Bu katman, "Page Object Model" adlı yaygın bir test otomasyonu deseni: her web sayfası kendi sınıfına karşılık gelir, HTML seçicileri (CSS selector'lar) burada yaşar. Site HTML'i değişirse sadece bu dosyalar güncellenir, `scenarios/` katmanına dokunulmaz.

### `com.ids.bot.util` (istatistik ve destek motoru)

Bu, projenin bilimsel "kalbi" — CICIDS2017 veri setinden türetilmiş istatistiksel parametreleri koda gömen katman:

| Sınıf | Görevi |
|---|---|
| `TimingProfile.java` | Immutable bir "record" — bir personanın zamanlama parametrelerini (log-normal ortalama/std, clamp sınırları) taşır |
| `TimingProfiles.java` | Fabrika sınıfı — `browsing()`, `searching()`, `formFilling()`, `aggregate()` metodlarıyla her personanın `TimingProfile`'ını üretir. CICIDS2017'nin gerçek istatistiksel analizinden (KMeans kümeleme + log-normal fit) türetilmiş sabitleri içerir. |
| `SessionIntensity.java` | Enum — persona başına Gaussian oturum uzunluğu dağılımı (bugün eklendi) |
| `BotState.java` | Botun bulunabileceği sayfa durumlarının (HOME, PRODUCTS, CONTACT vb.) enum tanımı |
| `MarkovTransitionModel.java` | Genel Markov zinciri motoru — "şu durumdan hangi durumlara, ne olasılıkla geçilebilir" mantığını yürütür |
| `BotPersonas.java` | Her senaryonun kendi geçiş matrisini (Markov olasılıkları) tanımlar — örn. Browsing'de HOME→PRODUCTS %60 gibi. **Not:** bu olasılıklar CICIDS'ten değil, davranışsal varsayımdan geliyor (dosyada bu açıkça belirtiliyor, dürüstlük için önemli). |
| `UserAgentPool.java` | 20 gerçekçi tarayıcı/işletim sistemi kombinasyonu, gerçek pazar payına göre ağırlıklı — her oturumda bir kez seçilip sabit kalır |
| `FormDataPool.java` | İletişim formunu doldururken kullanılacak sahte isim/e-posta/mesaj havuzu — **bilinçli olarak Türkçe bırakıldı**, çünkü form seçenekleri (`<option>` etiketleri) gerçek site HTML'iyle birebir eşleşmek zorunda |
| `CicidsParameterGenerator.java` | **Artık `@Deprecated`** — eski bir yaklaşımın kalıntısı, geriye dönük uyumluluk için duruyor, yeni kod `TimingProfile`/`TimingProfiles` kullanıyor |

---

## 4. Bir Bot Çalıştığında Ne Olur — Uçtan Uca Akış

1. `App.main()` çağrılır, hangi senaryo isteniyorsa (`browsing`/`searching`/`formfilling`) parametre olarak alınır.
2. `App.createDriver(userAgent)` çağrılır: `UserAgentPool`'dan rastgele bir UA seçilir, yeni bir `ChromeDriver` başlatılır, CDP komutlarıyla cache kapatılır ve bu **doğrulanır** (sessizce başarısız olamaz — hata varsa exception fırlatılır).
3. İlgili `Scenario` sınıfı örneklenir, `SessionIntensity`'den o personaya özel adım sayısı örneklenir.
4. Döngü başlar: her adımda `MarkovTransitionModel` bir sonraki sayfayı seçer, botun ilgili `Page` sınıfı üzerinden gerçek bir tıklama/navigasyon yapılır, `TimingProfile`'dan örneklenen bir süre kadar beklenir (gerçek insan temposu taklidi).
5. Senaryo bitince (adım sayısı tükenince ya da FormFilling'de form gönderilip HOME-dönüş kararı verilince) driver kapatılır.

`ParallelRunner` kullanıldığında bu akış üç kez, üç ayrı thread'de, üç izole `ChromeDriver` ile eşzamanlı çalışır.

### 4.3 MixedTrafficRunner ve Ground-Truth Session Log

`MixedTrafficRunner`, paralel bot oturumlarını çalıştırırken her oturum için bir **`session_log.csv`** üretir. Bu CSV her satırda şunları içerir: oturumun senaryo tipi (`browsing` / `searching` / `formfilling`), başlangıç ve bitiş Unix zaman damgaları.

Bu dosya, Faz 2'de Zeek/PCAP verisiyle eşleştirilerek hangi trafik akışının hangi persona tarafından üretildiğini gösteren ground-truth etiket kaynağı olarak kullanılır. Örnek çıktı: `session_log_20260706_150546.csv`.

---

## 5. Test Mimarisi

```
src/test/java/com/ids/bot/
├── PageObjectSmokeTest.java          (@Tag("integration"))
└── scenarios/
    ├── BrowsingScenarioTest.java     (unit + @Tag("integration") iç sınıf)
    ├── SearchingScenarioTest.java    (unit + @Tag("integration") iç sınıf)
    └── FormFillingScenarioTest.java  (unit + @Tag("integration") iç sınıf)
```

İki katman net ayrılmış:
- **Lab'sız (unit) testler** — hiçbir tarayıcı/ağ gerektirmez, saniyenin altında çalışır: oturum uzunluğu aralık kontrolleri, Markov geçişlerinin sadece tanımlı hedeflere gittiğinin doğrulanması, FormFilling'in HOME-dönüş oranının 100.000 örnekle istatistiksel doğrulanması.
- **`@Tag("integration")` testler** — gerçek Chrome ve lab ağı gerektirir: cache-bypass'ın gerçekten network'e çıktığının doğrulanması, sepete ekleme davranışı, form gönderiminin gerçek bir HTTP POST ürettiğinin doğrulanması.

Bu ayrım, `mvn test -DexcludedGroups=integration` ile hızlı geri bildirim (günlük geliştirme), `mvn test -Dgroups=integration` ile tam doğrulama (commit öncesi/lab erişimi varken) arasında seçim yapılabilmesini sağlıyor.

---

## 6. Projenin Güçlü Yanları (Dürüst Değerlendirme)

- **Katmanlı ayrım net** — davranış, HTML etkileşimi, istatistik birbirinden bağımsız, her biri değiştirilebilir.
- **İstatistiksel köken şeffaf** — hangi sayının CICIDS'ten geldiği, hangisinin varsayım olduğu kod içinde açıkça not edilmiş (örn. `BotPersonas`'taki Markov olasılıklarının veriden değil varsayımdan geldiği belirtiliyor). Bu, akademik dürüstlük açısından önemli bir detay, çoğu öğrenci projesinde atlanır.
- **Regresyon güvenliği** — cache-bypass gibi daha önce sessizce bozulmuş bir davranış artık bir testle korunuyor.
- **Deprecation disiplini** — eski kod silinmek yerine `@Deprecated` ile işaretlenip iz bırakılıyor, ani kırılmalar önleniyor.
- **"Bir navigasyon = bir bekleme" değişmezi artık tam** — 6 Temmuz 2026'da, `BrowsingScenario` ve `SearchingScenario`'da `homePage.open()` sonrasında bekleme çağrısının atlandığı bulunup düzeltildi. Artık tüm navigasyonlar — senaryo başlangıcındaki ilk navigasyon dahil — timing dağılımından örneklenen bir bekleme ile ayrılıyor; bu, N=10 resmi doğrulama sırasında KS testi tarafından yakalanmış istatistiksel olarak önemli bir düzeltmeydi.

## 7. Zayıf/Riskli Noktalar (Aynı Dürüstlükle)

- **İstatistiksel doğrulama tamamlandı (N=10).** 6 Temmuz 2026'da, ön-döngü wait düzeltmesi sonrasında N=10 resmi çalıştırma tüm personalar için KS testini geçti. Bu bölümdeki eski "iddia kanıtlanmadı" notu artık geçerli değil — bkz. Bölüm 9.
- **Header-seviyesi tutarsızlık bilinçli olarak ertelendi** — UA havuzu 20 farklı tarayıcı taklit ediyor ama gerçek istemci her zaman Chrome; bu, header analizi yapılırsa tespit edilebilir bir çelişki. Şimdilik flow-seviyesi feature'ları etkilemiyor ama Faz 2'de göz ardı edilemeyecek bir borç.
- **Markov olasılıkları veri-temelli değil, varsayım-temelli.** Dosyada dürüstçe belirtilmiş olması iyi, ama bu, sunumda/raporda savunulması gereken bir zayıflık.

---

*Bu rapor, 3 Temmuz 2026 tarihli geliştirme oturumundan derlendi; 6 Temmuz 2026'da N=10 resmi doğrulama, hata kaydı, RITA sonuçları ve regresyon testleriyle güncellendi.*

---

## 9. İstatistiksel Doğrulama — N=10 Resmi Sonuçları (6 Temmuz 2026)

Araç: `action_level_comparison.py` (`ANALYS-BENIGN/`) — HTTP doküman-isteği zaman damgalarından inter-navigasyon gap'i çıkarıp `TimingProfiles.java`'daki mixture modeliyle Monte-Carlo referans CDF üzerinden KS testi yapan action-seviyesi karşılaştırma scripti.

PRODUCT_DETAIL düzeltmesi (5 Temmuz, commit `758ba92`) ve ön-döngü wait düzeltmesi (6 Temmuz, commit `dec1cf7`) uygulandıktan sonra N=10 resmi doğrulama turu çalıştırıldı (`n10_official_fixed_20260706/`).

| Persona | KS Testi | Sonuç |
|---|---|---|
| Browsing | H₀ reddedilmedi | ✅ Geçti |
| Searching | H₀ reddedilmedi | ✅ Geçti |
| FormFilling | H₀ reddedilmedi | ✅ Geçti |

**Referans — N=5 hızlı kontrol değerleri (5 Temmuz akşamı):**

| Persona | KS p-değeri (N=5) |
|---|---|
| Browsing | 0.4442 |
| Searching | 0.2470 |
| FormFilling | 0.1355 |

Bug'lı ilk N=10 turu (`n10_official_20260706/`, ön-döngü wait **yok**): KS testi Browsing ve Searching için reddetti. Düzeltme sonrası `n10_official_fixed_20260706/` tüm personalar için geçti.

---

## 10. Hata Kaydı — Çözüme Kavuşturulmuş Kritik Hatalar

### 10.1 Tarayıcı Önbelleği Zeek Görünürlüğünü Gizliyordu (2 Temmuz 2026)

**Belirti:** Tekrarlı sayfa ziyaretleri Nginx/Zeek log'unda görünmüyordu. Bir 10-aksiyonluk Browsing oturumunda, aynı ürüne ikinci ziyarette Nginx `access.log`'da sıfır yeni istek oluştu.  
**Kök neden:** Chrome'un disk cache'i, `--disk-cache-size=0` ve `--disable-application-cache` flag'leriyle kapatılamıyordu (ikincisi modern Chrome'da no-op).  
**Düzeltme:** CDP (`Network.enable` + `Network.setCacheDisabled(true)`) — `enable` olmadan `setCacheDisabled` sessizce no-op kalıyor; bu sıra şarttır.  
**Konum:** `App.java` → `disableBrowserCache()`.

### 10.2 PRODUCT_DETAIL Durumundan Bağımsız Yeniden Yükleme (5 Temmuz 2026)

**Belirti:** Browsing KS testi sürekli reddediliyordu (p ≤ 0.05). Inter-navigasyon gap dağılımı beklentinin altında çıkıyordu.  
**Kök neden:** `BrowsingScenario` ve `SearchingScenario` içinde `case PRODUCT_DETAIL` bloğu, `current` durumundan bağımsız olarak her seferinde `productsPage.open()` çağırıyordu. Dominant geçiş PRODUCTS→PRODUCT_DETAIL (%55 / %80) olduğundan bot çoğu zaman zaten products.html'deyken oraya gereksizce yeniden gidiyordu — bu sıfır beklemeyle ikinci bir navigasyon üretiyordu.  
**Düzeltme:** `if (current != BotState.PRODUCTS)` kontrolü eklendi. Azınlık geçişlerde de `waitBetweenActions()` tutarlı uygulandı.  
**Commit:** `758ba92`

### 10.3 CICFlowMeter Eşik Uyumsuzluğu (4 Temmuz 2026)

**Belirti:** N=15 capture'da tüm KS testleri kesin reddedildi (p ≈ 0).  
**Kök neden:** Python `cicflowmeter`'ın `ACTIVE_TIMEOUT` sabiti varsayılan olarak 5ms; CICIDS2017'nin gerçek eşiği 5 saniye (1000× fark).  
**Düzeltme:** `pcap_to_csv.py`'de `--active-timeout` parametresi eklendi; `constants.ACTIVE_TIMEOUT` modül referansıyla runtime'da 5.0 saniyeye override ediliyor.

### 10.4 FWD IAT Zero-Inflation (2 Temmuz 2026)

**Belirti:** Üretilen bekleme sürelerinin %19'u `Math.max(1, ...)` clamp'i nedeniyle yapay olarak 1ms'ye yığılıyordu — CICIDS gerçek trafiğinde olmayan tespit edilebilir bir imza.  
**Kök neden:** Tek log-normal dağılım, CICIDS'teki gerçek zero-inflation yapısını modelleyemiyordu.  
**Düzeltme:** Active/Idle için kullanılan zero-inflated model FWD IAT'a da uygulandı — Bernoulli kapısı (`P_FWD_NEAR_ZERO=0.1934`) + near-zero bandı (1-50ms uniform) + koşullu log-normal + rejection sampling.  
**Sonuç:** 1ms'ye yığılma %19 → %1.22.

### 10.5 Ön-Döngü Bekleme Atlanıyordu (6 Temmuz 2026)

**Belirti:** N=10 resmi doğrulama sırasında Browsing ve Searching için KS testi reddedildi. `homePage.open()` → döngünün ilk navigasyonu arası gap her zaman ~23-25ms çıkıyordu.  
**Kök neden:** `BrowsingScenario.run()` ve `SearchingScenario.run()` içinde `homePage.open()` çağrısından hemen sonra `waitBetweenActions()` çağrılmıyordu. "Bir navigasyon = bir bekleme" değişmezi döngü içinde tutarlı uygulanıyordu ama senaryo başlangıcındaki ilk navigasyon için atlanmıştı.  
**Düzeltme:** Her iki dosyada da `homePage.open()` satırının hemen ardına `waitBetweenActions(timingProfile)` eklendi.  
**Konum:** `BrowsingScenario.java:38`, `SearchingScenario.java:40`  
**Commit:** `dec1cf7`  
**Regresyon testi:** `firstInterNavigationGapIsNotSkipped` — bkz. Bölüm 12.

---

## 11. RITA Beacon Skoru — Kararsız Sonuç (5 Temmuz 2026 Akşamı)

`MixedTrafficRunner` (3-eşzamanlı bot) ve gerçek insan gezintisi üzerinde kontrollü RITA beacon testleri yapıldı (eşzamanlılık, örneklem büyüklüğü ve gezinme hızı ayrı ayrı değiştirilerek izole edildi):

| Test Koşulu | Beacon Score | Severity |
|---|---|---|
| Genel ölçüm (temiz veri, sabah) | 0.275 | None |
| Genel ölçüm (kirli veri, akşam) | 0.426 | None |
| Bot — 3-eşzamanlı (MixedTrafficRunner) | **0.638** | Low |
| Bot — tek-sıralı | 0.568 | Low |
| Bot — 7-bağlantı örneklemi | 0.615 | Low |
| İnsan — hızlı gezinme | 0.272 | None |
| İnsan — yavaş gezinme | 0.892 | Medium |

**Sonuç:** Hiçbir senaryo "High" eşiğini (≥ 0.90) aşmadı. İnsan yavaş gezinme (0.892), bot testlerinin büyük bölümünden daha yüksek puan aldı — net, tutarlı bir "bot vs. insan" ayrımı yok. RITA bu trafik türü için kesin bir sinyal üretemiyor.

**Projenin tezi açısından anlamı:** Klasik kural/istatistik-tabanlı NIDS (RITA) bu davranışı ayırt edemiyor. Bu bulgu, Faz 2'deki Autoencoder'ın doldurması beklenen boşluğu doğrudan destekliyor ve projenin "complémentarité" savını somut biçimde güçlendiriyor.

---

## 12. Regresyon Testleri — 6 Temmuz 2026 Eklemeleri

İki yeni `@Tag("integration")` testi eklendi; her ikisi de ön-döngü wait bug'ı (bkz. 10.5) için regresyon güvencesi sağlıyor.

### 12.1 `BrowsingScenarioTest.firstInterNavigationGapIsNotSkipped`

**Ne test ediyor:** `BrowsingScenario.run()` içinde `homePage.open()` sonrasındaki beklemenin gerçekten çalıştığını — yani ilk inter-navigasyon gap'inin timing dağılımından örneklenmesi gerektiğini.

**Yöntem:** `EventFiringDecorator` + `WebDriverListener.beforeAnyWebDriverCall()` ile `driver.get()` çağrılarının zaman damgaları yakalanıyor. Deterministik `TimingProfile` kullanılıyor (active=300ms, idle=300ms, `pActiveIdleCycle=1.0` — her zaman active+idle dalı). İlk gap ≥ 550ms olmalı.

**Neden `beforeAnyWebDriverCall`:** `beforeGet(WebDriver, String)` override'ı, Selenium 4'ün `EventFiringDecorator`'ındaki reflection-tabanlı dispatch (`callListenerMethod` → `method.invoke()`) + Java 9+ modül sistemi + ByteBuddy proxy kombinasyonunda sessizce tetiklenmiyordu (`IllegalAccessException` yutuluyordu). `beforeAnyWebDriverCall` ise `invokeinterface` ile doğrudan tetikleniyor.

### 12.2 `SearchingScenarioTest.firstInterNavigationGapIsNotSkipped`

`BrowsingScenarioTest`'in aynı bug için `SearchingScenario`'ya uyarlanmış versiyonu. Test mantığı ve assertion eşiği aynı (≥ 550ms); `SearchingScenario(decorated, fixedProfile)` test-constructor'ını kullanıyor.

---

## 15. Git Commit Geçmişi — Önemli Değişim Noktaları

| Hash | Tarih | Açıklama |
|---|---|---|
| `94a98b2` | 4 Temmuz 2026 | Kaza sonrası ilk yeniden inşa — temel proje yapısı |
| `e4b2ee8` | 4 Temmuz 2026 | Sepete ekleme selector düzeltmesi |
| `a285703` | 4 Temmuz 2026 | Ürün adı selector + form subject düzeltmeleri |
| `44f5e07` | 4 Temmuz 2026 | `FormDataPool.SUBJECTS` kapsamı + deterministik kapsama testi |
| `758ba92` | 5 Temmuz 2026 | PRODUCT_DETAIL reload fix + Little's Law kalibrasyonu |
| `ab236b0` | 6 Temmuz 2026 | `MixedTrafficRunner`'a ground-truth `session_log.csv` eklendi |
| `dec1cf7` | 6 Temmuz 2026 | Ön-döngü wait bug düzeltmesi (Browsing + Searching) |
| `cae7a2c` | 6 Temmuz 2026 | Regresyon testleri: `firstInterNavigationGapIsNotSkipped` |

Tam geçmiş: `git log --oneline` (`~/Desktop/selenium-bot/`)
