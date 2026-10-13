# Validation du moteur direct — 13 octobre 2026

## Version 0.6.3 : satin utile, fidélité comparée au tatami

Auto décrit désormais traits, contreformes, détails arrondis et surfaces
compactes/larges. Les nouveaux essais satin équilibrés sur des formes étroites
sont vérifiés dans le repère final, sur la grille machine, puis comparés à un
candidat tatami. Une couverture structurelle acceptable ne suffit plus à les
promouvoir lorsque le fil couvre moins bien la forme ou déborde davantage.
Les petits détails ronds déjà qualifiés restent satin à côté d'un grand corps
rempli. La préférence esthétique entre variantes vérifie également la
couverture littérale ; la sécurité reste prioritaire.

Le [rapport comparatif](benchmarks/auto-satin-fidelity-2026-10-13.json) fige
`main` à **dc8081d**, le précédent 0.6.2 à **46b4397**, et le candidat par
empreinte source. **32 entrées**, dont neuf paires SVG/PNG, logos réels, texte,
anneaux, traits décalés et pastilles avec un corps rempli, utilisent les mêmes
fichiers et réglages PP1/coton/fil 40 wt/stabilisateur à découper. Les bitmaps
rendus des fixtures sont dimensionnés d'après leur recadrage réel : demander
80 mm aux deux formats sans tenir compte des marges aurait changé la couture.

Les commandes des deux références sont identiques sur ces 32 cas. Le nouveau
Balanced modifie **5 plans**, conserve exactement les **27 autres**, sans changer
leur palette. Les contours et la séparation des couleurs ne sont pas modifiés
par ce lot. Les PES/DST des 32 résultats sont relus ; les points, changements de
fil, bounds du cadre et limites de longueur restent conformes aux plans.
Aucun crowding satin mesuré n'est ajouté. Trois micro-régions du Nike SVG et
deux du multicolore PNG restent omises comme dans les deux références ; ce
corpus n'est donc pas présenté comme entièrement sans défaut.

| Couverture littérale du fil | main et 0.6.2 | 0.6.3 | Points du dessin |
|---|---:|---:|---:|
| Courbe serrée SVG | 84,37 % | 91,74 % | 221 → 178 |
| Courbe serrée PNG | 73,03 % | 90,45 % | 231 → 178 |
| Pepsi, couche noire | 86,21 % | 90,49 % | dessin : 12 458 → 12 473 |
| Pastille r = 2 mm, mesure locale | 85,65 % | 97,52 % | dessin : 1 611 → 1 585 |
| Pastille r = 2,5 mm, mesure locale | 83,93 % | 97,45 % | dessin : 1 654 → 1 597 |

Ces mesures concernent uniquement les points supérieurs quantifiés, avec un
fil modélisé de 0,3 mm ; sous-couches, ancrages et déplacements sont exclus.
La couverture structurelle utilise séparément une tolérance de 0,25 mm.
Les pastilles sont mesurées par région dans une fenêtre physique bornée ; le
rectangle reste identique. Les couches Pepsi bleue, rouge et blanche restent
respectivement à 81,92 %, 81,83 % et 84,14 %. Sur la courbe SVG, le débordement
passe de 5,25 à 6,04 mm² : ce coût est mesuré et reste dans la borne comparative
retenue. Les longs points satin restent sous la recommandation PP1 de 7 mm.

Le premier prototype, qui promouvait tout satin structurellement admissible,
faisait chuter la couverture d'un petit anneau de **97,25 % à 82,07 %** selon sa
position. Il est rejeté. Le garde-fou final compare le candidat au tatami : perte
maximale de 0,5 point de couverture et surplus de débordement limité au plus
grand de 0,25 mm² ou 2 % de la surface. Les quatre contrôles anneau/trait à 0,75×
et deux positions conservent ici exactement leurs anciens points. Un anneau
avec un pas satin explicite trop large reste refusé. Les formes en L équivalentes
partagent aussi leur méthode et leur direction réellement exportée.

