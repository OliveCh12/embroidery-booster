# Validation du moteur direct — 13 octobre 2026

## Comparaison des méthodes et performances

La [matrice actuelle](benchmarks/fill-methods-2026-10-13.json) compare **14
échantillons et cinq politiques**, avant/après la référence `650e164` : Auto
équilibré, priorité satin, satin strict, tatami uniforme et contours. Elle comprend
Phénix, Falcon, Nike bitmap, Pepsi, drapeau, courbes, pointes, branches,
contreformes et petits détails. Tous sont générés à 80 mm, profil PP1, tissu
stable, fil 40 wt et support à découper. Les images utilisateur restent locales ;
le rapport conserve leurs noms et empreintes, pas les images.

**Le satin strict passe désormais sur 11 cas sur 14, contre 4 auparavant.**
Les 67 politiques acceptées sur 70, contre 60 auparavant, restent accompagnées
de leurs diagnostics ; un export réussi n'est pas une qualification sur tissu.
Les trois refus satin sont conservés : couverture insuffisante de Pepsi,
directions incompatibles entre homologues du drapeau, et microîlots opaques du
SVG Nike historique sous la résolution satin. Les retirer ou les convertir en
tatami à l'insu de l'utilisateur aurait dénaturé le mode imposé.

| Image réelle | Nouveau résultat satin strict | Changement d'interprétation |
|---|---|---|
| Phénix | 3 171 points, 18 coupes, trois régions entièrement satin, aucune omission | Un unique fragment alpha de 0,0069 mm² est retiré au bord du même trait noir |
| Falcon | 4 298 points, 30 coupes, trois régions entièrement satin, aucune omission | 4 fils / 313 régions deviennent 1 fil noir / 3 régions ; 1 091 gris de bord partiellement transparents sont normalisés |
| Nike bitmap | Les trois régions passent le satin strict | La palette monochrome et les évidements sont conservés |
| Pepsi | L'Auto reste disponible ; le satin strict reste refusé | Quatre fils, blanc intérieur et contour noir restent préservés |

Phénix et Falcon passent les contrôles de couverture structurelle, points courts,
crowding et trajets supprimés. Les rubans directionnels complètent les rails MAT
qui laissaient des caps et jonctions découverts. Les six orientations possibles,
le plafond de 64 colonnes par région et les contrôles dans le repère machine
bornent ce travail. Les homologues gardent une stratégie et une décomposition
cohérentes ; les pointes très fines et le satin droit font l'objet de régressions.

### Temps mesurés

Les temps incluent interprétation, génération, previews et export, mais excluent
le démarrage/import Python et la relecture machine. Les trois cas simples sont
des **médianes de trois exécutions** dans le même environnement de développement.
Les logos sont des observations à une exécution, dont certaines réalisées
pendant les tests ; elles ne constituent pas des benchmarks matériels isolés.

| Cas / politique | Avant | Après |
|---|---:|---:|
| Colonne droite / satin | 0,173 s | 0,091 s |
| Courbe en S / tatami | 0,756 s | 0,384 s |
| Pointe / satin | 0,304 s | 0,153 s |
| Phénix / Auto seul | 1,911 s | 0,925 s |
| Falcon / Auto seul | 7,351 s | 1,122 s |
| Phénix / comparaison complète | 3,873 s | 2,098 s |
| Falcon / comparaison complète | 7,268 s | 3,360 s |

La comparaison recommande désormais le Phénix tout satin. Le choix « Satin
uniforme » partage ce plan déjà qualifié, sans répéter sa génération. Sur Falcon,
les cinq options sont calculées ; l'Auto reste en tatami avec zéro aire manquante
structurelle, alors que le satin ajoute 0,03 mm² manquants et davantage de sauts
(749 contre 609 mm), malgré moins de coupes (30 contre 45). Ce classement prudent
ne prétend pas choisir le plus beau reflet du fil. Les contours ne participent
jamais au classement des surfaces pleines.

Le pic RSS des processus mesurés est de 138–300 Mio après, contre 138–306 Mio
avant, hors appels de comparaison. Il inclut Python, bibliothèques natives,
génération et audits ; ce n'est pas une mesure des seules allocations Python.

