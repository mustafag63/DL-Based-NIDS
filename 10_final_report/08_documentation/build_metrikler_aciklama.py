"""
Metrikler_Aciklama_TR.pdf -- projede kullanılan her metriğin ne anlama
geldiği, nasıl hesaplandığı, neden seçildiği (güncel v2 sonuçlarıyla
somutlaştırılmış). reportlab + DejaVuSans (pdf_style_tr.py).
"""
import os

from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Spacer, PageBreak

from pdf_style_tr import (
    TITLE, SUBTITLE, BODY, NOTE, PAGE_SIZE, MARGINS,
    p, h1, h2, h3, bullets, hr, source_note, make_table,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "Metrikler_Aciklama_TR.pdf")

story = []

story.append(p("Değerlendirme Metrikleri — Kapsamlı Açıklama", TITLE))
story.append(p("NIDS Projesi — VAE ve Dense Autoencoder Anomali Tespiti (Güncel Model, 19 Feature)", SUBTITLE))
story.append(p("<i>Tarih: 30 Temmuz 2026</i>", NOTE))
story.append(hr())

story.append(p(
    "Bu doküman, projede kullanılan her metriği üç düzeyde açıklıyor: "
    "<b>(1)</b> matematiksel tanım, <b>(2)</b> bu NIDS bağlamında ne anlama "
    "geldiği (hangi hatayı cezalandırıyor), <b>(3)</b> projenin kendi güncel "
    "(19 feature, concurrency_src_1s dahil) sonuçlarıyla somut bağlantı. "
    "Referans modeller: Dense autoencoder (`phase3_dense/04_phase3_models/"
    "full_features`, 5 seed) ve VAE (`phase3_vae/05_contamination_sweep/"
    "04_models/contam_0pct`, 5 seed, deterministik z_mean skorlama)."))

# ============================================================ 0. CONFUSION MATRIX
story.append(h1("0. Temel Kavram: Confusion Matrix (Karışıklık Matrisi)"))
story.append(p(
    "Bu proje, benign trafiği <b>negatif sınıf</b> (0), saldırı trafiğini "
    "<b>pozitif sınıf</b> (1) olarak alıyor. Bir modelin threshold_95 "
    "eşiğindeki her kararı 4 kutudan birine düşer:"))
story.append(make_table(
    ["", "Gerçek: Benign", "Gerçek: Saldırı"],
    [
        ["Model: Benign dedi", "True Negative (TN) — doğru", "False Negative (FN) — kaçırılan saldırı"],
        ["Model: Saldırı dedi", "False Positive (FP) — yanlış alarm", "True Positive (TP) — doğru yakalanan saldırı"],
    ],
    col_widths=[4.0 * cm, 5.6 * cm, 6.4 * cm],
))
story.append(Spacer(1, 6))
story.append(p(
    "Dengesiz bir veri setinde (benign flow sayısı saldırı flow sayısından "
    "kat kat fazla) tek bir 'doğruluk (accuracy)' sayısı yanıltıcıdır — "
    "her şeyi 'benign' diyen bir model bile yüksek accuracy alabilir. Bu "
    "yüzden proje boyunca <b>hangi hatanın</b> (FN mi, FP mi) ölçüldüğünü "
    "açıkça ayıran metrikler kullanılıyor."))

# ============================================================ 1. RECALL
story.append(h1("1. Recall (Attack Recall / Duyarlılık)"))
story.append(p("<b>Tanım:</b> Recall = TP / (TP + FN) — gerçek saldırı flow'larının kaçta kaçının yakalandığı."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> Bir güvenlik ekibi için en kritik "
    "metriklerden biri — <b>kaçırılan saldırı</b> oranını doğrudan gösterir. "
    "Recall düşükse, model o saldırı tipini büyük ölçüde görmezden geliyor "
    "demektir; bu proje boyunca 'zayıf tespit' derken kastedilen budur."))
story.append(p(
    "<b>Projedeki somut örnek:</b> apache_bench'in recall'u, eski 18-feature "
    "modelde sadece %2,6-3,3 iken, concurrency_src_1s eklenince Dense'te "
    "%90,9'a, VAE'de %95,0'e çıktı — bu raporun en önemli tek sayısı budur "
    "(bkz. Proje_Sonuclar_TR.pdf, Bölüm 5)."))

