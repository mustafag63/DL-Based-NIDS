# Bağımsız Denetim Raporu — NIDS Projesi (VAE + Dense Autoencoder)

**Tarih:** 2026-07-28
**Kapsam:** `03_phase3_splits/` (split + scaler mantığı), `phase3_vae/` ve `phase3_dense/` model tanımları, threshold seçimi (%95 percentile val-benign), `06_attack_type_analysis/` + `07_segmented_injection/` değerlendirme script'leri ve bunların `10_final_report/06_scripts/` kopyaları (diff ile birebir aynı oldukları doğrulandı).
**Yöntem:** Sadece okuma/inceleme; hiçbir kod veya veri değiştirilmedi, hiçbir script çalıştırılmadı.

## Genel değerlendirme

Bu proje, bu ölçekteki bir çalışma için alışılmadık derecede öz-eleştirel ve iyi belgelenmiş: split-öncesi-scaler kuralı açıkça uygulanmış, beta seçimindeki test-leakage kendi iç denetiminde (`06_beta_selection_audit/`) yakalanıp düzeltilmiş, posterior collapse ayrı bir soruşturma klasörüyle (`09_collapse_investigation/`) incelenmiş, resampled window'ların yarattığı uid-düzeyi leakage post-hoc düzeltmeyle kapatılmış, apache_bench'in düşük recall'u saklanmak yerine ayrı bir tanı klasörüyle raporlanmış. **Ana pipeline'da (faz2 split + scaler) klasik anlamda bir data leakage bulamadım.** Aşağıdaki bulguların çoğu "yanlış yapılmış" şeyler değil, **sonuçların yorumlanma sınırlarını daraltan tasarım kararları ve gözden kaçmış varsayımlar**. İki tanesi (K1, K2) headline sonucu olan kontaminasyon eğrisinin mutlak değerlerini sorgulatacak kadar önemli; o yüzden "kritik" başlığına koydum.

---

## KRİTİK

### K1. Kontaminasyon sweep'inin test seti: benign ve attack farklı capture oturumlarından geliyor — window-artefaktı ile attack etiketi birbirine karışmış (confound)

`phase3_vae/05_contamination_sweep/prepare_contamination_data.py`:

- Benign havuzu (train **ve** val **ve** test-benign) **sadece `window_10_0pct`**'ten geliyor (satır 100–120).
- Attack havuzu (train kontaminasyonu **ve** test-attack) **sadece `window_02..08`**'den geliyor (satır 37–40, 91–97).

Yani sweep'in kendi test setinde (`01_data/test_set.csv`) "benign vs attack" ayrımı aynı zamanda birebir "window_10 vs window_02-08" ayrımı. window_10 farklı bir günde/oturumda yakalanmış ayrı bir capture; oturumlar arası herhangi bir sistematik fark (ağ yükü profili, servis dağılımı, Zeek/NIC durumu, arka plan trafiği) attack etiketiyle **tamamen alias'lanmış** durumda. Model "saldırıyı" değil "window_10'a benzemeyen her şeyi" ayırt ederek de aynı AUC'yi üretebilir.

**Neden tamamen çürütücü değil:** `06_attack_type_analysis/` aynı contam_0pct modellerini kök test split'i üzerinde (benign'i window_02-08 + resampled'dan gelen) değerlendiriyor ve portscan/slowloris orada da ~0.99–1.00 recall veriyor — yani o iki saldırı tipi için sinyalin gerçek olduğu bağımsız olarak doğrulanmış. Ayrıca confound tüm kontaminasyon seviyelerinde aynı olduğundan eğrinin **göreli** şekli (kontaminasyon arttıkça ne oluyor sorusu) mutlak AUC'lerden daha sağlam.

**Etkisi:** Kontaminasyon eğrisindeki mutlak PR-AUC/ROC-AUC/F1 değerleri olduğundan iyimser olabilir. Raporlarda bu sayılar sunulurken bu sınırlamanın açıkça yazılması gerekir; ideali test-benign'in bir kısmının window_02-08 benign'inden gelmesiydi.

### K2. Kontaminasyon sweep'inin benign train/val/test ayrımı düz rastgele permütasyon — faz2'nin signature-grouping disiplini burada uygulanmamış