Des essais à plusieurs pas montrent que des traits plus denses peuvent être
qualifiés en satin, sans que tous les pas et positions reçoivent ce choix.
La quantification de 0,1 mm et les fragments de rails restent sensibles à la
position ; un type identique ne garantit pas une séquence identique. Réduire les
jonctions et lisser les rails est le prochain travail de qualité, avant de
promouvoir davantage de petits anneaux.

Les temps suivants mesurent **la génération complète**, interprétation,
points et exports compris, avec comparaison des variantes désactivée. Chaque
référence utilise un processus neuf par cas, une chauffe et cinq mesures,
séquentiellement après les tests/builds. Les fichiers des six générations
sont identiques par référence. La machine de développement reste partagée :
ces observations ne démontrent pas un gain causal ni un speedup universel.

| Génération médiane | main | 0.6.2 | 0.6.3 |
|---|---:|---:|---:|
| Anneau | 0,511 s | 0,627 s | 0,558 s |
| Courbe en S | 0,801 s | 1,012 s | 0,705 s |
| Courbe serrée | 0,176 s | 0,211 s | 0,154 s |
| Trait droit | 0,204 s | 0,230 s | 0,163 s |
| Multicolore | 1,641 s | 1,510 s | 1,148 s |
| Phénix | 1,994 s | 2,642 s | 1,807 s |
| Nike avec lettrage | 2,774 s | 4,131 s | 2,661 s |
| Petit anneau 0,75× | 0,130 s | 0,158 s | 0,139 s |

La médiane est plus faible sur 8/8 cas face à la 0.6.2 et 6/8 face à main.
L'anneau et le petit anneau restent environ 9 % et 7 % plus lents que main.
Le p95 empirique augmente sur la courbe en S, le trait droit et le petit anneau
face au précédent malgré leurs médianes plus faibles. Le RSS final va de 139
à 251 Mio ; Phénix monte d'environ 222 à 240 Mio face au précédent, tout en
restant sous les 251 Mio de main. Le RSS inclut interpréteur, imports et chauffe,
mesuré avant les audits indépendants hors chrono. Tous les échantillons,
p95 et pics sont conservés dans le rapport.

Validation : suite complète de **887 tests Python**, puis **29 tests ciblés de
variantes après le dernier ajustement** ; **147 tests frontend**, Ruff,
TypeScript, ESLint et build Next.js isolé réussis. La wheel 0.6.3 correspond aux
35 fichiers Python validés. Le parcours web affiche v0.6.3 et une courbe Auto en
satin à 178 points ; téléchargements PES/DST relus, diagnostics vérifiés en
thèmes clair et sombre. Aucune couture physique PP1 n'a encore été validée.
La [roadmap](ROADMAP.md) distingue les fonctions livrées des prochains lots.

## Version 0.6.2 : coût réduit, fidélité conservée, comparaison explicite à main

Ce lot accélère trois primitives exactes : histogramme RGB par entier plutôt
que tri de triplets, égalité des quatre octets RGBA pour les noyaux, et comptage
des régions par tuiles à histogramme dense borné. Aucun seuil de couleur,
de détail, d'alpha ou de couverture n'est assoupli. Aucun cache global ou
canvas supplémentaire par peinture n'est ajouté.

Le [comparatif à trois références](benchmarks/interpretation-performance-2026-10-13.json)
fige `main` à **dc8081d**, le lot précédent à **97f6035** et le source candidat
0.6.2 par empreinte. Les **78 entrées** ont les mêmes octets source. Contre la
0.6.1, **78/78 SVG, rendus et diagnostics sont exactement identiques**, y compris
les tentatives et choix de réduction. Ce lot apporte donc une accélération,
pas une nouvelle interprétation graphique.

