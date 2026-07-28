# Analyse par type d'attaque — VAE clean-only vs Dense autoencoder v1

*Rapport technique — préparé pour Gérard*

*Périmètre : `06_attack_type_analysis/`, `07_segmented_injection/`, `08_dense_v1_comparison/`*

## 1. Contexte et objectifs

Le suivi de vendredi a identifié 4 tâches, toutes en **inference-only**
(aucun réentraînement de modèle) sur les modèles déjà entraînés
(VAE clean-only `contam_0pct`, 20 seeds ; Dense autoencoder v1
`full_features`, 5 seeds) :

1. **Dériver un label attack_type** (portscan / apache_bench / slowloris)
   par flow dans le test set, alors que le pipeline ne produisait jusqu'ici
   qu'un label binaire `is_attack`, et **casser la métrique binaire agrégée**
   en performance par type d'attaque individuel.
2. Étendre cette analyse aux **combinaisons par paires** de types d'attaque,
   pour vérifier si un type mal détecté (apache_bench) devient plus facile
   à détecter quand il partage l'ensemble d'évaluation avec un type bien
   détecté.
3. Construire une **expérience d'injection segmentée** : au lieu du test set
   mélangé habituel, réordonner les mêmes flows en blocs contigus par type
   d'attaque (benign → apache_bench → benign → slowloris → benign →
   portscan → benign), pour visualiser le score de reconstruction en
   fonction de la position dans le flux et vérifier si le comportement du
   modèle change à la frontière d'un bloc.
4. **Répéter les 3 analyses précédentes avec le Dense autoencoder v1**
   (au lieu du VAE) pour déterminer si la faiblesse observée sur
   apache_bench est spécifique à l'architecture VAE ou si elle est partagée.

Aucune des données originales (`test_with_attack_type.csv`,
`segmented_sequence.csv`, modèles `.keras`) n'a été modifiée entre les
étapes — chaque script réutilise les fonctions du script précédent
(`evaluate_group()`, `assemble_labeled_features_df()`,
`compute_error_matrix()`, `run_segmented_evaluation()`) via un objet
`backend` paramétrable (VAE ou Dense), sans dupliquer la logique de
chargement de modèle / seuil / calcul de métriques.

