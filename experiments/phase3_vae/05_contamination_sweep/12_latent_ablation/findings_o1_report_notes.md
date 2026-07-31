# O1 latent ablation — bulgular ve rapor notu taslakları

Denetim bulgusu O1 (`11_fable_review/independent_audit.md`): kanonik VAE'de
`latent_dim=10`, kendisini besleyen 8-birimlik bottleneck'ten geniş
(`18 → Dense(16) → Dense(8) → z_mean/z_log_var(10)`). z_mean 8-boyutlu
aktivasyonun lineer dönüşümü olduğundan latent kod en fazla 8 serbestlik
derecesi taşıyabilir — "latent=10" nominal, fiili değil.

## Ablation sonucu (bu klasördeki koşu, 2026-07-29)

`latent_dim=8` (bottleneck ile eşit) varyantı, diğer her şey birebir aynı
olacak şekilde eğitildi: aynı VAE sınıfı, β=0.25, dropout=0.1, aynı clean-only
train/val/test split, aynı 20 seed (0-19), deterministik z_mean skorlama +
seed başına val-benign threshold_95 (post-O2 kanonik konvansiyon). Seed-eşleşmeli
fark + bootstrap %95 CI (10.000 yeniden örnekleme). Tam tablolar:
`comparison_latent8_vs_latent10.{csv,md}`, per-seed CSV'ler ve
`active_dims_per_seed.csv` bu klasörde.

**Özet: iki varyant pratikte ayırt edilemez.**

- Recall@thr95 üç saldırı tipinde de **birebir aynı**: apache_bench 0.0262,
  portscan 0.9983, slowloris 1.0000 (paired fark tam 0).
- apache_bench ROC-AUC: 0.702 (latent=8) vs 0.667 (latent=10) — paired fark
  +0.035, %95 CI [−0.014, +0.086], sıfırı içeriyor → seed varyansı içinde
  (audit'in "latent sweep'teki +0.08 AUC farkı muhtemelen seed varyansı"
  öngörüsüyle tutarlı).
- benign FPR: 0.0603 vs 0.0577, CI sıfırı içeriyor.
- İstatistiksel olarak sıfırdan farklı çıkan tek şey portscan ROC-AUC/PR-AUC
  (+0.0002 / +0.0014) — pratik önemi olmayan büyüklükte.
- Aktif latent boyut (std(z_mean) > 0.15, train seti,
  `09_collapse_investigation` konvansiyonu): latent=10'da ortalama 5.9/10
  (seed'e göre 1-10 arası!), latent=8'de 4.4/8 (2-8 arası). Her iki varyant da
  nominal genişliğin tamamını kullanmıyor ve kullanılan boyut sayısı seed'e
  göre çok oynak.

**Sonuç:** fazla geniş latent boyutu ölçülebilir bir etkisi olmayan bir
mimari özensizlik; kanonik latent=10 sonuçları olduğu gibi geçerli. Rapor
buna sınırlama notu olarak yer vermeli (aşağıdaki taslaklar), sayıların
değişmesi gerekmiyor.

---

## Taslak 1 — Fransızca final rapora
(`10_final_report/07_final_written_report/rapport_final_attack_type_analysis.md`,
bölüm 7 civarına, mevcut "### Note de prudence" alt-bölüm üslubuyla)

> ### Note d'architecture — dimension latente nominale vs. effective
>
> L'encodeur du VAE (`18 → Dense(16) → Dense(8) → z_mean/z_log_var(10)`)
> donne au code latent une dimension (10) **supérieure à la couche qui
> l'alimente** (8). `z_mean` étant une transformation linéaire d'une
> activation à 8 dimensions, le code latent ne peut porter au plus que 8
> degrés de liberté : « latent = 10 » est une capacité nominale, pas
> effective. Pour vérifier que ce choix inhabituel n'affecte pas les
> conclusions, une ablation dédiée
> (`phase3_vae/05_contamination_sweep/12_latent_ablation/`) a réentraîné les
> 20 mêmes seeds avec latent = 8 (= la largeur du bottleneck), tout le reste
> inchangé (β = 0.25, mêmes splits, scoring z_mean déterministe,
> threshold_95 recalibré par seed). Résultat : les deux variantes sont
> **indiscernables** sur les métriques de détection — recall par type
> strictement identique (apache_bench 2.6 %, portscan 99.8 %, slowloris
> 100 %) ; ROC-AUC apache_bench 0.702 vs 0.667, soit une différence appariée
> de +0.035 dont l'IC bootstrap à 95 % [−0.014 ; +0.086] inclut zéro
> (variance de seed). Le nombre de dimensions latentes réellement actives
> (std(z_mean) > 0.15) reste inférieur à la largeur nominale dans les deux
> cas (en moyenne 4.4/8 et 5.9/10, très variable selon le seed). La
> dimension latente surdimensionnée est donc une **maladresse
> architecturale sans effet mesurable** sur les résultats rapportés ; elle
> est notée ici comme limite de conception, sans invalider les chiffres du
> modèle canonique (latent = 10).

## Taslak 2 — Türkçe dokümantasyona
(`10_final_report/08_documentation/DOCUMENTATION.md`, §0.2 "Kullanılan
modeller"in VAE paragrafının hemen ardına veya §7'ye sınırlama notu olarak)

> ### Mimari not — nominal vs. etkin latent boyutu (denetim bulgusu O1)
>
> VAE encoder'ında latent boyutu (10), kendisini besleyen ara katmandan (8)
> **daha geniştir**. `z_mean` 8-boyutlu bir aktivasyonun lineer dönüşümü
> olduğundan latent kod en fazla 8 serbestlik derecesi taşıyabilir —
> "latent=10" nominal bir kapasitedir, fiilen mevcut değildir. Bu alışılmadık
> seçimin sonuçları etkileyip etkilemediği ayrı bir ablation koşusuyla test
> edildi (`phase3_vae/05_contamination_sweep/12_latent_ablation/`): aynı 20
> seed, aynı hiperparametreler ve split'lerle `latent_dim=8` (bottleneck ile
> eşit) varyantı eğitildi ve deterministik z_mean skorlamayla karşılaştırıldı.
> İki varyant pratikte ayırt edilemez çıktı: tip başına recall birebir aynı
> (apache_bench %2.6, portscan %99.8, slowloris %100); apache_bench
> ROC-AUC farkı (+0.035) bootstrap %95 güven aralığı sıfırı içerdiğinden
> seed varyansından ayrıştırılamıyor. Fiilen kullanılan (aktif) latent boyut
> sayısı her iki varyantta da nominal genişliğin altında kalıyor (ortalama
> 4.4/8 ve 5.9/10). Dolayısıyla bu, sonuçları etkilemeyen ama tasarım
> gerekçesi açısından not edilmesi gereken bir **mimari sınırlamadır**;
> raporlardaki latent=10 sayıları geçerliliğini korur.