### Densité et preuves machine

Douze plans supplémentaires/références évaluent satin et tatami à 80/100/120 %
sur Phénix et Falcon. Les rangs de surface se densifient ; les fondations tatami
restent à 816/1 030 points et le satin Phénix à 620 points. **Falcon satin à 120 %
change de décomposition** : 57 colonnes et 66 coupes contre 24 et 30 à 100 %,
avec 1 074 points de soutien contre 847. Le pourcentage n'est donc pas une
promesse de croissance linéaire du nombre total de points, ni d'amélioration
visuelle. **100 % reste le point de départ recommandé.** Le réglage est relatif
au matériau et ne crée pas de construction 3D avec mousse.

Au total, **212 appels de génération et 205 paires PES/DST relues** vérifient
cadre, longueurs, sauts, coordonnées et changements de couleur ; les fils PES
concordent. Les fichiers acceptés respectent ces contraintes. Une connexion
proposée dans Pepsi/contours est retirée : le champ historique
`unsafe_connections` compte les propositions rejetées, pas des points dangereux
émis. Le rapport distingue ces rejets, les omissions et les mesures de couverture.

La couverture structurelle emploie une tolérance de 0,25 mm autour d'un modèle
de fil de 0,3 mm. Par exemple, Phénix satin a 100 % structurels mais 97,58 %
selon le modèle de fil sans cette tolérance. **Aucun résultat cousu ni relief réel
n'est certifié.** Consulter le [protocole de couture](SEWOUT.md).

Le moteur fonctionne immédiatement avec un classement déterministe des audits.
Un apprentissage de préférences pourra aider plus tard, avec des résultats
cousus annotés par matériau ; des préférences sur captures 2D seules ne prouvent
ni la stabilité du tissu ni la qualité professionnelle. Aucun modèle lourd ou
base de données de validations obligatoires n'est ajouté.

```bash
uv run python scripts/benchmark_fill_methods.py --phase both --baseline-ref 650e164 \
  --phoenix /chemin/logo_phoenix.png --falcon /chemin/logo_falcon.png \
  --nike /chemin/nike.png --pepsi /chemin/pepsi.png \
  --output output/performance-quality
uv run python scripts/benchmark_fill_methods.py --phase current --policy comparison \
  --case phoenix --phoenix /chemin/logo_phoenix.png \
  --output output/performance-comparison
```

Validation : **579 tests Python, 61 tests frontend**, Ruff, TypeScript, ESLint
et build Next.js. L'interface a généré Phénix/Auto tout satin et Falcon/Satin
strict, avec un fil noir et des liens PES cohérents ; les thèmes clair/sombre
sont vérifiés. La galerie locale est recalculée sur les 31 SVG existants, à
80 mm profil PP1, avec une couverture structurelle globale ≥99,95 % ; ses
diagnostics d'omissions restent consultables.

## Référence précédente — propositions automatiques comparées

Le [benchmark des variantes](benchmarks/automatic-variants-2026-10-13.json)
évalue **12 entrées et 29 plans distincts**, à 80 mm, profil PP1, tissu stable,
fil 40 wt et stabilisateur à découper. L'image interprétée, la palette et les
réglages de tissu sont partagés ; les points de chaque proposition sont
générés et contrôlés indépendamment. Aucun essai physique n'est revendiqué.

| Cas | Recommandation et résultat |
|---|---|
| Colonne 32 × 12 mm | Priorité satin : deux colonnes, 533 points, couverture structurelle 100 %, flotté maximal 6,40 mm, aucune pénétration serrée |
| Nike bitmap fourni | Équilibré : un fil noir, 3 143 points, couverture structurelle 100 %. La variante satin est disponible ; les jonctions inadéquates restent en tatami |
| Pepsi bitmap fourni | Équilibré : quatre fils, blanc intérieur préservé, 12 623 points, couverture structurelle 100 %. Le tatami uniforme omet 21 microdétails et reste à vérifier |
| Union Jack SVG | Équilibré : trois fils, 9 210 points, 17 régions dont quatre satin, aucune omission ; homologues traités de manière cohérente |
| Nike SVG historique | Trois détails de 0,01 mm² sous la résolution machine : recommandation explicitement à vérifier |