Face à `main`, le gain de qualité cumulé est conservé : dans les 19 accents
supplémentaires à vérité connue, **6 → 12** subsistent ; les contrôles de cercle
et trait oblique retrouvent le fil violet, la pastille noire retrouve son RGB
source, et le bord flouté évite deux fils indésirables. Un contre-trou alpha perdu
sur `main` est aussi conservé. Les 46/78 rendus restés identiques comprennent
Pepsi, Phénix, Falcon et Union Jack. Les 32 différences restantes ne sont pas
toutes présentées comme un gain de couture : ce sont des différences mesurées
d'interprétation, à rapprocher des oracles. Le XML des 78 SVG diffère de celui de
`main` à cause de sa sérialisation ; cela ne constitue pas un progrès visuel.

| Contrôle à 20 mm | main | 0.6.1 et 0.6.2 |
|---|---:|---:|
| Cercle violet anticrénelé de 0,5 mm | 2 fils, 272 points | 3 fils, 331 points |
| Trait oblique violet anticrénelé de 0,5 mm | 2 fils, 288 points | 3 fils, 333 points |
| Pastille noire anticrénelée | noir `#0d1010`, 276 points | noir source `#101010`, 331 points |
| Bord rouge/bleu flouté à 3 px | 4 fils, 247 points | 2 fils, 238 points |

Sur **7/7 références machine**, commandes sélectionnées, fils, PES/DST et
previews sont identiques à `main` et au précédent. Les quatre contrôles du
tableau conservent exactement les plans et exports de la 0.6.1, avec des
coordonnées finies, sans région omise ni liaison dangereuse mesurée. Quelques
métriques du candidat fill **non sélectionné** de Falcon diffèrent légèrement
de `main`, comme documenté auparavant ; aucune égalité globale de ses
diagnostics n'est revendiquée.

Les performances ci-dessous mesurent uniquement la **préparation de l'image**,
pas la génération complète des points. Les trois sources sont relancées
séquentiellement après les suites de validation : une chauffe et sept mesures
par image, en processus isolés, sans topologie ni rendu indépendant dans le
chemin chronométré. La charge de fond du système reste incontrôlée ; les p95
empiriques sont disponibles dans le JSON.

| Préparation médiane | main | 0.6.1 | 0.6.2 | Écart 0.6.2 / main |
|---|---:|---:|---:|---|
| Pepsi | 0,652 s | 0,665 s | 0,608 s | environ 7 % plus rapide |
| Phénix | 0,260 s | 0,328 s | 0,262 s | stable, environ +1 % |
| Falcon | 0,155 s | 0,158 s | 0,121 s | environ 22 % plus rapide |
| Union Jack | 0,600 s | 1,711 s | 1,356 s | 2,26 fois plus lent |
| Cercle violet anticrénelé de 0,5 mm | 0,010 s | 0,113 s | 0,085 s | environ 8,4 fois plus lent, violet récupéré |
| Bord flouté à 3 px | 0,011 s | 0,088 s | 0,061 s | environ 5,7 fois plus lent, 4 → 2 fils |

La médiane baisse sur **9/9 cas** face à la 0.6.1. La réduction du coût du drapeau
est d'environ **21 %** ; ses contrôles source restent coûteux face à `main`, même
si son résultat est identique. Les petits contrôles gagnent en médiane, mais
pas tous en p95 : le trait oblique passe de 0,112 à 0,137 s en p95 malgré une
médiane améliorée. Aucune baisse universelle de latence n'est annoncée.

| Pic RSS total | main | 0.6.1 | 0.6.2 |
|---|---:|---:|---:|
| Pepsi | 211 Mio | 218 Mio | 213 Mio |
| Phénix | 206 Mio | 197 Mio | 190 Mio |
| Falcon | 157 Mio | 150 Mio | 148 Mio |
| Union Jack | 631 Mio | 649 Mio | 635 Mio |
| Cercle violet anticrénelé de 0,5 mm | 118 Mio | 128 Mio | 135 Mio |

