# O7 IP-bazlı ground truth — kapsam doğrulaması ve rapor notu taslakları

Denetim bulgusu O7 (`11_fable_review/independent_audit.md`): ground truth
etiketi davranışa değil kaynak IP'ye dayanıyor.

## Kapsam doğrulaması (kod üzerinden, 2026-07-29)

- **Etiket tanımı tamamen IP-bazlı:** `faz2_feature_extraction.py:79-80,134-136` —
  önce lab filtresi (`id.orig_h ∈ LAB_IPS ∧ id.resp_h ∈ LAB_IPS`, 3 IP'lik
  kapalı lab: .1 kurban/sunucu, .2 saldırgan, .3 benign istemci), sonra
  `is_attack = (id.orig_h == "192.168.10.2")`. `prepare_window10.py` (VAE
  tarafı) aynı kuralı kullanıyor. Davranışsal/imza bazlı hiçbir sinyal
  `is_attack`'i belirlemiyor.
- **attack_log yalnızca saldırı TİPİ için kullanılıyor** (post-hoc ts
  eşleştirme, `derive_attack_type_labels.py`): is_attack'i değiştirmiyor.
  Yumuşatıcı bulgu: attack etiketli flow'ların **%100'ü** 1 sn toleransla
  bir saldırı komut aralığına düşüyor — etiket bu lab kurulumunda pratikte
  temiz (saldırgan makinede etiketli ama komutsuz "OS arka plan" flow'u
  fiilen kalmamış).
- **IP model girdisi değil:** 18 feature kolonunda IP yok — model IP'yi
  ezberleyemez; öğrendiği şey "saldırgan makineden çıkan trafiğin
  istatistiksel imzası"dır. Sınırlama etikette (neyin saldırı sayıldığında),
  feature'larda değil.
- **Raporlarda mevcut durum:** ne Fransızca rapor ne DOCUMENTATION.md
  `is_attack`'in nasıl tanımlandığını söylüyor (grep: `192.168`, "IP",
  "orig_h" → 0 sonuç; attack_log yalnızca attack_type bağlamında geçiyor)
  — net bir eksiklik, tehdit modeli notu gerekiyor.

---

## Taslak 1 — Fransızca final rapora
(`10_final_report/07_final_written_report/rapport_final_attack_type_analysis.md`,
bölüm 7'de O4 notunun ("Note de prudence — calibration du seuil...") hemen
ardına, "Pistes pour la suite"ten önce)

> ### Note sur le modèle de menace — une vérité terrain définie par l'IP source, pas par le comportement
>
> Dans tout le projet, le label `is_attack` est défini par **l'identité de
> la machine source**, pas par le comportement du flow :
> `is_attack = (id.orig_h == 192.168.10.2)`, appliqué après un filtre
> lab-only (origine **et** destination dans les 3 IP du lab). Aucun signal
> comportemental ou de signature n'entre dans ce label ; les logs
> d'orchestration (`attack_log.csv`) ne servent qu'à typer les attaques a
> posteriori — et le fait que 100 % des flows étiquetés attack tombent
> dans un intervalle de commande d'attaque (tolérance 1 s) montre que ce
> label est propre *dans ce laboratoire*. L'IP n'est pas une feature du
> modèle (les 18 colonnes n'en contiennent pas) : la limite est dans la
> **définition** de ce qui compte comme attaque, pas dans les entrées.
>
> Conséquence : ce que les modèles apprennent à séparer est, au sens
> strict, « la signature statistique du trafic émis par la machine
> attaquante » — pas une notion sémantique d'intention malveillante. Les
> scénarios où cette équivalence se brise ne sont pas couverts par
> l'évaluation : attaquant changeant d'adresse ou usurpant une IP
> (spoofing), trafic mixte légitime + malveillant derrière une même
> source (NAT, machine compromise émettant aussi du trafic normal),
> mouvement latéral depuis une machine « de confiance ». La
> généralisation à ces cas n'est ni testée ni garantie.
>
> Cette note ne remet pas en cause les résultats du projet — le sweep de
> contamination, les analyses par type d'attaque et les diagnostics
> apache_bench restent valides **sous cette définition de la vérité
> terrain**. Elle borne en revanche la portée des lectures « déploiement
> réel » : dans un environnement où l'attaquant n'est pas une source
> unique et dédiée, la correspondance label ↔ comportement devrait être
> réétablie (étiquetage par signature/comportement) avant de transposer
> les chiffres rapportés ici.

## Taslak 2 — Türkçe dokümantasyona
(`10_final_report/08_documentation/DOCUMENTATION.md`, §7.4'ün ardına
"### 7.5" olarak)

> ### 7.5 Tehdit modeli notu — ground truth davranışa değil kaynak IP'ye dayanır (denetim bulgusu O7)
>
> Proje genelinde `is_attack` etiketi flow'un **davranışıyla değil, kaynak
> makinenin kimliğiyle** tanımlıdır: lab-only filtresinin (kaynak **ve**
> hedef, 3 IP'lik lab kümesinde) ardından
> `is_attack = (id.orig_h == 192.168.10.2)`. Etikete hiçbir davranışsal
> veya imza bazlı sinyal girmez; orkestrasyon logları (`attack_log.csv`)
> yalnızca saldırı **tipini** sonradan atamak için kullanılır — attack
> etiketli flow'ların %100'ünün 1 sn toleransla bir saldırı komut
> aralığına düşmesi, etiketin *bu lab kurulumunda* pratikte temiz
> olduğunu gösterir. IP bir model girdisi değildir (18 feature kolonunda
> IP yoktur): sınırlama feature'larda değil, "neyin saldırı sayıldığı"
> tanımındadır.
>
> Bunun sonucu: modellerin ayırmayı öğrendiği şey, katı anlamda
> "saldırgan makineden çıkan trafiğin istatistiksel imzası"dır —
> semantik bir "kötücül davranış" kavramı değil. Bu eşdeğerliğin bozulduğu
> senaryolar değerlendirmenin kapsamı dışındadır: saldırganın IP
> değiştirmesi veya IP sahteciliği (spoofing), aynı kaynağın arkasında
> meşru + kötücül karışık trafik (NAT, ele geçirilmiş ama normal trafik
> de üreten bir makine), "güvenilir" bir makineden yanal hareket. Bu
> durumlara genelleme test edilmemiştir ve garanti edilemez.
>
> Bu not projenin diğer bulgularını geçersiz kılmaz — contamination
> sweep, attack-type analizleri ve apache_bench tanıları **bu ground
> truth tanımı altında** geçerlidir. Ancak "gerçek dünya deployment"
> okumalarının kapsamını sınırlar: saldırganın tek ve adanmış bir kaynak
> olmadığı bir ortamda, buradaki sayıları taşımadan önce etiket ↔
> davranış eşleşmesinin (imza/davranış bazlı etiketlemeyle) yeniden
> kurulması gerekir.