# ============================================================ 2. ROC-AUC
story.append(h1("2. ROC-AUC"))
story.append(p(
    "<b>Tanım:</b> ROC eğrisi, olası her eşik değeri için True Positive "
    "Rate'i (=recall) False Positive Rate'e karşı çizer. AUC (Area Under "
    "Curve), bu eğrinin altındaki alan — 0,5 = rastgele tahmin, 1,0 = "
    "kusursuz ayrım."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> <b>Eşikten bağımsız</b> bir ayrım gücü "
    "ölçüsü — 'model, saldırı flow'larına benign flow'lardan sistematik "
    "olarak daha yüksek bir anomali skoru veriyor mu?' sorusuna cevap "
    "verir, belirli bir threshold_95 seçimine bağlı değildir. Bu yüzden "
    "projede hem ROC-AUC hem de eşiğe bağlı recall/F1/FPR birlikte "
    "raporlanıyor: biri modelin ham ayrım gücünü, diğeri gerçek çalışma "
    "noktasındaki davranışını gösteriyor."))
story.append(p(
    "<b>Projedeki somut örnek:</b> apache_bench ROC-AUC'u eski modelde "
    "0,58-0,70 (rastgele tahminin biraz üzerinde) iken, yeni modelde "
    "0,98'in üzerine çıktı — modelin apache_bench'i benign'den ayırma "
    "gücü artık neredeyse kusursuz."))

# ============================================================ 3. PR-AUC
story.append(h1("3. PR-AUC (Precision-Recall Alan)"))
story.append(p(
    "<b>Tanım:</b> Precision = TP / (TP + FP) — modelin 'saldırı' dediği "
    "flow'ların kaçta kaçının gerçekten saldırı olduğu. PR eğrisi, "
    "precision'ı recall'a karşı çizer; PR-AUC bu eğrinin altındaki alandır "
    "(= Average Precision, AP)."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> ROC-AUC'un aksine, PR-AUC <b>sınıf "
    "dengesizliğine duyarlıdır</b> — saldırı flow'ları benign'e göre çok "
    "azınlıktaysa (bu projede apache_bench değerlendirmesinde saldırı "
    "prevalansı ~%17,9), PR-AUC yanlış alarmların pratikteki maliyetini "
    "ROC-AUC'tan daha iyi yansıtır. Baseline (rastgele model) PR-AUC'u, "
    "prevalansa eşittir — bu yüzden tablolarda 'baseline (prevalence = "
    "...)' çizgisiyle birlikte gösteriliyor."))
story.append(p(
    "<b>Projedeki somut örnek:</b> apache_bench PR-AUC'u Dense'te 0,893, "
    "VAE'de 0,904-0,932 — prevalansın (0,179) çok üzerinde, yani model "
    "'saldırı' dediğinde büyük çoğunlukla haklı."))
story.append(p(
    "<b>Not:</b> Bu projedeki PR-AUC/F1 sayıları, O3 dedup-prevalence "
    "düzeltmesi (Bölüm 6, Proje_Sonuclar_TR.pdf) güncel modele henüz "
    "yeniden uygulanmadığından <i>geçici</i> kabul edilmeli — resampled "
    "pencerelerin bazı flow'ları test setinde iki kez sayması, prevalansı "
    "(ve dolayısıyla PR-AUC/F1'i) hafifçe etkileyebilir. ROC-AUC/recall/"
    "FPR bundan etkilenmez."))

# ============================================================ 4. F1
story.append(h1("4. F1 Score"))
story.append(p(
    "<b>Tanım:</b> F1 = 2 × (Precision × Recall) / (Precision + Recall) — "
    "precision ve recall'un harmonik ortalaması, belirli bir eşikte "
    "(bu projede threshold_95) hesaplanır."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> Tek bir sayıda 'hem kaçırma hem yanlış "
    "alarm' dengesini özetler — ama <b>hangi hatanın daha maliyetli "
    "olduğunu ayırt etmez</b> (bir güvenlik ekibi genelde kaçırmayı yanlış "
    "alarmdan çok daha pahalı bulur, F1 bunu yansıtmaz). Bu yüzden projede "
    "F1 tek başına değil, recall/FPR/ROC-AUC ile birlikte okunuyor."))
story.append(p(
    "<b>Projedeki somut örnek:</b> apache_bench F1'i 0,040-0,051'den "
    "0,82-0,84'e çıktı — recall'daki büyük sıçramanın F1'e yansıması."))