**11 recommandations sur 12 passent les contrôles géométriques.** Les 58
fichiers PES/DST relus conservent exactement les coordonnées et les changements
de couleur ; les fils PES concordent. Tous les plans de ce corpus respectent
les limites du cadre, des points et des sauts, avec zéro connexion dangereuse,
point court ou pénétration satin trop proche. Les palettes, réglages physiques
et politiques des régions équivalentes concordent entre variantes.
Sur les images dépassant 256 régions visibles, un budget opérationnel conserve
la génération équilibrée et signale les alternatives non calculées. Il évite
de répéter trois fois les audits coûteux sans altérer l'interprétation de l'image.

Le classement ignore les petites différences de couverture déjà comprises
dans les seuils validés : un tatami ne remplace pas automatiquement un satin
utile pour gagner quelques centièmes de millimètre de distance au fil. La
priorité satin n'est recommandée que si le gain de surface satin est substantiel
et conserve les contrôles de couverture et les limites de déplacement. Le
nombre de points n'est pas un score de beauté.

Le cache réutilise rasterisation, quantification, repères, contours et MAT
communs sans partager de plan mutable. Les tests comparent les commandes
issues du cache et d'une génération indépendante. L'interface change aperçu,
fils, diagnostics et téléchargements ensemble lors du choix d'une variante.

```bash
uv run python scripts/benchmark_variants.py \
  --nike /chemin/nike.png --pepsi /chemin/pepsi.png \
  --output output/automatic-variants
```

Les deux bitmaps sont facultatifs et restent hors du dépôt. Les mesures décrivent
la géométrie des points sur la grille de 0,1 mm, avec la tolérance structurelle
de 0,25 mm ; elles ne prouvent pas l'opacité, la tension ni le relief sur tissu.

La référence précédente `650e164` passe : **503 tests Python**, **54 tests frontend**, Ruff,
TypeScript, ESLint et build Next.js. Les changements de proposition et de liens
PES sont vérifiés dans l'interface sur Nike et Pepsi, avec des layouts de
390 × 844 et 1440 × 1000 pixels et les thèmes clair/sombre. Les tests protègent
le plafond de comparaison inclusif à 256 régions et la conservation exacte du
primaire au-delà de ce plafond.

## Consolidation satin et imports

La [matrice reproductible](benchmarks/satin-input-reliability-2026-10-13.json)
compare `939f9f9` au moteur corrigé sur **26 cas**, à 80 mm : colonnes de 4 / 7,2 /
7,8 / 12 mm, pointe, anneau, branches, courbe serrée, trous, symétrie, drapeau,
accent coloré et les images Nike / badge JPEG / Pepsi fournies. Elle relit les
PES et DST et compare leurs coordonnées au plan quantifié, indépendamment de
l'aperçu. Les images utilisateur ne sont pas incluses dans le dépôt.

| Cas | Avant | Après |
|---|---|---|
| Colonne 7,8 mm en Satin | Refus à 7,5 mm | Deux colonnes adjacentes ; couverture structurelle 100 %, flotté maximal 4,50 mm |
| Colonne 12 mm / pointe large | Tatami en Auto, refus en Satin | Satin divisé audité ; couverture structurelle 100 % |
| Nike noir/blanc | Noir + blanc parasite ; 3 525 points | Noir seul ; 3 143 points, aucun blanc brodé |
| Badge JPEG, PP1 / six couleurs | 3 766 régions machine, 2 112 détails omis | 1 561 régions, 469 détails omis ; trois fils |
| Badge JPEG, douze couleurs | Refus : 6 974 régions après interprétation | Export ; 2 918 régions avant tracé, 3 045 régions machine ; quatre fils |
| Pepsi | Quatre fils dont le blanc intérieur | Mêmes quatre fils ; blanc préservé ; couverture structurelle 100 % |

La limite de **4 096 régions** et les longueurs machine ne sont pas augmentées.
La division satin conserve les rails extérieurs ; les coutures intérieures sont
bornées et décalées. Les régions compactes larges restent en tatami automatique.
Les quatre refus restants en Satin forcé — branches, courbe serrée, grande forme
trouée et Nike complet — signalent une couverture ou des piqûres inadéquates.
Leurs versions Auto exportent. Forcer le satin ne désactive aucun audit.