Le RSS inclut les imports, bibliothèques natives et chauffe de chaque processus.
Les gains mémoire ne sont pas uniformes et ne représentent pas des allocations
par étape. Les budgets restent 16 MP en source et 2 048 px au travail ; les bins
denses et valeurs temporaires de comptage sont bornés à 65 537 / 65 536.

Le script suivi [benchmark_interpretation.py](../scripts/benchmark_interpretation.py)
génère sept fixtures sans image personnelle et compare les refs par archives Git,
sans changer de checkout. Les modes qualité/performance sont séparés, les sources
hashées et les diagnostics complets enregistrés. Un dossier de sortie neuf est
requis. Le corpus complet de 78 entrées et les sources réelles restent des
artefacts locaux ; le rapport conserve ses paramètres et conditions de reprise.

**Limites inchangées : sept accents JPEG encore perdus, 14 diagnostics de noyaux
non résolus et le petit parasite JPEG préexistant.** Le drapeau garde ses
58 micro-régions omises. Les contrôles graphiques et les exports réimportés ne
certifient pas une couture physique, ni l'acceptation par Brother.

Validation : **865 tests Python**, **132 tests frontend**, Ruff, TypeScript,
ESLint et build Next.js isolé passent. La wheel 0.6.2 contient les mêmes fichiers
Python que le source validé. Le parcours web affiche v0.6.2, trois fils et
331 points ; ses PES/DST téléchargés sont identiques à ceux de la 0.6.1.

## Version 0.6.1 : accents anticrénelés et preuves de peinture source