# ============================================================ 5. FPR
story.append(h1("5. Benign FPR (False Positive Rate)"))
story.append(p(
    "<b>Tanım:</b> FPR = FP / (FP + TN) — benign flow'ların kaçta kaçının "
    "yanlışlıkla saldırı diye işaretlendiği."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> Bir güvenlik ekibinin katlanmak zorunda "
    "kalacağı 'yalancı alarm' yükü. threshold_95 tanımı gereği (benign "
    "validasyon setinin %95. persentili), FPR yapısal olarak ~%5 civarında "
    "olması <b>beklenir</b> — gözlenen sapmalar (bu projede %5,9-6,6 "
    "arası), val→test transferindeki küçük sistematik sapmayı ve "
    "concurrency_src_1s'in benign yüksek-frekans trafiğe kısmi etkisini "
    "yansıtıyor."))
story.append(p(
    "<b>Projedeki somut örnek:</b> concurrency_src_1s eklenmeden önce "
    "benign FPR ~%6,15 (Dense) / %5,77 (VAE) idi; sonra ~%6,60 / %6,64'e "
    "çıktı — apache_bench recall'undaki devasa kazanca kıyasla küçük bir "
    "maliyet (+0,4-0,5 puan)."))

# ============================================================ 6. threshold_95
story.append(h1("6. threshold_95"))
story.append(p(
    "<b>Tanım:</b> Held-out (eğitime hiç girmemiş) benign doğrulama "
    "flow'larının reconstruction-error dağılımının <b>95. persentili</b>. "
    "Bir flow'un hatası bu değeri aşarsa 'saldırı' diye işaretlenir."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> 'Benign trafiğin en kötü %5'i kadar "
    "anormal görünen her şeyi alarma çevir' kuralı — tasarım gereği FPR'ı "
    "yaklaşık %5'e sabitler. Bu değer her seed için <b>ayrı ayrı yeniden "
    "hesaplanır</b> (seed'ler arası model varyansını val setine göre telafi "
    "eder) ve VAE için deterministik z_mean skoru üzerinden, Dense için "
    "kendi reconstruction error'u üzerinden hesaplanır — iki model kendi "
    "hata dağılımına göre kalibre edilir, ortak bir sabit sayı değildir."))
story.append(p(
    "<b>Bilinen sınırlama:</b> Küçük bir val setinden (VAE için 653 flow) "
    "tahmin edilen bir kuyruk persentili gürültülü olabilir; ayrıca "
    "val→test transferinde küçük bir sistematik yukarı sapma gözlenmiştir "
    "(gerçekleşen FPR nominal %5'in biraz üzerinde) — detay için final "
    "rapordaki 'Threshold calibration note'a bakınız."))

# ============================================================ 7. KS
story.append(h1("7. KS İstatistiği (Kolmogorov-Smirnov Testi)"))
story.append(p(
    "<b>Tanım:</b> İki dağılımın (örn. bir feature'ın benign'deki değerleri "
    "ile aynı feature'ın apache_bench'teki değerleri) ampirik kümülatif "
    "dağılım fonksiyonları (CDF) arasındaki <b>en büyük dikey mesafe</b>. "
    "0 = dağılımlar özdeş, 1 = tamamen ayrık."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> Retrain yapmadan, ucuza 'bu feature "
    "saldırı tipini ayırt etmede işe yarar mı?' sorusunu ön-test etmek "
    "için kullanıldı — hem eski 18 feature'ın apache_bench için neden "
    "yetersiz kaldığını teşhis etmekte (Bölüm 4.1, Proje_Sonuclar_TR.pdf), "
    "hem de yeni feature adaylarını (IAT, concurrency) retrain'e sokmadan "
    "önce elemekte/onaylamakta kullanıldı."))
story.append(p(
    "<b>Kritik uyarı — projenin kendi bulgusu:</b> Yüksek KS, tek başına "
    "'bu feature işe yarayacak' anlamına gelmez. apache_bench'in en iyi "
    "eski feature'ları KS=0,62-0,76 veriyordu ama işe yaramıyordu — çünkü "
    "apache_bench'in ortalaması benign'in normal aralığının "
    "<b>içindeydi</b> (sadece 0,4-0,7 standart sapma uzakta), yüksek KS "
    "sadece apache_bench'in çok dar/düşük-varyanslı bir küme olmasından "
    "kaynaklanıyordu. Buna karşılık concurrency_src_1s'in KS'i benzer "
    "aralıktaydı (0,86-0,99) ama ortalama kayması çok daha büyüktü "
    "(3-4 standart sapma) — retrain'de işe yarayan da bu oldu. Kısacası: "
    "<b>KS'e ek olarak ortalama-kayma büyüklüğüne (effect size) bakmadan "
    "bir feature hakkında karar vermeyin</b> — bu proje bunun hem başarısız "
    "(IAT) hem başarılı (concurrency) örneğini içeriyor."))