**22 générations sur 26 réussissent, contre 18 auparavant.** Tous les exports
réussis concordent exactement avec le plan : coordonnées, nombre de points,
changements de couleur et couleurs PES. Aucun dépassement du cadre, point court,
flotté au-delà de 8 mm ou saut au-delà de 12 mm n'est relevé.

Le JPEG complexe conserve un statut **à contrôler** : couverture structurelle
99,94 % / 99,90 %, plus grand manque 0,32 / 0,28 mm² en six / douze couleurs.
Des détails demeurent trop petits à cette taille. Il ne doit pas être présenté
comme une reproduction parfaite ou qualifiée sur tissu. Les temps de cette
comparaison sont des mesures uniques sous charge : environ 51 s en six couleurs
(86 s auparavant) et 104 s en douze couleurs. Ils ne sont pas un engagement de
performance. L'essai d'une réduction plus agressive des fragments a été écarté
pour préserver les peintures réelles.

Les régressions protègent aussi les accents cyan connectés ou isolés, le centre
blanc d'un badge épais, les peintures grises pâles, les SVG et les palettes
littérales. Le retrait des évidements monochromes reste une inférence signalée,
désactivable avec le nettoyage ; les intérieurs compacts ambigus sont conservés.
Les compteurs de nettoyage excluent désormais les choix sans modification.

Reproduction :

```bash
uv run python scripts/benchmark_reliability.py --baseline-ref 939f9f9 \
  --nike /chemin/nike.png --complex-badge /chemin/badge.jpg \
  --pepsi /chemin/pepsi.png --output output/reliability
```

Les trois images sont facultatives ; sans elles, le script compare 21 cas
synthétiques. L'interface est vérifiée avec le Nike noir seul et la colonne
7,8 mm en Satin forcé. La PP1 est le profil web par défaut ; les défauts
library/CLI restent compatibles. Un test PP1 combine satin et tatami avec un
seul fil, sans changement de bobine supplémentaire, avec réimport PES/DST exact.
La validation finale passe : **462 tests Python**, **51 tests frontend**, Ruff,
TypeScript, ESLint et build Next.js. Le JPEG en douze couleurs a aussi été généré
dans l'interface : PES/DST disponibles, statut à contrôler et manque de 0,28 mm²
affichés. Les diagnostics de nettoyage ont été recalculés après correction du
compteur sans changement ; les SVG interprétés sont identiques octet pour octet
à ceux de la matrice, donc ses mesures machine restent valides.

## Version actuelle : 0.5.1

La suppression du fond distingue maintenant les aplats, les dégradés doux
affines et les dégradés non linéaires. Une propagation depuis l'extérieur et
une protection des intérieurs fermés préservent les peintures du logo. Le
matting local retire les franges de compression accessibles depuis le fond ;
la préparation couleur récupère les pixels contaminés au contour avant la
palette. Le tracé multicolore partage une silhouette alpha et évite un second
antialiasing des masques de peinture. Aucun modèle ni dépendance n'est ajouté.

### Fidélité du masque

Le [benchmark des masques](benchmarks/background-masks-0.5.1.json) compare
`30c58df` à 0.5.1 sur **14 cas** : badges à fond uni, linéaire, radial ou coloré,
compressions PNG/JPEG/WEBP, accent isolé et Pepsi fourni. Les références
synthétiques sont connues avant composition. Pour Pepsi, la référence est un
proxy géométrique : l'intérieur du plus grand contour sombre fermé, avec une
tolérance de deux pixels source pour son antialiasing. Ce n'est pas une
annotation manuelle de photographie.

- Aucun pixel résiduel à plus de deux pixels de la référence sur ce corpus.
- Aucun pixel manquant dans le noyau érodé des motifs ; IoU minimale : **99,699 %**.
- Pepsi : **4 808 → 0** pixels parasites au-delà de cette tolérance,
  **75 → 1** composante, blanc intérieur conservé. La suppression seule prend
  0,264 s sur ce fichier ; temps indicatif d'une exécution.