`prepare_contamination_data.py` satır 111–116: window_10'un 4356 benign flow'u `rng.permutation` ile %70/15/15'e bölünüyor. Oysa ana pipeline (`faz2_feature_extraction.py`) tam da şu gerekçeyle `GroupShuffleSplit(groups=signature_id)` kullanıyor: aynı araç aynı parametrelerle tekrar tekrar koştuğu için near-duplicate flow'lar var ve bunlar train/val/test'in iki tarafına düşerse değerlendirme iyimserleşiyor. window_10 benign trafiği de aynı Selenium+Locust jeneratörlerinden geliyor — near-duplicate yoğunluğu yüksek olmalı. Düz rastgele bölmede train'deki bir flow'un neredeyse aynısı val'de (threshold'u belirliyor) ve test-benign'de (FPR'yi belirliyor) bulunabilir.

**Etkisi:** Sweep'te benign tarafın reconstruction error'ı yapay olarak düşük, dolayısıyla threshold_95 yapay olarak dar ve benign/attack ayrımı yapay olarak kolay olabilir. K1 ile birleşince sweep'in mutlak metriklerine iki ayrı iyimserlik kaynağı biniyor. Projenin kendi standardına (faz2) göre bir tutarsızlık olduğu için — yani proje bu riski bildiği hâlde burada uygulamadığı için — kritik sayıyorum.

---

## ORTA

### O1. VAE mimarisi: latent_dim (10) > önceki gizli katman (8) — mimari olarak tutarsız, latent sweep'in sonucu bu yüzden şüpheli

Encoder: `18 → Dense(16) → Dense(8) → z_mean/z_log_var(10)`. Latent boyutu, kendisini besleyen katmandan **geniş**. z_mean 8-boyutlu bir aktivasyonun lineer dönüşümü olduğundan latent kod en fazla 8 serbestlik derecesi taşıyabilir; "latent=10" pratikte var olmayan bir kapasite. Notebook'taki latent sweep (6/8/10) bu yüzden elma-armut karşılaştırması: latent=10'un +0.08 AUC farkı ilkesel bir kapasite kazancı değil, büyük olasılıkla seed varyansı (ki `07_seed_variance/` tam da bu varyansın büyük olduğunu göstermiş). Ayrıca:

- Latent sweep **beta=1.0 ile** (yani ağır posterior-collapse rejiminde, 1/10 aktif boyutla) yapılmış, beta sonra latent=10 sabitken seçilmiş. Greedy sıralı seçimin sırası ters: collapse'ı belirleyen beta önce, kapasite sonra seçilmeliydi (ya da grid).
- Nihai model "latent=10, beta=0.25" diye raporlanıyor ama aktif boyut 3/10 — `09_collapse_investigation/` bunun feature uzayının düşük içsel boyutundan beklendiğini ikna edici şekilde gösteriyor, bu iyi; ama o zaman raporlarda "latent=10" yerine "etkin latent ~3, nominal 10" demek daha dürüst olur.

Bu bir "sonuçları geçersiz kılan hata" değil (model çalışıyor, AUC gerçek), ama mimari seçim gerekçesi göründüğü kadar sağlam değil.

### O2. VAE anomaly skoru tek stokastik örnekle hesaplanıyor; notebook versiyonunda seed bile yok

- Notebook'taki `reconstruction_error()` her çağrıda `tf.random.normal` ile **tek bir** z örnekler, seed sabitlenmez → notebook'un thr_pctl/AUC/F1 sayıları çalıştırmadan çalıştırmaya değişir (tam tekrarlanabilir değil).
- Sweep'teki `reconstruction_error(..., eval_seed)` seed'i sabitler (tekrarlanabilirlik ✓) ama seed değeri keyfî (900_000 vs 950_000 offset'leri) ve **tek örneklemli MC tahmini gürültülü**: aynı flow'un skoru keyfî seed'e göre değişir; raporlanan sayılar bu keyfî seçime hafifçe bağlı.
- Deterministik alternatif (z_mean ile skorlamak) veya çok örnekli ortalama (An & Cho tarzı, `10_probabilistic_scoring/`'da zaten denenmiş) ana metrik olarak kullanılmıyor.

**Öneri:** ana raporlardaki skorun ya `z = z_mean` (deterministik) ya da L≥10 örnek ortalaması olması; tek-örnek + keyfî seed en zayıf seçenek.

### O3. Resampled window'lar test setinde aynı flow'un iki kopyasını bulunduruyor — metrikler çift sayıyor

faz2'nin post-hoc düzeltmesi (bölüm 3.5) resampled satırı kaynak-ikizinin split'ine zorluyor; bu train↔test leakage'ı doğru şekilde kapatıyor. Ama yan etkisi: kaynak satır **ve** byte-aynı kopyası artık **aynı** split'te — test setinde aynı gerçek flow iki kez sayılıyor (derive script'inin kendi docstring'ine göre test attack flow'larının ~%31'i resampled kopya). Bu:

- test metriklerinde bağımsız örneklem sayısını olduğundan büyük gösterir (std'ler ve "n_attack" yanıltıcı),
- train tarafında da duplicate'ler bazı flow'lara fiilen 2x ağırlık verir,
- faz2'deki "official seed" seçimi (balance_score) düzeltme **öncesi** split'lerle hesaplanıyor; düzeltme sonrası denge farklı olabilir (script bunun uyarısını basıyor ama seed seçimini yenilemiyor).

Dedup'lu (kopyaları atılmış) bir test varyantıyla ana metriklerin yeniden raporlanması ucuz bir sağlamlık kontrolü olur.

### O4. Threshold yöntemi (%95 percentile val-benign): varsayımları ve zayıf noktaları

Yöntemin örtük varsayımları ve pratikteki gedikleri:

1. **Tasarım gereği ~%5 FPR'a kilitlenir.** Flow-düzeyi bir NIDS için %5 FPR operasyonel olarak çok yüksektir (binlerce flow/saat → yüzlerce yanlış alarm). Bu bir "hata" değil ama raporlarda F1'in bu keyfî çalışma noktasına bağlı olduğu vurgulanmalı; threshold'dan bağımsız metrikler (AUC/PR-AUC) zaten raporlanıyor, iyi.
2. **Val-benign dağılımı = deployment-benign dağılımı varsayımı.** Sweep'te threshold window_10 val-benign'inden (~%15 × 4356 ≈ 653 flow) kalibre edilip `06_attack_type_analysis/`'te window_02-08 benign'ine uygulanıyor — gözlenen FPR ~%5.7, yani transfer bu veride kabaca tutmuş; ama bu şans, garanti değil. Ayrıca projede iki farklı val-benign konvansiyonu var (notebook: Dense'in val'i; sweep: window_10 val'i) — hangi sayının hangi kalibrasyonla üretildiği rapor okurken karışmaya açık.
3. **n=653'ten %95 percentile gürültülüdür** (sıra istatistiği ~33. en büyük değer); seed başına threshold_95 std'sinin görünür olması kısmen bundan.
4. **K2'deki near-duplicate sorunu threshold'u doğrudan etkiler:** train'dekine neredeyse özdeş val flow'ları error dağılımının sol kuyruğunu şişirir, threshold'u aşağı çeker.
5. Kontamine train senaryolarında bile threshold hep **temiz val-benign'den** geliyor — gerçekçi bir "etiketin yok, verin kirli" senaryosunda temiz bir val setin var olmayacağı raporda tartışılmaya değer (sweep'in cevapladığı soru bu değilse de sınırlama olarak yazılmalı).

### O5. VAE-vs-Dense karşılaştırması eğitim verisi ve ölçekleyiciyle confound'lu

`08_dense_v1_comparison/` aynı test akışlarında yan yana tablolar üretiyor, ama iki model:

- farklı train setleriyle (VAE: window_10, 4356 benign; Dense: window_01-08 train split'i, 23 274 benign),
- farklı miktarda veriyle (~5x fark),
- farklı kategori kapsamıyla (window_10'daki icmp/OTH/S0, Dense encoder'ında all-zero kodlanıyor — `prepare_window10.py` bunu dürüstçe belgeliyor)

eğitilmiş. `phase3_vae/README.md` "bu bir mimari karşılaştırma değil" diye açıkça uyarıyor — doğru — ama `08_dense_v1_comparison/` klasörünün çıktıları tablo formatıyla fiilen mimari karşılaştırma gibi okunuyor. Rapor metinlerinde her tabloya bu confound'un dipnot olarak girmesi gerekir.

### O6. Segmented-injection'daki benign-segment FPR farkları "örneklem gürültüsü" diye yorumlanmış; oysa sistematik kompozisyon farkı

`build_segmented_injection.py` benign havuzunu **ts sırasına göre** 4 bitişik dilime bölüyor. Window'lar zamanda ardışık olduğundan segment-0 erken window'ların, segment-6 geç window'ların (ve resampled kopyaların) benign'ini içeriyor. Gözlenen FPR'ler (0.031 / 0.034 / 0.096 / 0.070) rastgele dalgalanma değil, **window-bazlı benign dağılım kaymasının** doğrudan görüntüsü olmalı — segment 4-6'daki FPR, geç window'ların benign profiline modelin daha kötü uyduğunu söylüyor. `results_segmented.md`'deki yorum ("smaller per-segment sample sizes... rather than the model drifting") bu yüzden yanlış varsayım içeriyor; n≈1705'lik segmentlerde %3.1 vs %9.6 farkı örneklem gürültüsüyle açıklanamaz (binom std ≈ %0.5). Segment-FPR'yi window_id'ye göre kırıp bakmak bunu tek satırda netleştirir. (Ana bulguyu — apache_bench recall'unun blok yerleşiminde de düşük kalması — etkilemez; o sonuç per-flow karar mantığı gereği zaten beklenendi ve doğru raporlanmış.)

### O7. Ground truth tanımı IP-bazlı: `is_attack = (orig_h == 192.168.10.2)`

Saldırgan makineden çıkan **her** flow saldırı sayılıyor (OS arka plan trafiği, saldırı komutları arasındaki boşluklarda oluşan bağlantılar dahil), saldırganın **hedef değil kaynak** olmadığı hiçbir flow saldırı sayılamıyor. Lab-IP filtresi (`orig_h ∈ LAB_IPS ∧ resp_h ∈ LAB_IPS`) bunu büyük ölçüde sınırlıyor ve `derive_attack_type_labels.py` çıktısında attack flow'ların %100'ünün 1 sn toleransla bir attack_log komut aralığına eşleşmesi etiketin pratikte temiz olduğunu gösteriyor. Yine de bu, "etiket = davranış" değil "etiket = kaynak kimliği" demek; raporda tehdit modeli sınırlaması olarak bir cümleyle yer almalı (içeriden/yanal hareket gibi senaryolara genellemez).

---

## KOZMETİK / KÜÇÜK

1. **faz2 kırılganlığı:** `split_once()` benign ile signature çakışan attack flow'ları `attack_rest`'ten düşürüyor (satır 229–231); bu satırlar hiçbir split'e girmeyeceği için 308. satırdaki `UNASSIGNED` assert'i patlar. Pipeline çalıştığına göre mevcut veride çakışma boş — ama ileride veri değişirse hata mesajı ("Found unassigned rows!") gerçek nedeni (çakışan-signature attack düşürme) hiç ima etmiyor. Ya düşürülen satırlara açık bir split etiketi verilmeli ya da assert mesajı bu durumu anlatmalı. Ayrıca çakışan attack'leri değerlendirmeden tamamen düşürmek — çakışma boş olmasaydı — "benign'e en çok benzeyen saldırıları testten çıkarma" anlamına gelirdi; bu tasarım tercihi docstring'de gerekçelendirilmemiş.
2. **Performans:** `evaluate_group()` her grup için 20 modeli diskten yeniden yüklüyor (single: 3 grup × 20, pairwise: 3 grup × 20 daha). Model önbelleği eklemek koşum süresini ~1/6'ya indirir. Benzer şekilde `build_combined_features()` her script'te tüm CSV'leri baştan okuyor.
3. `reconstruction_error()` içindeki `tf.random.set_seed(eval_seed)` **global** seed'i değiştiriyor — çağıran süreçteki diğer rastgeleliği de etkiler; `tf.random.Generator` ile lokal tutulabilir.
4. Notebook bölüm 7'de test seti, mimari arayış (bölüm 9) devam ederken bir kez okunmuş — collapse-düzeltme çalışmasını başlatma kararı test sonucu görüldükten sonra alınmış. `06_beta_selection_audit/` seçim-metriği leakage'ını düzeltmiş ama bu "workflow-düzeyi" temas kalıntı olarak duruyor. Sonucu değiştirdiğine dair işaret yok; sadece raporda şeffaflık notu olarak anılabilir.
5. Ağır kuyruklu feature'lar (`byte_ratio`, `bytes_per_sec`) log dönüşümü olmadan StandardScaler'a giriyor; reconstruction error birkaç aşırı-ölçekli feature tarafından domine ediliyor (portscan/slowloris error'larının benign'den ~10⁶ kat büyük olması bunun işareti). Bu, apache_bench gibi "benign ölçeğinde" kalan saldırıların error uzayında görünmez kalmasına katkıda bulunuyor olabilir — `log1p` + scaler denemesi, apache_bench tanı çalışmasının önerdiği yeni feature'lardan daha ucuz bir ilk adım.
6. `AUC_TOLERANCE=0.01`, `ACTIVE_STD_THRESHOLD=0.15`, `ACTIVE_DIM_AUC_TOLERANCE=0.03` eşikleri keyfî ve duyarlılıkları test edilmemiş (seçim kuralları güzelce yazılmış olsa da eşik değerleri sonucu belirliyor: tolerans 0.05 olsaydı KL-annealing 10/10 aktif boyutla seçilebilirdi).
7. `10_final_report/06_scripts/` kopyaları orijinallerle birebir aynı (diff ile doğrulandı) — burada sorun yok; ileride senkron bozulmasın diye kopya yerine symlink/hash notu düşünülebilir.

## Sorun bulunamayan / doğrulanan noktalar

- **faz2 scaler sırası doğru:** StandardScaler yalnızca train split'ine fit ediliyor (satır 379–380), split scaler'dan önce yapılıyor; docstring eski hatalı iki-script versiyonunu da dürüstçe anlatıyor.
- **GroupShuffleSplit mantığı doğru kurulmuş:** signature_id window-önekli, benign %70/15/15 ve attack %50/50 ayrımları grup bazlı, dört split arasında signature kesişimi assert'le kontrol ediliyor.
- **OneHotEncoder'ın global fit'i** bilinçli ve savunulabilir bir istisna (kategori sözlüğü sayısal sızıntı taşımaz) ve açıkça belgelenmiş.
- **Kontaminasyon setlerinin flow_id disjointness'ı** (train-attack ∩ test-attack = ∅ vb.) assert'lerle ve manifest hash'leriyle güvence altında.
- **Model yükleme/serileştirme düzeltmeleri** (Lambda→ClipLogVar) ve beta-seçimi leakage düzeltmesi doğru yapılmış; düzeltilmiş notebook'ta seçim yalnızca val metriklerinden, test tek sefer okunuyor.
- **apache_bench zafiyeti** gizlenmemiş; ayrı tanı script'leriyle araştırılıp raporlanmış.

## Özet öncelik listesi

| # | Bulgu | Ciddiyet | Önerilen aksiyon |
|---|---|---|---|
| K1 | Sweep test setinde benign=window_10, attack=window_02-08 confound'u | Kritik | Raporlara sınırlama notu; mümkünse karma-benign'li test varyantı |
| K2 | Sweep benign split'inde signature-grouping yok | Kritik | Grouped split ile sweep'in en azından 0% noktasını yeniden koş |
| O1 | latent(10) > bottleneck(8); latent seçimi collapse rejiminde yapılmış | Orta | "Etkin latent ~3" olarak raporla; ileride latent ≤ 8 |
| O2 | Tek-örnekli stokastik skor; notebook'ta seed'siz | Orta | z_mean ile deterministik skor veya L≥10 ortalama |
| O3 | Test setinde resampled kopyalar çift sayım | Orta | Dedup'lu test varyantıyla sağlamlık kontrolü |
| O4 | Threshold varsayımları (FPR=5%, küçük val n, dağılım transferi) | Orta | Raporda varsayımları açıkça listele |
| O5 | VAE-Dense karşılaştırması train-verisi confound'lu | Orta | Tablolara dipnot |
| O6 | Benign-segment FPR farkı yanlış yorumlanmış | Orta | Segment FPR'yi window_id kırılımıyla yeniden yorumla |
| O7 | IP-bazlı ground truth | Orta | Tehdit modeli sınırlaması notu |
| 1–7 | Kozmetik maddeler | Düşük | Fırsat buldukça |