# ============================================================ 8. Reconstruction error
story.append(h1("8. Reconstruction Error (Yeniden İnşa Hatası)"))
story.append(p(
    "<b>Tanım:</b> Bir autoencoder, girdisini sıkıştırıp (bottleneck) "
    "tekrar açar; reconstruction error, girdi ile bu yeniden inşa edilmiş "
    "çıktı arasındaki ortalama kare farkıdır (MSE): "
    "<i>error = mean((x - x̂)²)</i>."))
story.append(p(
    "<b>NIDS bağlamında anlamı:</b> Model sadece benign trafikle "
    "eğitildiğinden, 'normal'in nasıl sıkıştırılıp açılacağını öğrenir. "
    "Benign bir flow verildiğinde düşük hatayla yeniden inşa edilir; "
    "modelin daha önce görmediği bir kalıp (saldırı) verildiğinde ise "
    "yeniden inşa daha kötü olur — <b>anomali skoru budur</b>. threshold_95 "
    "bu skor üzerinde tanımlanır."))
story.append(p(
    "<b>VAE'ye özel not — deterministik z_mean skorlama:</b> VAE'nin "
    "bottleneck'i olasılıksal (z_mean, z_log_var); orijinal skorlama "
    "yöntemi her hesaplamada z'yi rastgele örnekliyordu (reparametrizasyon "
    "trick'i), bu da aynı flow'un skorunun çalıştırmadan çalıştırmaya "
    "değişmesine yol açıyordu (bağımsız denetim bulgusu O2). Bu proje, "
    "z = z_mean kullanarak (örnekleme yapmadan) <b>deterministik</b> bir "
    "skora geçti — concurrency_src_1s ile yapılan VAE retrain'i (VAE v2) "
    "baştan bu yöntemle skorlanmıştır."))

# ============================================================ 9. Pooled vs decomposed
story.append(h1("9. Pooled Recall vs. Decomposed Recall"))
story.append(p(
    "<b>Tanım:</b> İkili (pairwise) değerlendirmede, aynı test setinde iki "
    "farklı saldırı tipi birlikte bulunur. <b>Pooled recall</b>, bu "
    "karışık settteki TÜM saldırı flow'larının (iki tipin toplamı) ortalama "
    "recall'udur. <b>Decomposed recall</b> ise aynı setin içinden sadece "
    "belirli bir tipin (örn. sadece apache_bench) flow'larını ayırıp onun "
    "kendi recall'unu hesaplar."))
story.append(p(
    "<b>NIDS bağlamında anlamı — neden ikisi de gerekli:</b> Pooled recall "
    "yanıltıcı olabilir: iyi tespit edilen bir tip (portscan, recall≈1,0) "
    "karışıma eklendiğinde, pooled recall <b>mekanik olarak</b> yükselir — "
    "apache_bench'in kendi tespitinde hiçbir gerçek iyileşme olmasa bile. "
    "Decomposed recall bu karışım etkisini ayıklar ve 'model gerçekten bu "
    "tipi daha mı iyi tespit ediyor?' sorusuna dürüst cevap verir."))
story.append(p(
    "<b>Projedeki somut örnek:</b> portscan + apache_bench çiftinde pooled "
    "recall %93,8 (Dense) / %96,6 (VAE) görünüyor — ama apache_bench'in "
    "kendi (decomposed) recall'u tam olarak solo değerlendirmedeki gibi "
    "kalıyor (Dense: %90,9; VAE: %95,0), hangi tiple eşleştirildiğinden "
    "bağımsız. Bu, modelin her flow için verdiği kararın statik olduğunu "
    "(eşit eşik, flow-bazlı, komşu flow'lardan etkilenmeyen) somut olarak "
    "doğruluyor."))

# ============================================================ 10. concurrency_src_1s
story.append(h1("10. concurrency_src_1s — Yeni Feature'ın Mantığı"))
story.append(p(
    "<b>Tanım:</b> Bir flow için, o flow'un kendi zaman damgası (ts) "
    "etrafında ±1 saniyelik pencerede, <b>aynı kaynak IP'den</b> gelen "
    "başka kaç flow olduğunun sayısı. Formül olarak: aynı "
    "<i>window_id</i> içinde, aynı <i>id.orig_h</i>'ye sahip flow'lar "
    "zaman damgasına göre sıralanır, her flow için |Δt| ≤ 1s olan "
    "komşularının sayısı (kendisi hariç) sayılır."))
