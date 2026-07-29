# O4 threshold analizi — bulgular ve rapor notu taslakları

Denetim bulgusu O4 (`11_fable_review/independent_audit.md`): `threshold_95`
küçük bir val-benign seti üzerinden kalibre ediliyor (window_10 val split,
n=653; 95. persentil ≈ sıralamada ~33. en büyük değer) ve başka window'ların
benign'ine uygulanıyor — dağılım-transferi varsayımı + küçük-n persentil
gürültüsü.

## Sayısal doğrulama sonucu (bu klasördeki koşu, 2026-07-29)

20 kanonik clean-only VAE seed'i, deterministik z_mean skorlama (post-O2
konvansiyon), retrain yok. Tam tablolar: `threshold_transfer_per_seed.csv`,
özet: `threshold_transfer_summary.md`.

- **Kalibrasyon n'i:** tüm seed'lerde aynı 653 flow'luk val-benign seti.
- **Seed-arası oynaklık:** threshold_95 ortalama 0.0903, std 0.0252,
  **CV %27.9**, aralık [0.043, 0.153] (3.6 kat). Tek seed içindeki bootstrap
  %95 CI'ın ortalama genişliği threshold'un **%59.7'si** — yani seed-arası
  görünen oynaklığın önemli kısmı model farkı değil, n=653'ten ağır
  sağ-kuyruklu bir dağılımın 95. persentilini tahmin etmenin doğal gürültüsü.
- **Val→test transferi:** val threshold'unun test-benign'de gerçekleştirdiği
  FPR **%5.77 ± 0.58** (nominal %5.00; aralık %4.78–%6.93; 20 seed'in
  18'inde > %5 — sistematik, rastgele değil). Test-benign'de tam %5 verecek
  threshold, val threshold'unun ortalama 1.082 katı. KS(val, test-benign
  error) ortalama **0.067** (aralık 0.047–0.123), 5/20 seed'de p<0.01 —
  saptanabilir ama küçük bir kayma.
- **Kapsam:** AUC/PR-AUC threshold'dan bağımsız, etkilenmiyor; etkilenen
  yalnızca thr95'e bağlı recall/F1/FPR çalışma noktası.

---

## Taslak 1 — Fransızca final rapora
(`10_final_report/07_final_written_report/rapport_final_attack_type_analysis.md`,
bölüm 7'de O1 notunun ("Note d'architecture") hemen ardına)

> ### Note de prudence — calibration du seuil sur un petit ensemble de validation
>
> Le `threshold_95` de chaque seed est le 95ᵉ percentile de l'erreur de
> reconstruction sur un ensemble val-benign de **653 flows seulement**
> (split de validation de window_10) — soit un ordre statistique estimé à
> partir de la ~33ᵉ plus grande valeur. Deux conséquences quantifiées
> (`10_final_report/06_scripts/o4_threshold_transfer/`, 20 seeds, scoring
> z_mean déterministe, aucun réentraînement) :
>
> **(1) Le seuil est intrinsèquement bruité.** Entre seeds, threshold_95
> varie de 0.043 à 0.153 (moyenne 0.090, **CV 27.9 %**) ; et au sein d'un
> même seed, l'intervalle de confiance bootstrap à 95 % du percentile a une
> largeur moyenne de ~60 % du seuil. Une part importante de la variabilité
> apparente du seuil entre seeds n'est donc pas une différence de modèle,
> mais le bruit d'estimation d'un percentile de queue sur n = 653.
>
> **(2) Le transfert val → test tient à peu près, avec un biais
> systématique.** Appliqué aux flows benign du test (fenêtres différentes de
> celle de calibration), le seuil val donne un FPR réalisé de **5.77 % ±
> 0.58 %** contre 5.00 % nominal (18 seeds sur 20 au-dessus de 5 % — un
> écart orienté, pas du bruit) ; le seuil qui donnerait exactement 5 % sur
> le test benign serait en moyenne 8 % plus haut. Le test KS entre les deux
> distributions d'erreur benign (val vs test) est en moyenne de 0.067 —
> un décalage détectable mais de faible ampleur. Sur ces données le
> transfert est donc raisonnable, mais **rien ne garantit que l'écart reste
> aussi faible dans un environnement de déploiement différent** : le seuil
> devrait y être recalibré sur du benign local.
>
> Portée : les métriques indépendantes du seuil (ROC-AUC, PR-AUC) ne sont
> pas concernées ; seul le point de fonctionnement dépendant de
> threshold_95 (recall, F1, FPR) l'est.

## Taslak 2 — Türkçe dokümantasyona
(`10_final_report/08_documentation/DOCUMENTATION.md`, §7 "Sonuç ve
Öneriler" içine sınırlama notu olarak — 7.2'nin ardına, dokümanın numaralı
alt-bölüm düzeniyle "### 7.3" olarak)

> ### 7.3 Sınırlama notu — threshold_95'in küçük val setinden kalibrasyonu (denetim bulgusu O4)
>
> Her seed'in `threshold_95`'i, yalnızca **653 flow'luk** bir val-benign
> seti (window_10 validation split'i) üzerindeki reconstruction error'ın
> 95. persentilidir — yani sıralamada ~33. en büyük değere dayanan bir sıra
> istatistiği. Bunun iki ölçülmüş sonucu var
> (`10_final_report/06_scripts/o4_threshold_transfer/`, 20 seed,
> deterministik z_mean skor, retrain yok):
>
> **(1) Threshold doğası gereği gürültülü.** Seed'ler arasında threshold_95
> 0.043 ile 0.153 arasında değişiyor (ortalama 0.090, **CV %27.9**); tek
> seed içinde bile persentil tahmininin bootstrap %95 güven aralığının
> ortalama genişliği threshold'un ~%60'ı. Yani seed'ler arası görünen
> threshold oynaklığının önemli bir kısmı model farkı değil, n=653'ten
> ağır sağ-kuyruklu bir dağılımın kuyruk persentilini tahmin etmenin doğal
> gürültüsüdür.
>
> **(2) Val→test transferi kabaca tutuyor, ama sistematik bir sapmayla.**
> Val'den kalibre edilen threshold, test setinin benign flow'larında
> (kalibrasyon window'undan farklı window'lar) nominal %5.00 yerine
> ortalama **%5.77 ± 0.58** FPR gerçekleştiriyor (20 seed'in 18'inde >%5 —
> yönlü bir sapma, gürültü değil); test-benign'de tam %5 verecek threshold
> ortalama %8 daha yüksek olurdu. İki benign error dağılımı arasındaki KS
> istatistiği ortalama 0.067 — saptanabilir ama küçük bir kayma. Bu veri
> setinde transfer makul çalışıyor; ancak **farklı bir deployment
> ortamında sapmanın bu kadar küçük kalacağının garantisi yoktur** —
> orada threshold yerel benign trafikten yeniden kalibre edilmelidir.
>
> Kapsam: threshold'dan bağımsız metrikler (ROC-AUC, PR-AUC) bu bulgudan
> etkilenmez; etkilenen yalnızca threshold_95'e bağlı çalışma noktası
> metrikleridir (recall, F1, benign FPR).