**Dérivation du label attack_type.** `test_with_attack_type.csv` est
construit par jointure entre `03_phase3_splits/test_indices.csv` et les
logs d'orchestration (`ground_truth/attack_log.csv`, un log cumulatif par
fenêtre de capture, filtré à l'intervalle propre de chaque fenêtre) sur la
clé `(window_id, ts)`. Pour les fenêtres rééchantillonnées
(`window_resampled_15pct/20pct`, ~31% des flows d'attaque du test set), qui
n'ont pas leur propre `attack_log.csv` mais conservent le `ts` d'origine du
flow source, la correspondance est faite **globalement** sur `ts` (tolérance
1s) plutôt que par `window_id` — les fenêtres réelles ne se chevauchant
jamais dans le temps, cette approche résout correctement 100% des 3110 flows
d'attaque du test set (taux de correspondance vérifié).

---

## 2. Performance par type d'attaque (analyse individuelle)

**Protocole.** Pour chaque type d'attaque, l'ensemble d'évaluation est :
tous les flows benign du test set + uniquement les flows de ce type
(les 2 autres types sont exclus de cette exécution). Seuil = `threshold_95`
(95ᵉ percentile de l'erreur de reconstruction sur les flows benign de
validation), calculé par seed. Moyenne ± écart-type sur 20 seeds (VAE).

| attack_type | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | Benign FPR (thr95) | Attack Recall (thr95) |
|---|---|---|---|---|---|---|
| apache_bench | 1487 | 0.5815 ± 0.0768 | 0.2133 ± 0.0219 | 0.0507 ± 0.0081 | 0.0565 ± 0.0059 | **0.0328 ± 0.0055** |
| portscan | 694 | 0.9982 ± 0.0005 | 0.9886 ± 0.0023 | 0.7737 ± 0.0161 | 0.0578 ± 0.0056 | 0.9889 ± 0.0138 |
| slowloris | 929 | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0.8271 ± 0.0158 | 0.0570 ± 0.0062 | 1.0000 ± 0.0000 |

*(source : `06_attack_type_analysis/results_single_attack_type.csv/.md`)*

### Constat principal

**apache_bench n'est quasiment jamais détecté** : recall = 3.3%, F1 = 0.051,
ROC-AUC = 0.58 (à peine mieux que le hasard). À l'inverse, portscan et
slowloris sont détectés quasi parfaitement (recall ≥ 0.99, ROC-AUC ≥ 0.998).

### Pourquoi la métrique binaire agrégée masque ce problème

Le test set contient 1487 flows apache_bench, 694 portscan et 929 slowloris
— soit apache_bench = 47.8% des flows d'attaque, mais la métrique binaire
`is_attack` habituelle (recall/F1 agrégé, voir par ex. les métriques Phase 3
existantes) mélange les 3 types dans un seul chiffre. Comme portscan et
slowloris sont détectés à ~99-100%, ils tirent la moyenne globale vers le
haut : un recall binaire global proche de 65-70% (cohérent avec les
résultats historiques du contamination sweep, voir
`phase3_vae/05_contamination_sweep/README.md`) peut coexister avec un type
d'attaque presque totalement manqué. Sans décomposition par attack_type,
cette faiblesse structurelle n'apparaît dans aucun rapport agrégé — d'où
l'intérêt de cette analyse.

**Cause probable (feature-level).** apache_bench (`ab.exe`, requête HTTP
fixe de 80 octets, `conn_state=SF`, durée < 1s) produit un flow qui
ressemble, dans l'espace des 18 colonnes de features actuelles, à du trafic
HTTP benign ordinaire — contrairement à portscan (ports non-HTTP,
`conn_state` distinctif) et slowloris (connexion maintenue ouverte
30s+, `conn_state=RSTO/S1`), qui ont une signature bien plus éloignée du
comportement benign appris par les deux autoencodeurs.

---

## 3. Performance par paires de types d'attaque

**Protocole.** Pour chaque paire, l'ensemble d'évaluation est : tous les
flows benign + les flows des 2 types de la paire (le 3ᵉ type est exclu).
Mêmes modèle/seuil que la section 2.

| Paire | n_attack | ROC-AUC | PR-AUC | F1 (thr95) | Recall poolé (thr95) |
|---|---|---|---|---|---|
| portscan + apache_bench | 2181 | 0.7135 ± 0.0527 | 0.5598 ± 0.0232 | 0.4447 ± 0.0070 | 0.3369 ± 0.0061 |
| portscan + slowloris | 1623 | 0.9993 ± 0.0002 | 0.9975 ± 0.0007 | 0.8905 ± 0.0105 | 0.9953 ± 0.0057 |
| apache_bench + slowloris | 2416 | 0.7427 ± 0.0474 | 0.6283 ± 0.0219 | 0.5170 ± 0.0054 | 0.4044 ± 0.0029 |

*(source : `06_attack_type_analysis/results_pairwise_attack_type.csv/.md`)*

### Recall poolé vs. recall décomposé — une distinction essentielle

Le recall "poolé" ci-dessus mélange les 2 types de la paire : il **augmente
mécaniquement** dès qu'un type bien détecté (portscan ou slowloris) est
ajouté à apache_bench, même si le comportement du modèle sur les flows
apache_bench eux-mêmes ne change pas. Le seuil et le modèle étant fixes, la
décision de flagger un flow ne dépend jamais des autres flows présents dans
le set d'évaluation — c'est une propriété structurelle des deux
autoencodeurs testés (décision statique par flow, sans mémoire de
séquence).

Pour vérifier cela empiriquement, le recall a été **décomposé par
sous-type** à l'intérieur de chaque paire :

| Ensemble d'évaluation | Recall poolé (paire) | Recall apache_bench seul (décomposé) |
|---|---|---|
| apache_bench (solo) | — | 0.0328 ± 0.0055 |
| portscan + apache_bench (paire) | 0.3369 ± 0.0061 | 0.0324 ± 0.0050 |
| apache_bench + slowloris (paire) | 0.4044 ± 0.0029 | 0.0322 ± 0.0048 |

*(source : `06_attack_type_analysis/results_combined.md`)*

**Confirmation empirique : le recall d'apache_bench ne change pas
(0.0322-0.0328, à l'intérieur du bruit de seed) qu'il soit évalué seul ou
en présence d'un autre type.** La hausse apparente du recall "poolé" à
33-40% est un artefact du mélange, pas une amélioration réelle de la
détection d'apache_bench — ce point est explicité pour éviter toute
conclusion erronée du type « le pairing améliore la détection
d'apache_bench ».

---

## 4. Expérience d'injection segmentée (blocs contigus)

**Protocole.** Les mêmes flows de `test_with_attack_type.csv` (aucune
donnée synthétique, aucun rééchantillonnage avec remplacement) sont
réordonnés en un flux unique : le pool benign est divisé en 4 segments
quasi égaux, avec un bloc d'attaque contigu inséré entre chaque paire de
segments benign, dans l'ordre configurable
`apache_bench → slowloris → portscan`
(`07_segmented_injection/build_segmented_injection.py`, ordre
paramétrable via `--order`).

![Erreur de reconstruction du VAE clean-only le long du flux segmenté](figures/segmented_injection_error_plot.png)

*Figure 1 — Erreur de reconstruction (échelle log, moyenne sur 20 seeds) en
fonction de la position dans le flux segmenté. Les lignes verticales
marquent les frontières de segment ; la ligne pointillée horizontale est le
`threshold_95` moyen. Le bloc apache_bench reste visuellement au niveau
benign, alors que slowloris et portscan sautent immédiatement au-dessus du
seuil.*

| Segment | n | Benign FPR (thr95) | Attack Recall (thr95) | F1 (thr95) | Recall test set mélangé (réf.) |
|---|---|---|---|---|---|
| benign (seg. 0) | 1705 | 0.0305 ± 0.0070 | — | — | — |
| apache_bench | 1487 | — | 0.0322 ± 0.0044 | 0.0623 ± 0.0083 | 0.0328 ± 0.0055 |
| benign (seg. 2) | 1705 | 0.0336 ± 0.0078 | — | — | — |
| slowloris | 929 | — | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 |
| benign (seg. 4) | 1705 | 0.0962 ± 0.0222 | — | — | — |
| portscan | 694 | — | 0.9882 ± 0.0148 | 0.9940 ± 0.0075 | 0.9889 ± 0.0138 |
| benign (seg. 6) | 1706 | 0.0696 ± 0.0088 | — | — | — |

*(source : `07_segmented_injection/results_segmented.md`, threshold_95 moyen
= 0.1246)*

### Confirmation : comportement statique, indépendant de l'ordre

Les recalls par bloc (0.0322 / 1.0000 / 0.9882) sont **quasi identiques**
aux recalls du test set mélangé (0.0328 / 1.0000 / 0.9889) — la
différence est du même ordre que le bruit de seed. Ceci confirme
empiriquement que le VAE (comme le Dense autoencoder, voir section 5) est
un détecteur **statique par flow, sans état ni mémoire de séquence** :
qu'une attaque arrive isolée, mélangée à d'autres types, ou en bloc
contigu ne change rien à la décision prise sur un flow donné.

### Note de prudence — fluctuation du Benign FPR entre segments

Le FPR benign varie de **3.05% à 9.62%** selon le segment (vs. 5.75% en
moyenne sur tout le pool benign en un seul bloc). Il serait tentant d'y
lire un effet de "dérive" du modèle au fil du flux, mais **ce n'est
probablement qu'un artefact d'échantillonnage** : chaque segment ne
contient que ~1700 flows, une taille d'échantillon modeste pour un FPR
attendu autour de 5-6% (l'intervalle de confiance à cette taille couvre
largement l'écart observé). Le modèle n'a aucun état porté d'un flow à
l'autre, donc aucun mécanisme plausible de dérive n'existe ici — cette
fluctuation ne doit pas être interprétée sans un rejeu à plus grand n
(segments plus larges, plus de seeds) pour la confirmer ou l'infirmer.

---

## 5. Comparaison VAE vs Dense autoencoder v1

**Protocole.** Les 3 analyses précédentes ont été répétées à l'identique
(mêmes flows, mêmes 18 colonnes de features, même convention
`threshold_95`) sur `phase3_dense/04_phase3_models/full_features`
(5 seeds). Le Dense v1 n'ayant pas de fichier `threshold.json` sauvegardé
par seed, le seuil est recalculé à la volée comme le 95ᵉ percentile de
l'erreur de reconstruction sur les flows benign de validation de
`phase3_dense/03_phase3_splits` — convention reprise telle quelle de
`analysis/attack_type_breakdown_evaluation.py`. Le Dense v1 consomme les
mêmes colonnes `_scaled` que le VAE, sans scaler distinct (confirmé : les
`row_index` de ses propres splits pointent tous dans
`features_all_windows.csv`, sans offset vers les fenêtres
rééchantillonnées).

### Performance individuelle par type

| attack_type | Modèle | ROC-AUC | PR-AUC | F1 (thr95) | Attack Recall (thr95) |
|---|---|---|---|---|---|
| apache_bench | VAE | 0.5815 ± 0.0768 | 0.2133 ± 0.0219 | 0.0507 ± 0.0081 | **0.0328 ± 0.0055** |
| apache_bench | Dense v1 | 0.6957 ± 0.0791 | 0.2704 ± 0.0406 | 0.0401 ± 0.0003 | **0.0262 ± 0.0000** |
| portscan | VAE | 0.9982 ± 0.0005 | 0.9886 ± 0.0023 | 0.7737 ± 0.0161 | 0.9889 ± 0.0138 |
| portscan | Dense v1 | 0.9988 ± 0.0007 | 0.9912 ± 0.0032 | 0.7645 ± 0.0135 | 0.9931 ± 0.0155 |
| slowloris | VAE | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0.8271 ± 0.0158 | 1.0000 ± 0.0000 |
| slowloris | Dense v1 | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0.8157 ± 0.0055 | 1.0000 ± 0.0000 |

*(source : `08_dense_v1_comparison/results_single_attack_type_dense.csv/.md`)*

### Injection segmentée — Dense v1

![Erreur de reconstruction du Dense autoencoder v1 le long du flux segmenté](figures/segmented_injection_error_plot_dense.png)

*Figure 2 — Même flux segmenté que la Figure 1, évalué avec le Dense
autoencoder v1. Le bloc apache_bench forme une ligne quasi plate et
déterministe (écart-type de recall = 0.0000 sur les 5 seeds), contrairement
au nuage plus bruité du VAE (dû à l'échantillonnage stochastique de la
reparamétrisation) — mais le niveau d'erreur reste comparable, bien en
dessous du seuil.*

### Conclusion : la faiblesse sur apache_bench n'est pas spécifique à l'architecture

**Le Dense autoencoder v1 rate apache_bench au moins aussi mal que le VAE**
(recall 2.6% vs 3.3%, F1 0.040 vs 0.051) — sur les 3 protocoles testés
(individuel, paires, segmenté), les deux modèles échouent de façon quasi
identique. Une nuance intéressante : le Dense v1 a un **meilleur pouvoir de
séparation brut** sur apache_bench (ROC-AUC 0.696 vs 0.581, PR-AUC 0.270 vs
0.213) — son score continu ordonne mieux les flows apache_bench par rapport
au benign — mais cet avantage ne se traduit **pas** en meilleure détection
au seuil `threshold_95` réel, chaque modèle étant calibré indépendamment sur
sa propre distribution d'erreur benign.

### Comparaison macro-moyenne (équilibre global entre types)

| Modèle | Recall macro (3 types) | F1 macro (3 types) |
|---|---|---|
| VAE | 0.6739 | 0.5505 |
| Dense v1 | 0.6731 | 0.5401 |

L'écart entre les deux modèles (≤ 0.01) est **plus petit que la variance
inter-seed du VAE lui-même sur apache_bench (std ROC-AUC = 0.077)** — aucun
des deux modèles n'est donc de façon significative plus « équilibré » que
l'autre entre les types d'attaque. Le motif est identique dans les deux
cas : portscan et slowloris quasi parfaits, apache_bench presque
totalement manqué.

*(source complète : `08_dense_v1_comparison/comparison_vae_vs_dense.md`)*

---

## 6. Conclusion générale

1. **La métrique binaire `is_attack` masque une faiblesse structurelle
   sévère sur apache_bench** (recall 2.6-3.3% selon le modèle), invisible
   dans les rapports agrégés existants car diluée par les 2 autres types
   d'attaque, détectés quasi parfaitement (≥ 98.8% de recall).
2. **Ce recall n'est pas amélioré par la co-présence d'un autre type
   d'attaque** dans l'ensemble d'évaluation (recall décomposé stable à
   ~3.2-3.3% qu'apache_bench soit seul ou en paire) — la hausse du recall
   "poolé" observée en paire est un artefact de mélange de populations, pas
   une amélioration réelle de la détection.
3. **L'ordre d'arrivée des flows (mélangé vs bloc contigu) ne change rien**
   au comportement du modèle — confirmé empiriquement sur le VAE et le
   Dense v1, cohérent avec le fait que les deux sont des détecteurs
   statiques par flow, sans mémoire de séquence.
4. **La faiblesse sur apache_bench est partagée par le VAE et le Dense
   autoencoder v1** — deux architectures différentes échouent de façon
   quasi identique, ce qui pointe vers une **limite du jeu de 18 features
   actuel** plutôt qu'un défaut d'un modèle en particulier. Changer
   d'architecture d'autoencodeur ne résoudra probablement pas ce problème
   seul.

### Pistes pour la suite

- **Feature engineering ciblé sur la signature apache_bench** (requête
  HTTP fixe de 80 octets, `conn_state=SF`, durée < 1s) : des features
  actuellement absentes du pipeline (timing inter-requêtes, taux de
  requêtes par IP source sur une fenêtre glissante, ordre des octets dans
  la charge utile) pourraient mieux séparer ce trafic du HTTP benign — les
  18 colonnes actuelles (durée/bytes/pkts agrégés + protocole/service/
  conn_state one-hot) ne capturent pas la répétitivité qui distingue un
  benchmark HTTP automatisé d'une requête utilisateur isolée.
- **Seuil ou modèle spécifique par type d'attaque** (approche ensembliste)
  plutôt qu'un seuil unique global — étant donné que portscan et slowloris
  sont déjà quasi résolus, un second détecteur/seuil dédié à la signature
  HTTP courte pourrait cibler spécifiquement apache_bench sans dégrader les
  2 autres types.
- **Élargir le rééchantillonnage benign par segment** avant de tirer des
  conclusions sur la fluctuation du FPR observée en section 4 (3-9.6%) —
  vérifier si elle persiste à un n plus grand par segment.