Les calculs locaux coûteux utilisent des tuiles de 512 pixels et un contexte de
48 pixels. La fermeture du contour et la propagation restent globales : un
badge ne change pas d'interprétation parce qu'il traverse une limite de tuile.

### Conséquences sur les points de Pepsi

Le [benchmark machine à 80 mm](benchmarks/background-stitches-80mm.json)
utilise les mêmes paramètres avant/après : profil générique, quatre fils
effectifs, douze couleurs maximum, grille 305 DPI, fil modèle 0,3 mm et tolérance
structurelle 0,25 mm.

| Mesure | 0.5.0 | 0.5.1 |
|---|---:|---:|
| Points | 15 084 | 12 628 |
| Coupes | 304 | 176 |
| Sauts | 486 | 327 |
| Îlots après palette | 150 | 60 |
| Régions omises | 45 | 0 |
| Couverture structurelle par couleur | 99,99 % | 100 % |
| Plus grand manque structurel | 0,01 mm² | 0,00 mm² |
| Points courts / connexions dangereuses / pénétrations satin trop proches | 0 / 0 / 0 | 0 / 0 / 0 |
| Dimensions du plan | 79,8 × 80,3 mm | 80 × 80 mm |

Le liseré noir conserve le satin ; les surfaces larges gardent le tatami et
les petits détails leur traitement sûr. Les 27 détails compacts étendus d'au
plus 0,08 mm par extrémité sont signalés. La couverture structurelle n'est pas
une occupation de 100 % de chaque pixel par du fil : le tatami garde son
espacement prévu. Aucun essai sur tissu n'est revendiqué.

### Vérifications et reproduction

- **426 tests Python passent** (84,87 s), dont les frontières de tuiles, les
  accents pâles, les fonds ambigus et les badges compressés. Les régressions
  PNG/JPEG/WEBP génèrent aussi du PES et vérifient sa réimportation.
- **49 tests frontend passent** ; TypeScript, ESLint et le build Next.js passent.
  La liste des fils suit les vrais changements machine, y compris les couleurs
  répétées et les passages sans point. Les limites exactes des pauses et les
  contrastes du Canvas clair/sombre sont couverts. L'atelier est aussi vérifié
  à 390 px, sans débordement horizontal : pause avant le rouge de Pepsi, puis
  lecture continue jusqu'à la fin.
- Le lecteur compact est vérifié en clair/sombre et à 390 px : arrêt après
  **8 736 points**, avant le noir, puis reprise continue jusqu'aux **12 628**
  points. Changer le mode conserve la pause. La timeline répond à Home et aux
  flèches ; l'avance par commande reste disponible dans les options. Le panneau
  droit affiche contrôles et journal, défile indépendamment et se ferme avec
  Échap. Aucun débordement horizontal ni erreur console observé.
- Ruff, formatage, `git diff --check` et distributions Python 0.5.1 validés.
- L'atelier affiche le Pepsi nettoyé et ses diagnostics, puis la simulation
  dans un cadre 100 × 100 mm. Le PES téléchargé contient exactement les
  **12 628 pénétrations** et coordonnées du plan quantifié, avec quatre fils.

```bash
uv run python scripts/benchmark_background.py --baseline-ref 30c58df \
  --pepsi /chemin/pepsi.png --output output/background-validation
uv run python scripts/benchmark_direct.py --baseline-ref 30c58df \
  --design-width-mm 80 --input /chemin/pepsi.png \
  --output output/background-stitches.json
```

Le premier script utilise les fixtures synthétiques du dépôt ; le fichier
Pepsi est optionnel et reste local. Les fichiers utilisateur ne sont pas
ajoutés au dépôt.

