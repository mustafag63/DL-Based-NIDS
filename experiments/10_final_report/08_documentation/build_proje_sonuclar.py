"""
Proje_Sonuclar_TR.pdf -- genel okuyucu seviyesinde Turkce ozet rapor,
guncel (19-feature, concurrency_src_1s dahil) v2 sonuclarina gore.
reportlab + DejaVuSans (Turkce karakter destegi icin -- pdf_style_tr.py).
"""
import os

from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Spacer, PageBreak

from pdf_style_tr import (
    TITLE, SUBTITLE, BODY, NOTE, PAGE_SIZE, MARGINS,
    p, h1, h2, h3, bullets, hr, source_note, make_table, figure,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_PATH = os.path.join(HERE, "Proje_Sonuclar_TR.pdf")

FIG = lambda *parts: os.path.join(PROJECT_ROOT, *parts)

story = []

# ============================================================ BAŞLIK
story.append(p("NIDS Projesi — Genel Sonuç Raporu", TITLE))
story.append(p("VAE ve Dense Autoencoder ile Anomali Tabanlı Saldırı Tespiti — "
              "Güncel Model (19 Feature, concurrency_src_1s Dahil)", SUBTITLE))
story.append(p("<i>Tarih: 30 Temmuz 2026 — Kapsam: proje kökü, "
              "10_final_report/CHANGELOG.md'deki tüm ilgili maddeler</i>", NOTE))
story.append(hr())

# ============================================================ 1. GİRİŞ
story.append(h1("1. Giriş — Bu Proje Ne Yapıyor"))
story.append(p(
    "Bu proje, bir laboratuvar ağında toplanan gerçek trafik akışlarından (Zeek "
    "<i>conn.log</i> kayıtları) yola çıkarak, <b>ağ saldırılarını normal (benign) "
    "trafikten ayırt eden</b> iki farklı unsupervised (etiketsiz-eğitim) anomali "
    "tespit modeli geliştiriyor: bir <b>VAE (Variational Autoencoder)</b> ve bir "
    "<b>Dense Autoencoder</b>. Her iki model de sadece normal trafikle eğitiliyor; "
    "model 'normal'in nasıl göründüğünü öğreniyor, ve test zamanında bir flow'u "
    "kendi öğrendiği kalıba göre ne kadar kötü 'yeniden inşa edebildiğine' "
    "(reconstruction error) bakarak anormal (potansiyel saldırı) olup olmadığına "
    "karar veriyor."))
story.append(p(
    "Test edilen 3 saldırı tipi:"))
story.append(bullets([
    "<b>portscan</b> — hedef makinede açık port arayan, çok sayıda kısa/başarısız bağlantı üreten bir tarama aracı.",
    "<b>slowloris</b> — bağlantıyı olabildiğince uzun süre açık tutarak sunucu kaynaklarını tüketmeye çalışan bir DoS aracı.",
    "<b>apache_bench (ab)</b> — normalde bir performans/yük test aracı; burada saldırgan tarafından, sunucuyu yormak için aynı HTTP isteğini çok hızlı ve çok sayıda tekrarlamakta kullanılıyor.",
]))
story.append(p(
    "Rapor boyunca geçen <b>threshold_95</b>, benign doğrulama (validation) "
    "akışlarının reconstruction-error dağılımının 95. persentilidir — 'benign "
    "trafiğin en kötü %5'inin üzerinde kalan her şey alarm' kuralı. Her metriğin "
    "tam tanımı ve neden seçildiği için bkz. <i>Metrikler_Aciklama_TR.pdf</i>."))

# ============================================================ 2. FAZ 1-2-3
story.append(h1("2. Faz 1-2-3 — Veri, Feature'lar, Model (Kısa Özet)"))
story.append(h2("Faz 1 — Veri Toplama"))
story.append(p(
    "8 ayrı capture penceresinde (window_01_0pct … window_08_22pct), benign ve "
    "saldırı trafiği eşzamanlı olarak toplandı; hedef saldırı yüzdeleri %0-22 "
    "arasında değişiyor. Toplama sırasında iki ciddi altyapı hatası (Zeek "
    "process restart'ı, ağ kartı checksum-offloading sorunu) tespit edilip "
    "düzeltildi ve etkilenen pencereler yeniden yakalandı — bozuk veri hiçbir "
    "analize girmedi."))
story.append(h2("Faz 2 — Feature Extraction ve Leakage-Free Split"))
story.append(p(
    "Her flow'dan 18 modelleme feature'ı çıkarıldı: 8 ölçeklenmiş sayısal "
    "değer (süre, byte/paket sayıları, byte/paket oranları) ve 10 one-hot "
    "kategorik sütun (protokol, servis, bağlantı durumu). Train/val/test "
    "ayrımı, neredeyse-özdeş flow'ların (aynı araç, aynı parametrelerle "
    "üretilmiş) farklı split'lere sızmasını önlemek için <b>signature bazlı "
    "gruplama</b> ile yapıldı; ölçekleyici (StandardScaler) sadece train "
    "split'ine fit edildi — test/val bilgisi hiçbir zaman ölçeklemeye "
    "karışmadı (leakage-free kural, proje boyunca korundu)."))
story.append(h2("Faz 3 — Model Mimarisi ve Eğitim"))
story.append(p(
    "Her iki model de aynı temel mimariyi paylaşıyor: "
    "<i>Input → Dense(16) → Dropout → Dense(8, bottleneck) → Dropout → "
    "Dense(16) → Output</i>. VAE'de bottleneck, bir ortalama/varyans "
    "(z_mean/z_log_var, latent boyut=10, β=0.25) çiftine dönüşüyor; Dense "
    "autoencoder'da bottleneck doğrudan 8 boyutlu bir sıkıştırma. Adam "
    "optimizer, MSE loss, en fazla 200 epoch, erken durdurma (patience=12). "
    "VAE, tamamen ayrı bir capture penceresinden (window_10, sadece benign, "
    "3.049 flow) eğitildi; Dense ise windows 01-08'in train split'inden "
    "(23.274 flow, ~7,6× daha büyük) — bu eğitim-verisi farkı, iki modelin "
    "karşılaştırmasında hep akılda tutulması gereken bir not (bkz. bağımsız "
    "denetim bulgusu O5, aşağıda)."))

# ============================================================ 3. DENETİM
story.append(h1("3. Bağımsız Denetim (Fable Review) — Özet"))
story.append(p(
    "Proje, sonuçlar ilk kez raporlanmadan önce bağımsız bir teknik denetimden "
    "geçirildi (<i>11_fable_review/independent_audit.md</i>). Denetim 2 kritik "
    "(K1, K2) ve 7 orta düzey (O1-O7) bulgu tespit etti; hepsi ele alındı ve "
    "düzeltildi veya rapor metnine sınırlama notu olarak eklendi — hiçbiri "
    "gözlerden kaçırılmadı."))
story.append(make_table(
    ["Kod", "Bulgu", "Ne yapıldı"],
    [
        ["K1", "Kontaminasyon sweep'inde benign ve attack farklı capture "
               "oturumlarından geliyordu — window-artefaktı ile saldırı "
               "etiketi birbirine karışabilirdi (confound).",
               "Deconfounded doğrulama kolu eklendi (11_deconfounded_check/); "
               "ana bulgular confound altında da geçerli çıktı."],
        ["K2", "Benign train/val/test ayrımı düz rastgele permütasyonla "
               "yapılıyordu — Faz 2'nin signature-gruplama disiplini "
               "kontaminasyon sweep'inde uygulanmamıştı.",
               "Signature-gruplu split ile yeniden doğrulama yapıldı."],
        ["O1", "VAE'nin nominal latent boyutu (10), onu besleyen katmandan "
               "(8) geniş — mimari olarak tutarsız.",
               "latent=8 ile ayrı bir ablasyon koşturuldu: sonuçlar "
               "istatistiksel olarak ayırt edilemez çıktı (bkz. final "
               "rapor, latent-dimension notu)."],
        ["O2", "VAE anomali skoru tek stokastik örnekle (reparametrizasyon "
               "trick'i, sabit olmayan seed) hesaplanıyordu — sayılar "
               "çalıştırmadan çalıştırmaya değişebiliyordu.",
               "Skorlama <b>deterministik z_mean</b>'e geçirildi (z = z_mean, "
               "örnekleme yok); bu değişiklik concurrency_src_1s retrain'ine "
               "de (VAE v2) baştan uygulandı."],
        ["O3", "Resampled pencereler (window_resampled_15/20pct) test "
               "setinde bazı flow'ların iki kopyasını barındırıyor — "
               "metrikler çift sayabiliyor.",
               "Dedup sağlamlık kontrolü yapıldı (davranışsal metriklerde "
               "fark &lt;0.02); <b>bu düzeltme güncel (19-feature) "
               "PR-AUC/F1 sayılarına henüz yeniden uygulanmadı — bkz. "
               "Bölüm 6, açık sınırlama.</b>"],
        ["O4", "Threshold_95 yöntemi (küçük val setinden %95 persentil) "
               "gürültülü ve val→test transferinde küçük bir sistematik "
               "sapma taşıyor.",
               "Etki büyüklüğü ölçüldü ve rapora sınırlama notu olarak "
               "eklendi (bkz. final rapor)."],
        ["O5", "VAE-vs-Dense karşılaştırması, farklı eğitim verisi ve "
               "kapsamıyla confound'lu (mimari farkı mı, veri farkı mı "
               "belirsiz).",
               "Rapor metinlerine bu confound'u açıkça belirten bir not "
               "eklendi."],
        ["O6", "Segmented-injection'daki benign-segment FPR farkları "
               "'örneklem gürültüsü' diye yorumlanmıştı; aslında window "
               "bazlı sistematik bir kompozisyon farkıydı.",
               "Yorum düzeltildi; ana bulgu (apache_bench recall'unun blok "
               "halinde de düşük kalması) etkilenmedi."],
        ["O7", "Ground truth (is_attack) davranışa değil, kaynak IP "
               "kimliğine göre tanımlı — 'saldırgan makine' ile 'kötücül "
               "davranış' birebir örtüşmüyor.",
               "Tehdit modeli sınırlaması olarak rapor metnine ve "
               "dokümantasyona eklendi."],
    ],
    col_widths=[1.3 * cm, 7.3 * cm, 7.4 * cm],
))
story.append(Spacer(1, 4))
story.append(source_note("11_fable_review/independent_audit.md"))

# ============================================================ 4. APACHE_BENCH
story.append(PageBreak())
story.append(h1("4. apache_bench Sorunu — Bulgu, Araştırma, Çözüm"))
story.append(h2("4.1 Ne bulundu"))
story.append(p(
    "Saldırı tipine göre kırılmış (ayrıştırılmış) performans ölçümü "
    "yapıldığında, toplu (agregat) metriğin gizlediği ciddi bir zayıflık "
    "ortaya çıktı: <b>apache_bench neredeyse hiç tespit edilmiyordu</b> "
    "(recall ≈ %2,6-3,3, ROC-AUC ≈ 0,58-0,70), portscan ve slowloris ise "
    "neredeyse kusursuzdu (recall ≥ %98,8). apache_bench, saldırı flow'larının "
    "yaklaşık yarısını oluşturduğundan, bu zayıflık toplu metrikte kayboluyordu."))
story.append(h2("4.2 Neden kaçırılıyordu"))
story.append(p(
    "apache_bench aynı kısa HTTP isteğini defalarca tekrarlıyor. Tek bir flow "
    "olarak bakıldığında bu istek sıradan, benign bir HTTP bağlantısından "
    "istatistiksel olarak ayırt edilemiyor — 18 feature'ın hiçbiri flow'lar "
    "<i>arasındaki</i> ilişkiyi (tekrar hızı, eşzamanlılık) yakalamıyordu, "
    "hepsi tek bir flow'u kendi başına değerlendiriyordu."))
story.append(h2("4.3 Araştırma: bir başarısız, bir başarılı deneme"))
story.append(p(
    "<b>Önce denenen (başarısız): flow'lar-arası zaman farkı (IAT).</b> "
    "<i>13_temporal_feature_experiment/</i>'de, bir flow ile aynı kaynak "
    "IP'nin bir önceki flow'u arasındaki süre feature olarak eklenip "
    "modeller yeniden eğitildi. Sonuç: recall hiç değişmedi (KS istatistiği "
    "sadece 0,375 — mevcut feature'lardan zayıf). Bu deney ayrıca ilginç "
    "bir yan bulgu ortaya çıkardı: ilk teşhis analizindeki 'apache_bench "
    "medyan IAT'ı benign'den 2364× kısa' bulgusu, ölçümün seyrek bir test "
    "alt kümesinde yapılmasından kaynaklanan bir <b>artefakttı</b> — tüm "
    "flow'lar üzerinde doğru hesaplandığında fark sadece ~2×'ye iniyordu."))
story.append(p(
    "<b>Sonra denenen (başarılı): pencere-bazlı yoğunluk (concurrency).</b> "
    "<i>14_concurrency_feature_experiment/</i>'de, bir flow'un kendi zaman "
    "damgası etrafında (±1 saniye) aynı kaynak IP'den kaç flow daha geldiği "
    "sayıldı (<b>concurrency_src_1s</b>). Bu feature apache_bench'i güçlü "
    "şekilde ayırt etti ve retrain sonrası recall'u kalıcı olarak yükseltti. "
    "Knock-out testi (feature'ı dondurup modeli aynen değerlendirme) "
    "iyileşmenin gerçekten bu feature'dan geldiğini doğruladı."))
story.append(h2("4.4 Canonical modele entegrasyon — 3 aşamalı retrain"))
story.append(bullets([
    "<b>Aşama 1 — Dense v2:</b> concurrency_src_1s, Dense pipeline'ının "
    "feature tablosuna eklendi (log1p + sadece benign-train'e fit "
    "StandardScaler, leakage-free); Dense autoencoder 5 seed ile "
    "19-feature üzerinde yeniden eğitildi.",
    "<b>Aşama 2 — VAE v2:</b> aynı feature, VAE'nin tamamen ayrı eğitim "
    "verisi kaynağı olan window_10 için de (Dense v2'nin AYNI scaler'ıyla, "
    "refit edilmeden — assert ile doğrulandı) hesaplandı; VAE 5 seed ile "
    "19-feature üzerinde, deterministik z_mean skorlamayla yeniden eğitildi.",
    "<b>Aşama 3 — Pairwise + Segmented:</b> her iki yeni model, ikili "
    "kombinasyon ve bloklu-enjeksiyon protokolleriyle de değerlendirildi.",
]))
story.append(p(
    "Sonrasında eski (18-feature) tüm sonuçlar <i>V1_ARCHIVE/</i>'a taşındı "
    "(silinmedi) ve 19-feature sonuçlar tek canonical sürüm oldu."))
story.append(source_note("10_final_report/CHANGELOG.md, 2026-07-30 tarihli maddeler; "
                         "V1_ARCHIVE/README.md"))

# ============================================================ 5. GÜNCEL SONUÇLAR
story.append(PageBreak())
story.append(h1("5. Güncel (v2) Sonuçlar — Her İki Model"))
story.append(p(
    "Aşağıdaki tüm sonuçlar canonical modele aittir: 19 feature "
    "(concurrency_src_1s dahil), 5 seed, threshold_95 seed başına yeniden "
    "hesaplanmış. <b>Pooled recall</b>, bir ikili (pair) değerlendirme "
    "setindeki TÜM saldırı flow'larının ortalama recall'udur; <b>decomposed "
    "recall</b> ise aynı setin içindeki tek bir saldırı tipinin (örn. "
    "sadece apache_bench) kendi recall'udur — ayrım Bölüm 5.2'de somut "
    "sayılarla gösteriliyor."))

story.append(h2("5.1 Tekli saldırı tipi (single attack-type)"))
story.append(make_table(
    ["Model", "Saldırı tipi", "ROC-AUC", "PR-AUC", "F1", "Benign FPR", "Recall"],
    [
        ["Dense", "apache_bench", "0,9808 ± 0,0076", "0,8930", "0,8218", "0,0660 ± 0,0036", "0,9092 ± 0,0382"],
        ["Dense", "portscan", "0,9997 ± 0,0002", "0,9973", "0,7551", "0,0660 ± 0,0036", "1,0000 ± 0,0000"],
        ["Dense", "slowloris", "1,0000 ± 0,0000", "1,0000", "0,8050", "0,0660 ± 0,0036", "1,0000 ± 0,0000"],
        ["VAE", "apache_bench", "0,9836 ± 0,0123", "0,9035 ± 0,0805", "0,8428 ± 0,0337", "0,0664 ± 0,0110", "0,9500 ± 0,0453"],
        ["VAE", "portscan", "0,9998 ± 0,0001", "0,9983", "0,7551", "0,0664 ± 0,0110", "1,0000 ± 0,0000"],
        ["VAE", "slowloris", "1,0000 ± 0,0000", "1,0000", "0,8048", "0,0664 ± 0,0110", "1,0000 ± 0,0000"],
    ],
    col_widths=[1.6 * cm, 2.7 * cm, 2.9 * cm, 2.3 * cm, 1.8 * cm, 2.7 * cm, 2.0 * cm],
    highlight_col=6,
))
story.append(Spacer(1, 4))
story.append(source_note("09_dense_v2_comparison/results_single_attack_type_dense_v2.csv/.md, "
                         "10_vae_v2_comparison/results_single_attack_type_vae_v2.csv/.md"))

story.append(figure(FIG("10_final_report", "01_single_attack_type", "dense", "roc_pr_apache_bench.png"),
                    "Şekil 1 — Dense autoencoder, apache_bench için ROC ve Precision-Recall eğrileri."))
story.append(figure(FIG("10_final_report", "01_single_attack_type", "vae", "roc_pr_apache_bench.png"),
                    "Şekil 2 — VAE, apache_bench için ROC ve Precision-Recall eğrileri."))

story.append(h2("5.2 İkili kombinasyonlar (pairwise)"))
story.append(make_table(
    ["Model", "Çift", "ROC-AUC", "Pooled Recall", "apache_bench-only Recall (decomposed)"],
    [
        ["Dense", "portscan + apache_bench", "0,9868 ± 0,0052", "0,9381 ± 0,0261", "0,9092 ± 0,0382"],
        ["Dense", "apache_bench + slowloris", "0,9882 ± 0,0046", "0,9441 ± 0,0235", "0,9092 ± 0,0382"],
        ["VAE", "portscan + apache_bench", "0,9887 ± 0,0084", "0,9659 ± 0,0309", "0,9500 ± 0,0453"],
        ["VAE", "apache_bench + slowloris", "0,9899 ± 0,0076", "0,9692 ± 0,0279", "0,9500 ± 0,0453"],
    ],
    col_widths=[1.6 * cm, 4.6 * cm, 2.9 * cm, 3.0 * cm, 5.9 * cm],
))
story.append(Spacer(1, 4))
story.append(p(
    "apache_bench'in kendi (decomposed) recall'u, hangi diğer saldırı "
    "tipiyle eşleştirildiğinden bağımsız olarak <b>sabit</b> kalıyor "
    "(Dense: her koşulda 0,9092; VAE: her koşulda 0,9500) — pooled "
    "recall'daki artış, sadece daha iyi tespit edilen bir tipin karışıma "
    "eklenmesinden kaynaklanan bir karışım etkisi, apache_bench'in kendi "
    "tespitinde bir iyileşme değil."))
story.append(source_note("11_pairwise_segmented_v2/{dense_v2,vae}/results.md"))

story.append(h2("5.3 Bloklu (segmented) enjeksiyon"))
story.append(p(
    "Aynı test flow'ları, karışık sırada değil, bitişik bloklar halinde "
    "yeniden sıralandı: benign → apache_bench → benign → slowloris → "
    "benign → portscan → benign. Amaç: saldırı tipi izole bir blok halinde "
    "gelse bile modelin davranışının değişip değişmediğini kontrol etmek."))
story.append(figure(FIG("10_final_report", "03_segmented_injection", "dense", "error_plot.png"),
                    "Şekil 3 — Dense autoencoder, bloklu enjeksiyon akışı boyunca reconstruction error "
                    "(log ölçek, 5 seed ortalaması). threshold_95 = 0,1256."))
story.append(figure(FIG("10_final_report", "03_segmented_injection", "vae", "error_plot.png"),
                    "Şekil 4 — VAE, aynı akış. threshold_95 = 0,0987."))
story.append(p(
    "Her iki modelde de blok-recall, karışık test setindeki recall'la "
    "birebir aynı çıktı (Dense apache_bench bloğu: 0,9092; VAE: 0,9500) — "
    "modelin her flow için verdiği karar, o flow'un akışta nerede "
    "durduğundan bağımsız, statik bir karar."))
story.append(source_note("11_pairwise_segmented_v2/{dense_v2,vae}/block_recall_f1.md"))

story.append(h2("5.4 Özet: değişimin büyüklüğü"))
story.append(figure(FIG("10_final_report", "07_final_written_report", "figures", "apache_bench_before_after.png"),
                    "Şekil 5 — apache_bench recall ve ROC-AUC, eski (18 feature) ve yeni "
                    "(19 feature, concurrency_src_1s dahil) model, her iki mimari."))

# ============================================================ 6. AÇIK SINIRLAMA
story.append(PageBreak())
story.append(h1("6. Açık Sınırlama Notu"))
story.append(p(
    "<b>O3 dedup-prevalence düzeltmesi, güncel (19-feature) PR-AUC/F1 "
    "sayılarına henüz yeniden uygulanmadı.</b> Eski (18-feature) rapor, "
    "resampled pencerelerin (window_resampled_15pct/20pct) test setinde "
    "bazı gerçek flow'ları iki kez saydığını tespit edip (bağımsız denetim "
    "bulgusu O3), PR-AUC/F1'i dedup edilmiş bir test setinden yeniden "
    "hesaplayan bir düzeltme uygulamıştı — ROC-AUC/recall/FPR gibi "
    "davranışsal metriklerin bu çift-saymadan etkilenmediği ayrıca "
    "doğrulanmıştı (fark &lt;0,02). Bu düzeltme, concurrency_src_1s "
    "entegrasyonu sonrası güncel modele <b>henüz yeniden uygulanmadı</b> — "
    "bu raporda gösterilen ROC-AUC, recall ve FPR sayıları güvenilir "
    "kabul edilebilir, ancak PR-AUC ve F1 sayıları düzeltme uygulanana "
    "kadar <b>geçici (provisional)</b> olarak okunmalı. Bu, bilinen ve "
    "takip edilen bir sonraki adım, sessizce göz ardı edilmiş bir hata "
    "değil."))
story.append(source_note("V1_ARCHIVE/10_final_report/01_single_attack_type/vae/dedup_sanity_check/; "
                         "10_final_report/07_final_written_report/rapport_final_attack_type_analysis.md, Bölüm 6"))

doc = SimpleDocTemplate(OUT_PATH, pagesize=PAGE_SIZE, **MARGINS,
                        title="NIDS Projesi — Genel Sonuç Raporu", author="IDS-Project")
doc.build(story)
print(f"Wrote {OUT_PATH}")