Le quatrième lot retrouve les noyaux opaques et constants des aplats avant
réduction, même lorsque leurs bords comportent beaucoup de nuances. Il compare
les candidats avec la palette réellement produite par `bitmap_colors` ; une
proximité RGB globale pouvait inventer du violet entre deux aplats rouge/bleu.
Aucune couleur n'est injectée dans l'image. Si les preuves couleur restent
ambiguës, le moteur conserve la réduction historique qui protège la silhouette,
y compris les contreformes alpha. Le contrat, les seuils et l'opt-out sont
précisés dans [l'interprétation](INPUT_INTERPRETATION.md#préserver-les-détails-avant-la-palette).

Le [rapport avant/après](benchmarks/source-paint-cores-2026-10-13.json) compare
**78 entrées** à `d27c73a`, avec sources identiques par empreinte : les 47 cas
précédents, 29 contrôles à vérité connue et deux champs de couleur continus.
Les conversions aboutissent sans erreur ; **66 SVG restent identiques et 12
changent**. Dans les 19 accents supplémentaires connus, la conservation passe
**de 6 à 12** : quatre cercles/traits anticrénelés et deux H JPEG à qualités
35/75 sont récupérés. Les quatre cercles restés absents au lot 0.6.0 sont aussi
corrigés. Les dix contrôles négatifs ne produisent aucun nouveau parasite ; un
bord flouté passe de cinq peintures interprétées à deux, celles de sa source.

Quatre contrôles de couture à 20 mm, profil PP1, sont relus en PES et DST :

| Contrôle | Avant | Après |
|---|---:|---:|
| Cercle violet anticrénelé de 0,5 mm | 2 fils, 272 points | 3 fils, 331 points |
| Trait oblique violet anticrénelé de 0,5 mm | 2 fils, 288 points | 3 fils, 333 points |
| Pastille noire anticrénelée | 276 points, noir `#0d1010` | 331 points, noir source `#101010` |
| Bord rouge/bleu flouté à 3 px | 4 fils, 247 points | 2 fils, 238 points |

Les coordonnées sont finies, les fils et changements de couleur correspondent
aux plans et aucune région n'est omise sur ces quatre contrôles. Sur **7/7
références historiques**, SVG interprétés, labels, topologies, commandes, fils,
décisions, statistiques, previews et octets PES/DST restent strictement identiques.
Le drapeau conserve ses 58 micro-régions omises : ce lot ne change pas le
planificateur de points.

La mesure porte seulement sur la préparation : une chauffe puis sept passages,
en processus séparés, sur la machine de développement dont la charge concurrente
n'est pas contrôlée. Elle documente un coût de fidélité, pas une accélération.

| Entrée | Médiane avant → après | p95 avant → après |
|---|---:|---:|
| Pepsi | 0,643 → 0,651 s | 0,655 → 0,669 s |
| Phénix | 0,299 → 0,328 s | 0,304 → 0,333 s |
| Union Jack | 0,640 → 1,680 s | 0,653 → 1,782 s |
| Cercle violet anticrénelé, 20 mm | 0,015 → 0,119 s | 0,015 → 0,160 s |
| Bord flouté, 20 mm | 0,014 → 0,089 s | 0,014 → 0,096 s |

Le pic RSS total du drapeau passe de 636 à 662 Mio. Les stress de 16 MP restent
bornés à une grille de travail de 960² : 0,82 s / 574 Mio pour un damier et
0,34 s / 263 Mio pour un RGB opaque à nombreuses nuances. Ces pics incluent
Python, les imports et bibliothèques natives ; le RGB de stress n'est pas une
photo sémantique. Les budgets source/travail restent 16 MP / 2 048 px maximum.

**Limites : sept accents JPEG restent perdus**, 14 diagnostics de noyaux restent
non résolus et le petit parasite préexistant de la diagonale JPEG 35 subsiste.
Les deux H JPEG restaurés possèdent des noyaux constants exploitables : aucune
tolérance JPEG ni promesse générale de restauration des photos n'est ajoutée.
Les contrôles portent sur la fidélité graphique et les fichiers exportés ; ils
ne prouvent ni un résultat cousu ni l'acceptation par un fabricant.

Validation : **808 tests Python**, **132 tests frontend**, Ruff, TypeScript,
ESLint, build Next.js isolé et contenu de la wheel 0.6.1 vérifiés. Le parcours web
produit les trois fils et 331 points du cercle ; les téléchargements PES/DST
sont relus avec deux changements de couleur et des coordonnées finies. Le header
affiche v0.6.1 et la simulation a été contrôlée en light/dark. Les régressions
critiques sont reproductibles par les tests du dépôt. Les scripts complets du
corpus, snapshots et images utilisateur sont des artefacts locaux ignorés ;
le rapport précise les empreintes, paramètres et conditions de reproduction.

## Version 0.6.0 : détails conservés avant réduction

Le troisième lot inspecte le bitmap source avant le thumbnail et la palette.
Il conserve le candidat historique quand les détails significatifs subsistent,
et adapte la grille seulement en présence de pertes mesurées. Les règles,
seuils et limites sont décrits dans [l'interprétation](INPUT_INTERPRETATION.md#préserver-les-détails-avant-la-palette).
Le header affiche **v0.6.0**, depuis le package frontend, en light/dark et sur
écran étroit. Le rapport de réduction rejoint les diagnostics existants.

Le [corpus avant/après](benchmarks/adaptive-sampling-2026-10-13.json) compare
**47 entrées** à la référence `a11df08` : aplats avec accents et traits de
0,1/0,25/0,5/1 mm, contreformes alpha, rotations/reflets/marges, JPEG à trois
qualités, badge sur dégradé, cercles antialiasés et quatre logos réels.
Les sources sont identiques par empreinte. Les 47 conversions aboutissent ;
19 adaptent utilement leur grille, dont **18 récupèrent une peinture violette**
et une récupère une contreforme alpha. Aucun écart significatif n'est laissé
sans résolution dans le périmètre audité. Cela ne certifie pas les couleurs
des images dont seul l'alpha a été comparé.

Deux contrôles brodables à 20 mm démontrent une correction jusqu'aux points :

| Détail violet littéral de 0,5 mm | PNG avant | PNG après | SVG natif |
|---|---:|---:|---:|
| Trait de 2,5 mm de haut | 2 fils, 255 points | 3 fils, 260 points | 3 fils, 280 points |
| Carré | 2 fils, 270 points | 3 fils, 243 points | 3 fils, 340 points |

Avant, une couverture structurelle proche de 100 % masquait la disparition
complète du violet dans l'interprétation. Après, les deux PNG conservent ce fil,
sans omission, et la relecture PES/DST confirme les points, deux changements
de couleur et des coordonnées finies dans le cadre PP1. PNG et SVG ne produisent
pas les mêmes commandes ; la correction ne prétend pas les rendre identiques.

Sur **7/7 références**, SVG interprétés, labels, topologie, commandes, fils,
décisions, statistiques, aperçu SVG et octets PES/DST restent exactement
identiques. Phénix conserve 2 709 points et 18 coupes. Les 58 micro-régions
omises du drapeau restent présentes dans les diagnostics de référence : ce lot
ne modifie pas le planificateur de points. Les poussières sous 0,01 mm² ne
déclenchent plus un faux split si le corps principal subsiste ; une fragmentation
entière en poussières et une nouvelle contreforme significative restent détectées.

Les performances ci-dessous mesurent uniquement la préparation, dans des
processus séparés, après une chauffe et sur sept passages. Le p95 est empirique
sur cet échantillon court. La charge de la machine de développement n'est pas
contrôlée ; ces résultats documentent le coût, sans prouver une accélération.

| Entrée | Médiane avant → après | p95 avant → après |
|---|---:|---:|
| Trait violet 0,5 mm, motif 20 mm | 0,011 → 0,079 s | 0,012 → 0,081 s |
| Même détail, motif 80 mm | 0,178 → 1,250 s | 0,182 → 1,295 s |
| Phénix | 0,287 → 0,328 s | 0,290 → 0,339 s |
| JPEG qualité 35 | 0,169 → 0,182 s | 0,207 → 0,189 s |

Le cas 80 mm paie une grille quatre fois plus grande et les contrôles source,
avec un pic RSS total de 260,9 → 350,4 Mio. Un stress indépendant de 16 MP donne
574 Mio pour un damier très fragmenté et 261 Mio pour du RGB opaque à nombreuses
nuances ; ces pics incluent Python, les imports et les bibliothèques natives.
Le second stress n'est pas une photo sémantique. Le plafond de travail reste
2 048 pixels et celui de la source 16 MP ; aucune super-résolution n'est appliquée.

**Limite importante : quatre cercles violets antialiasés de 0,25/0,5 mm restent
absents après palette.** Leurs nombreuses nuances les placent dans le contrôle
alpha seul. Récupérer ces couleurs avant réduction est le prochain lot ; aucune
garantie de fidélité complète des photos ou JPEG difficiles n'est annoncée.

Validation : **786 tests Python**, **130 tests frontend**, Ruff, TypeScript,
ESLint, build Next.js et wheel 0.6.0. Le parcours web a généré les trois fils du
PNG de contrôle ; le header reste visible en light/dark et à 320 px de largeur.
Ces contrôles logiciels ne remplacent pas un essai sur tissu.

## Consolidation : contrat d'interprétation

Le premier lot de `engine-consolidation` conserve le comportement de `dc8081d`
et ajoute un contrat immutable des masques, couleurs et unités physiques. La
comparaison [avant/après sur sept entrées](benchmarks/interpretation-contract-2026-10-13.json)
retrouve des SVG interprétés, labels/topologies, commandes, palettes, décisions,
aperçus SVG et fichiers PES/DST identiques. Seuls les diagnostics géométriques
de l'entrée sont enrichis. Les paramètres de comparaison sont enregistrés ;
ces exécutions isolent la compatibilité et ne mesurent pas un gain de vitesse.
Les références couvrent Pepsi, Phénix, Falcon, drapeau, anneau, PNG à trou et
détail détaché, puis SVG à couleurs superposées.
Le drapeau conserve 58 petits détails omis et une couverture structurelle de
99,99 % déjà présents dans la référence. Une compatibilité exacte ne valide
donc pas la qualité de ces détails.

## Consolidation : fidélité du tracé et profils couleur

Le deuxième lot ajoute un audit catégoriel du SVG sur la grille immuable des
labels, avec retour aux contours non simplifiés si la simplification les altère.
Les tests isolés montrent la perte d'un îlot ou d'une contreforme d'un pixel à
une tolérance de 0,5 px, puis leur récupération. Ils couvrent aussi les couleurs
adjacentes, les diagonales, les masques denses, les métriques physiques et le
refus avant tracing/rendu d'un masque dépassant les budgets. Le tracé conserve
les coordonnées historiques ; les sommets colinéaires sont retirés.

La [comparaison sur les sept mêmes cas](benchmarks/tracing-fidelity-2026-10-13.json)
retrouve les labels rendus, topologies, commandes, fils, décisions, statistiques,
aperçus de points et octets PES/DST inchangés. Seuls les SVG raster sérialisés
diffèrent ; les SVG vectoriels conservés restent identiques. Aux tolérances
physiques de ces entrées, aucun fallback n'est nécessaire. Le corpus ne prouve
donc pas un gain de couture sur ces logos : il confirme leur stabilité sous les
nouveaux contrôles. Les cas synthétiques à tolérance élevée prouvent le correctif.
Les temps sont des essais unitaires contextualisés, sans conclusion de vitesse.

Les tests de normalisation couvrent RGBA, EXIF, profil sRGB embarqué, LAB TIFF,
PNG indexé avec table alpha, clé de transparence RGB, canal L/A et fallback de
profil invalide ou LittleCMS indisponible. Les couleurs sans profil gardent leur
décodage antérieur. Le diagnostic est disponible dans l'API, le JSON machine et
**Détails**, sans ajouter de panneau. L'analyse reste celle d'une interprétation
pixel/physique ; elle ne mesure pas le rendu sur tissu et ne garantit pas les
entrées photo HDR/16 bits.

## Remplissage : contacts tangents et précision géométrique

Un log de l'API a révélé une exception GEOS lors de l'intersection d'une rangée
avec le contour tourné. L'entrée échouée a été effacée par le nettoyage normal
des jobs incomplets ; cette exception exacte n'a pas été reproduite sur le
corpus synthétique. Une faiblesse indépendante a toutefois été démontrée : un
polygon valide avec une contreforme tangente à son enveloppe peut devenir
invalide après une rotation numérique. Par exemple, enveloppe `(0,0)-(10,8)` et
contreforme `(2,0),(3,2),(2,3),(1,2)` à −30° sur l'environnement de validation.

Le moteur conserve son chemin habituel si la géométrie tournée est valide. Sinon,
ou après une exception GEOS, il découpe les lignes de balayage dans le contour
original valide, puis projette uniquement les segments obtenus. La bascule est
conservée pour les rangées suivantes. Aucun buffer de réparation, remplissage
de trou ou snapping des contours n'est appliqué. Si les deux repères échouent,
une erreur explicite remplace l'exception brute.

Les tests de régression couvrent le contact tangent avec une perturbation
numérique contrôlée, un retry GEOS sur neuf angles et l'échec irréparable. Ils
vérifient l'absence de traversée des trous, la conservation des coordonnées
machine à 0,1 mm et un écart numérique ≤ 10⁻¹² mm sur ces exemples. Ce fallback
renforce la robustesse du découpage ; il ne prouve pas que toutes les causes
d'erreur géométrique sont corrigées.

Le corpus Pepsi, Phénix, Falcon, drapeau et trois contrôles conserve les
commandes, fils, statistiques, aperçu sélectionné et octets PES/DST sur **7/7**
entrées après ce correctif. Les masques et topologies indépendants sont également
inchangés. Sur Falcon, certaines métriques des candidats fill rejetés varient
légèrement (`missing_mm2` 268,16 → 268,18, `spill_mm2` 31,60 → 31,65), ainsi que
des longueurs de saut. La sélection reste identique ; l'égalité n'est pas
revendiquée pour tous les candidats ou leurs diagnostics. Le [rapport borné](benchmarks/fill-topology-2026-10-13.json)
conserve cette distinction.

## Parasites de couleur : image, aperçu et points machine

Le Pepsi fourni révélait deux causes indépendantes : les fondations rouge/bleu
étaient affichées en gris technique, et certaines nuances de bord compressées
recevaient le fil noir distant par proximité Lab globale. L'aperçu utilise
désormais le fil actif pour les sous-couches ; les SVG/PNG statiques suivent les
commandes cousues et n'affichent pas les déplacements aiguille levée.

La correction bitmap utilise seulement des peintures de confiance présentes
dans le voisinage d'une nuance faible. Elle conserve l'alpha, les noyaux opaques,
les vrais détails noirs, les palettes littérales et les peintures SVG. Le nombre
de pixels réattribués est visible dans **Détails → Interprétation du dessin**.
Les règles et leur opt-out sont décrits dans [l'interprétation](INPUT_INTERPRETATION.md#palette-et-parasites-bitmap).

| Pepsi, même taille 80 mm et priorité satin | Avant | Après |
|---|---:|---:|
| Composantes noires interprétées | 53 | 6, liseré et lettres |
| Régions visibles après interprétation | 58 | 11 |
| Pixels de bord réattribués | 0 | 77 |
| Pénétrations noires dans les anciens micro-îlots parasites | 25 | 0 |
| Pénétrations noires à plus de 1 mm du noir réel de la source | 107 | 0 |
| Points machine totaux | 12 594 | 12 459 |
| Coupes planifiées | 174 | 131 |
| Fils | 4 | 4 |
| Couverture structurelle de chaque fil | 100 % | 100 % |

Le second audit inclut **toutes** les phases cousues : surface, sous-couche,
liaisons, ancrages et pénétrations d'entrée. Le rayon de 1 mm est une référence
conservative propre à cette source de faible résolution ; 68 points satin et
une liaison du liseré se trouvent à environ 0,52 mm du noir source sans être des
parasites. Aucun segment cousu n'entre à plus de 0,35 mm dans une autre peinture
interprétée. Ce dernier contrôle, seul, n'aurait pas détecté une erreur en amont
dans la palette : il faut aussi comparer l'interprétation à l'image originale.

La relecture **PES et DST** retrouve exactement les positions des pénétrations,
les segments cousus, leur couleur active et les quatre fils du JSON. Le nombre
de coupes décodées peut différer selon le format, notamment l'heuristique DST
fondée sur les sauts ; aucune égalité de ces commandes n'est revendiquée.

Phénix (2 709 points), Falcon (4 124) et le drapeau (9 483) ont aussi été
régénérés : palettes et commandes inchangées, PES/DST identiques octet par octet,
couverture structurelle de chaque fil à 100 %. Les régressions synthétiques
protègent les yeux, lettres et points noirs opaques, les petits aplats gris,
les transparences, les rotations/reflets et le nettoyage désactivé. Un gris
neutre ambigu reste conservé ; le contexte local ne suffit pas à le supprimer.

Le surcoût de la palette, médiane de trois passages après chauffe, est de
**7 ms** pour Pepsi (436 × 436 px utiles) et **74 ms** pour un aplat synthétique
de 1 800 × 1 800 px. Ces mesures isolent le helper, sans démontrer un gain global
de génération. Les résultats détaillés sont dans le [rapport des parasites](benchmarks/colour-artifacts-2026-10-13.json).

Validation finale : **645 tests Python**, **112 tests frontend**, Ruff,
TypeScript, ESLint et build Next.js de production passent. Le renderer est
testé en light/dark et contraste ; le masquage des fondations ne crée aucune
liaison entre couleurs. Cette validation ne remplace pas un essai sur tissu.

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

## Nettoyage du fond : version 0.5.1

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
