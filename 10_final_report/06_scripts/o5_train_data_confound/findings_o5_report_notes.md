# O5 train-data confound — bulgular ve rapor notu taslakları

Denetim bulgusu O5 (`11_fable_review/independent_audit.md`): VAE-vs-Dense
karşılaştırması aynı test flow'ları üzerinde yapılıyor ama iki model çok
farklı eğitim verisiyle eğitilmiş — mimari farkı ile veri farkı karışıyor
(confound). Rapor tabloları fiilen "mimari karşılaştırması" gibi okunuyor;
`phase3_vae/README.md`'deki "bu bir mimari karşılaştırma değil" uyarısı
karşılaştırma çıktılarının hiçbirine taşınmamış.

## Doğrulama sonucu (split dosyaları + script'lerden, retrain yok, 2026-07-29)

| | VAE (clean-only, kanonik) | Dense v1 (full_features) |
|---|---|---|
| Train window'ları | yalnızca `window_10_0pct` | `window_01`–`window_08` |
| Train benign n | 3.049 (4.356 havuzun %70'i) | 23.274 (~7,6 kat) |
| Threshold val seti | window_10 val, n=653 | window_01-08 val benign, n=4.609 |
| Seed sayısı | 20 | 5 |
| Split yöntemi | 70/15/15 rastgele | GroupShuffleSplit (signature_id) |

- **Scaler confound DEĞİL:** StandardScaler + OneHotEncoder **yalnızca
  Dense'in train split'inde** fit edilip her iki tarafa da uygulanıyor
  (`prepare_window10.py`, `prepare_contamination_data.py`) — iki taraf aynı
  ölçekte. Audit'in "ölçekleyiciyle confound'lu" ifadesinin doğru kısmı
  **kategori kapsamı**: window_10'daki `proto=icmp` ve `conn_state ∈ {OTH,
  S0}` değerlerini Dense'in encoder'ı hiç görmemiş → VAE'nin eğitim
  verisinde bu flow'lar all-zero kodlu (kategorik sinyal kayıp).
- **Değerlendirme tarafı özdeş** (aynı test flow'ları, aynı 18 kolon, aynı
  threshold konvansiyonu) — confound eval'de değil, modellerin ne
  öğrendiğinde.
- **Etkilenen ifadeler:** macro parite tabloları (VAE 0.6739/0.5505 vs
  Dense 0.6731/0.5401 → "hiçbiri daha dengeli değil"), "Dense'in ham ayrım
  gücü biraz daha iyi" nüansı (apache_bench ROC-AUC 0.696 vs 0.581),
  "répétées à l'identique" tarzı yalnızca-model-değişti izlenimi veren
  protokol cümleleri. Ana bulgu (apache_bench → feature-set sınırlaması)
  zayıflamıyor; tersine, farklı mimari + farklı veriyle aynı başarısızlık
  deseni ortak paydayı (18 kolonluk feature uzayı) daha da işaret ediyor.

---

## Taslak 1 — Fransızca final rapora
(`10_final_report/07_final_written_report/rapport_final_attack_type_analysis.md`,
§5 "Comparaison macro-moyenne" bölümünün sonuna)

> #### Note de lecture — les deux modèles n'ont pas été entraînés sur les mêmes données
>
> Cette comparaison est menée sur **les mêmes flows de test, les mêmes 18
> colonnes et la même convention de seuil** pour les deux modèles — côté
> évaluation, elle est bien à armes égales. Côté **entraînement**, en
> revanche, les deux modèles diffèrent bien au-delà de l'architecture : le
> VAE est entraîné sur le seul benign de window_10 (**3 049 flows** de
> train, 20 seeds, split aléatoire 70/15/15), le Dense v1 sur les windows
> 01–08 (**23 274 flows** de train, soit ~7.6× plus, 5 seeds,
> GroupShuffleSplit par signature) ; et window_10 contient des valeurs
> catégorielles (proto = icmp, conn_state OTH/S0) que l'encodeur one-hot —
> ajusté uniquement sur le train du Dense — n'a jamais vues, donc encodées
> en tout-zéro dans les données d'entraînement du VAE. Le scaler lui-même
> n'est pas un facteur de confusion (il est ajusté une seule fois, sur le
> train du Dense, et appliqué aux deux côtés — même échelle partout), mais
> la composition, le volume et la couverture catégorielle des données
> d'entraînement, si.
>
> Conséquence : les comparaisons fines de cette section — la quasi-égalité
> macro (0.674/0.551 vs 0.673/0.540) comme la nuance « meilleur pouvoir de
> discrimination du Dense sur apache_bench » (ROC-AUC 0.696 vs 0.581) — ne
> peuvent pas être attribuées à l'architecture seule : la différence de
> données d'entraînement y contribue de façon indissociable. Les
> formulations du type « répétées à l'identique » (section 5, protocole)
> concernent le protocole d'évaluation, pas les conditions d'entraînement,
> et doivent être lues avec cette note.
>
> La conclusion principale, elle, **n'est pas fragilisée — elle est
> renforcée** : deux architectures différentes, entraînées sur des données
> très différentes (composition de fenêtres, volume ~7.6×, couverture
> catégorielle), échouent sur apache_bench selon le même motif
> (recall ≤ 3.3 %). Le dénominateur commun n'est ni le modèle ni le jeu
> d'entraînement, mais l'espace de features à 18 colonnes — ce qui appuie
> d'autant la lecture « limite du jeu de features » de la section 7.

## Taslak 2 — Türkçe dokümantasyona
(`10_final_report/08_documentation/DOCUMENTATION.md`, §7.3'ün ardına
"### 7.4" olarak)

> ### 7.4 Sınırlama notu — VAE ve Dense v1 aynı eğitim verisiyle eğitilmedi (denetim bulgusu O5)
>
> Bölüm 5'teki karşılaştırma, **aynı test flow'ları, aynı 18 kolon ve aynı
> threshold konvansiyonuyla** yapılıyor — değerlendirme tarafı elma-elma.
> Ancak **eğitim tarafında** iki model mimariden çok daha fazlasıyla
> ayrışıyor: VAE yalnızca window_10'un benign'iyle eğitildi (**3.049**
> train flow'u, 20 seed, rastgele 70/15/15 split), Dense v1 ise window_01-08
> ile (**23.274** train flow'u — ~7,6 kat fazla, 5 seed, signature bazlı
> GroupShuffleSplit). Ayrıca window_10'da Dense'in one-hot encoder'ının
> (yalnızca Dense'in train'inde fit edilmiştir) hiç görmediği kategorik
> değerler var (`proto=icmp`, `conn_state ∈ {OTH, S0}`) — bu flow'lar
> VAE'nin eğitim verisinde all-zero kodlanmıştır, kategorik sinyalleri
> kayıptır. Scaler'ın kendisi bir confound değildir (tek sefer, Dense'in
> train'inde fit edilip iki tarafa da uygulanır — ortak ölçek); confound
> eğitim verisinin kompozisyonu, hacmi ve kategori kapsamıdır.
>
> Sonuç olarak bölüm 5'teki ince taneli karşılaştırmalar — macro
> neredeyse-eşitlik (0.674/0.551 vs 0.673/0.540) ve "Dense'in apache_bench
> üzerinde ham ayrım gücü biraz daha iyi" nüansı (ROC-AUC 0.696 vs 0.581) —
> tek başına mimariye atfedilemez: eğitim verisi farkı bu sayılara
> ayrıştırılamaz biçimde karışır. "3 analiz aynı şekilde tekrarlandı"
> tarzı ifadeler değerlendirme protokolünü anlatır, eğitim koşullarını
> değil — bu notla birlikte okunmalıdır.
>
> Ana bulgu ise bu confound'dan **zayıflamaz, güçlenir**: iki farklı
> mimari, çok farklı eğitim verileriyle (window kompozisyonu, ~7,6 kat
> hacim, kategori kapsamı) apache_bench üzerinde aynı deseni veriyor
> (recall ≤ %3,3). Ortak payda ne model ne eğitim seti — 18 kolonluk
> feature uzayı; bu da bölüm 7.1'deki "feature-set sınırlaması" çıkarımını
> daha da destekler.