story.append(p(
    "<b>Neden bu şekilde tasarlandı:</b>"))
story.append(bullets([
    "<b>Log1p dönüşümü</b> — ham sayım feature'ı sağa çarpık "
    "(çoğu flow'un yakınında az sayıda komşu var, birkaçının çok fazla); "
    "log1p bu çarpıklığı azaltıp modelin öğrenmesini kolaylaştırıyor.",
    "<b>Scaler sadece benign-train split'ine fit edildi</b> — projenin "
    "her feature'da uyguladığı leakage-free kuralın aynısı; val/test "
    "bilgisi ölçeklemeye hiç karışmadı.",
    "<b>Hiçbir yerde sabit bir IP değeri yok</b> — hesaplama tamamen "
    "veri-güdümlü (o flow'un gerçek kaynak IP'si neyse ona göre "
    "gruplanıyor); bu, modelin belirli bir IP adresini ezberlemesini "
    "değil, genel bir davranış kalıbını (yüksek istek hızı) öğrenmesini "
    "sağlamak için kasıtlı bir tasarım kararı.",
    "<b>Neden ±1 saniye:</b> Denenen 3 yarıçaptan (±1s/±2s/±5s) apache_bench "
    "için en güçlü ve en yorumlanabilir ayrımı ±1s verdi (bkz. "
    "14_concurrency_feature_experiment/), ve knock-out testinde (feature "
    "dondurulup model aynen değerlendirildiğinde) iyileşmenin gerçekten bu "
    "feature'dan geldiği doğrulandı.",
]))
story.append(p(
    "<b>Neden işe yaradı:</b> apache_bench'i benign HTTP trafiğinden ayıran "
    "şey, tek bir isteğin şekli değil — aynı isteğin çok kısa aralıklarla "
    "defalarca tekrarlanması. Eski 18 feature'ın hepsi tek bir flow'u kendi "
    "başına değerlendiriyordu; concurrency_src_1s, ilk kez flow'lar "
    "<b>arasındaki</b> ilişkiyi (yerel istek yoğunluğu) modele veren "
    "feature oldu."))
story.append(p(
    "<b>Genellenebilirlik uyarısı:</b> Bu laboratuvar veri setinde tek bir "
    "saldırgan IP var; feature IP-agnostik tasarlanmış olsa da, veri "
    "setinin kendisi 'yüksek istek hızı = şüpheli' ile 'yüksek istek hızı = "
    "bu spesifik saldırgan' ayrımını yapamaz. Çok-kaynaklı (NAT, load "
    "balancer, meşru yüksek-hızlı istemciler) bir ortamda bu feature'ın "
    "benign false-positive davranışı doğrulanmadan production'a "
    "taşınmamalı (bkz. Proje_Sonuclar_TR.pdf, Bölüm 4.3)."))

story.append(hr())
story.append(h2("Özet Tablo — Hangi Metriğe Ne Zaman Bakmalı"))
story.append(make_table(
    ["Soru", "Bakılacak metrik"],
    [
        ["Model genel olarak bu saldırı tipini ayırt edebiliyor mu (eşikten bağımsız)?", "ROC-AUC"],
        ["Dengesiz sette (az saldırı, çok benign) ayrım gücü ne kadar?", "PR-AUC"],
        ["Gerçek çalışma noktasında (threshold_95) kaç saldırı kaçırılıyor?", "Recall"],
        ["Gerçek çalışma noktasında kaç yanlış alarm var?", "Benign FPR"],
        ["Recall ve precision'ı tek sayıda özetle (eşitlik varsayımıyla)", "F1"],
        ["Bu feature retrain'e değer mi (ucuz ön-test)?", "KS + ortalama-kayma büyüklüğü"],
        ["Bir çiftteki iyileşme gerçek mi, karışım etkisi mi?", "Decomposed vs. pooled recall"],
    ],
    col_widths=[10.5 * cm, 5.5 * cm],
))

doc = SimpleDocTemplate(OUT_PATH, pagesize=PAGE_SIZE, **MARGINS,
                        title="Değerlendirme Metrikleri — Kapsamlı Açıklama", author="IDS-Project")
doc.build(story)
print(f"Wrote {OUT_PATH}")