Les fonds texturés ou ambigus restent conservés en Auto. Il n'y a pas de
segmentation sémantique universelle des photos. Un cas JPEG supplémentaire de
1 040 pixels avec un liseré d'un pixel peut encore garder 38 pixels gris
éloignés de plus de deux pixels : le moteur privilégie la conservation des
vrais détails ambigus. L'aperçu et le choix Conserver/Retirer restent nécessaires
pour ces entrées. Voir les [règles d'interprétation](INPUT_INTERPRETATION.md).

## Historique : validation 0.5.0

Les mesures et vérifications ci-dessous concernent **0.5.0** : interprétation du fond, consolidation des couleurs bitmap,
nettoyage borné des parasites et choix Auto/Satin/Tatami/Point droit. Le moteur
reste entièrement direct, avec PES/DST exportés par pyembroidery.

## Corpus géométrique de référence

Le [benchmark à 80 mm](benchmarks/input-strategy-80mm.json) compare la révision
`f8dacbc` à cette version sur **31 SVG** : logos, lettres, courbes, anneaux, trous
intentionnels, angles, petites îles, multicolore et Union Jack. Paramètres et
mesure identiques : grille 305 DPI, fil modèle 0,3 mm, couche supérieure
quantifiée, tolérance structurelle 0,25 mm.

| Mesure | 0.4.0 | 0.5.0 |
|---|---:|---:|
| Générations réussies | 31/31 | 31/31 |
| Couverture structurelle moyenne | 99,9994 % | 99,9994 % |
| Couverture minimale | 99,98 % | 99,98 % |
| Plus grand manque | 0,02 mm² | 0,02 mm² |
| Points trop courts | 0 | 0 |
| Pénétrations satin trop proches | 0 | 0 |
| Coupes | 1069 | 1068 |

Les homologues conservent une stratégie commune. L'angle par couleur concerne
les surfaces substantielles ; les détails fins gardent leur angle géométrique.
Les temps sont enregistrés à titre indicatif, avec des validations concurrentes.
L'ancien [benchmark du passage au direct uniquement](benchmarks/direct-only-80mm.json)
reste disponible comme mesure historique.

```bash
uv run python scripts/benchmark_direct.py --baseline-ref f8dacbc \
  --design-width-mm 80 --output docs/benchmarks/input-strategy-80mm.json
uv run python scripts/compare_quality.py --design-width-mm 80 \
  --machine brother-skitch-pp1
```

## Images fournies : Pepsi et aigle

Le [benchmark des images](benchmarks/input-interpretation-80mm.json) contient
leurs empreintes SHA-256 et une comparaison complète avec `f8dacbc`, à largeur
80 mm, profil générique, 12 couleurs maximum. Les fichiers utilisateur restent
locaux ; ils ne sont pas ajoutés au dépôt.

| Mesure | Pepsi avant | Pepsi après | Aigle avant | Aigle après |
|---|---:|---:|---:|---:|
| Fils | 8 | 4 | 11 | 11 |
| Points | 18 030 | 15 084 | 18 502 | 18 590 |
| Coupes | 1291 | 304 | 1999 | 1043 |
| Sauts | 1868 | 486 | 2192 | 1242 |
| Couverture structurelle par couleur | 99,71 % | 99,99 % | 99,43 % | 99,51 % |
| Plus grand manque par couleur | 0,03 mm² | 0,01 mm² | 0,16 mm² | 0,24 mm² |
| Régions trop petites omises | 891 | 45 | 1258 | 2394 |

**Pepsi :** le fond extérieur gris `#f2f2f2` est retiré ; le badge blanc, le
contour noir, le rouge et le bleu restent peints. La consolidation passe de
2976 à 150 îlots avant tracé, avec quatre couleurs de fil. Les 83 211 pixels
signalés correspondent aux nuances réaffectées à ces couleurs, pas à des pixels
alpha effacés. Les derniers petits fragments contrastés de compression restent
visibles dans les diagnostics, plutôt que d'être confondus avec un vrai accent.

**Aigle :** l'alpha indique déjà un fond transparent. Le nettoyage fusionne
3628 pixels de couleur proche, soit 91,05 mm² à cette taille : 4538 → 1512 îlots
avant tracé. Aucun alpha n'est supprimé. Les coupes baissent de **48 %** ; le
nombre total de points augmente légèrement. Le recadrage avant échantillonnage
conserve davantage de contours et de très petits détails que l'ancien tracé.
Les masques interprétés diffèrent donc : les couvertures avant/après ne sont
pas des mesures de fidélité au même bitmap brut. Les régions omises et le plus
grand manque augmentent aussi sur cet exemple ; le résultat reste explicitement
**à contrôler**, sans promesse de broderie parfaite. Réduire la palette peut
simplifier ces dégradés ; le preset PP1 propose six fils maximum.

Le [test supplémentaire PP1](benchmarks/input-pp1-80mm.json) donne 13 180 points,
6 fils et 818 coupes sur le même aigle à 80 mm. Aucun point court, crowding ou
connexion dangereuse ; couverture par couleur 99,60 %, plus grand manque
0,31 mm². Cette réduction simplifie les opérations machine mais ne valide pas
les petits détails manquants : le statut reste à contrôler.

Le benchmark distingue la couverture de silhouette (`top_metrics`) et les audits
par couleur (`stats`). La silhouette globale peut être entièrement couverte
alors que de minuscules îles d'une couleur restent manquantes. Les audits par
couleur et omissions déterminent la nécessité de revue ; une moyenne globale
ne les masque pas.

Pour répéter sur les fichiers d'origine :

```bash
uv run python scripts/benchmark_direct.py --baseline-ref f8dacbc \
  --design-width-mm 80 --input /chemin/pepsi.png --input /chemin/aigle.png \
  --output output/input-benchmark.json
```

## Régressions et fichiers machine

- **357 tests Python passent** sur la version finale (80,30 s).
- Fond fermé blanc conservé ; fond extérieur retiré par propagation ; ouverture
  alpha et canal diagonal respectés. Rotation/reflet ne changent pas ce choix.
- Logo JPEG compressé : quatre aplats récupérés, un vrai accent vert isolé
  conservé. Nettoyage borné, opt-out, alpha inchangé et taille finale du cadre
  vérifiés. La limite de 4096 régions est vérifiée avant le tracé coûteux.
- Satin forcé valide sur colonnes sûres et refusé sur formes incompatibles.
  Fill forcé évite le MAT ; running signale sa couverture de contours.
- Une frange de l'aigle révélait un ancrage débordant après son second arrondi.
  Un contour réduit à sept sommets reproduit le défaut ; l'ancrage corrigé
  reste dans la géométrie autorisée, sans omission ni point trop court.
- Les rejets géométriques des candidats restent distincts des erreurs fatales de
  budget/cadre. Les omissions sont signalées et restent dans l'audit.
- Les points réimportés depuis PES/DST sont comparés au plan quantifié. Plages de
  couverture, sous-couche, liaisons et ancrages ne se recouvrent pas dans leur
  comptage. `underlay_stitches` exclut désormais les nœuds de contexte.
- **32 tests frontend passent**, ainsi que TypeScript, ESLint et le build Next.js.
  Les réglages sont sérialisés explicitement. Le lecteur distingue les phases
  et masque les marqueurs de début/aiguille sur le résultat terminé.
- L'atelier est vérifié avec le Pepsi fourni : refus explicite du satin forcé,
  Tatami uniforme sur les régions cousables, puis Auto avec quatre fils. Les
  filtres d'aperçu et la lecture pas à pas fonctionnent. Le PES téléchargé depuis
  l'interface retrouve exactement les 15 084 pénétrations du plan quantifié
  (79,8 × 80,3 mm dans le cadre PP1), y compris leurs coordonnées.
- Les distributions Python 0.5.0 (`sdist` et `wheel`) se construisent avec succès.

## Limites physiques

Une couverture structurelle de 100 % ne signifie pas que chaque pixel est
recouvert de fil : le tatami conserve un espacement volontaire. Les trous
intentionnels restent ouverts ; les détails sous la résolution machine sont
signalés. Le nettoyage modifie seulement l'interprétation documentée, jamais
une mesure pour faire artificiellement réussir un audit.

Le lecteur montre les commandes réelles, y compris sauts, coupes et changements
manuels de fil. Le profil PP1 utilise 400 points/min et un cadre 100 × 100 mm
([Brother](https://www.brother-usa.com/p/sewing-embroidery/PP1)). Le temps affiché
exclut les changements de bobine, déplacements et accélérations.

La validation professionnelle finale exige un [essai sur tissu](SEWOUT.md).
Aucun résultat cousu physiquement n'est revendiqué dans ce rapport.
