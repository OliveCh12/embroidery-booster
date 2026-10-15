# Interprétation du fond et stratégie de couture

## Qualité de source et résolution utile

Pour un logo, privilégier le SVG vectoriel d’origine ou un PNG transparent net,
avec des aplats et des contours distincts. Une photo encodée dans un fichier SVG
reste une image raster ; les éléments SVG `<image>` sont refusés par le moteur.
La [documentation Wilcom sur les entrées adaptées](https://docs.wilcom.com/embroiderystudio/26/en/OnlineHelp/Automatic/bitmaps/Choosing_suitable_artwork.htm)
recommande les PNG transparents, les aplats et une source détaillée. Ses
[conseils de numérisation](https://docs.wilcom.com/embroiderystudio/28/en/OnlineHelp/Automatic/bitmaps/bitmaps-4.htm)
varient selon le dessin : une illustration simple peut demander moins de pixels
qu’une photo ou de petits détails. Un minimum fixe en pixels ou une métadonnée
DPI ne constitue donc pas une règle fiable pour toutes les broderies.

`input_quality.py` mesure les pixels **du motif après retrait du fond et avant
réduction de la grille**, rapportés aux dimensions physiques finales, y compris
l’ajustement au cadre. Les dimensions source, utiles et de travail sont distinctes.
Une grande marge transparente ne donne pas artificiellement une bonne note à
un petit logo, et un fichier marqué « 1200 dpi » ne bénéficie d’aucun bonus.
La politique de conseil du moteur est :

| Pixels utiles par mm | Retour utilisateur |
|---|---|
| moins de 3 | Source très peu définie à cette taille |
| de 3 à moins de 6 | Source limitée pour des contours fins |
| à partir de 6 | Définition exploitable ; la complexité reste à vérifier |
| cible de 12 | Environ 305 dpi, adaptée à l’échantillonnage de contours fins |

Ces seuils sont indicatifs, sans blocage d’une source simple. À 80 mm, la cible
correspond à environ 960 pixels utiles. Le moteur propose aussi une largeur
compatible avec cette cible quand le fichier est trop petit. Trois pixels
d’échantillonnage d’un détail sont un repère de résolution de l’image, pas une
largeur minimale de point ou une garantie de brodabilité. La résolution n’augmente
ni la densité de couture ni le nombre de sous-couches. Une source peut avoir
été agrandie avant import ; cette analyse ne retrouve pas sa résolution d’origine.

`POST /api/analyze` utilise la même préparation que `generate()`, mais ne calcule
aucun point et ne conserve aucun job. Une analyse simultanée est autorisée,
indépendamment des jobs de génération. L’interface attend 300 ms après une
modification de taille/interprétation pour éviter des requêtes à chaque frappe ;
elle annule les requêtes dépassées et reprend au plus deux fois une réponse
temporaire 503, sans réessayer une erreur d’entrée. Elle ne bloque pas la génération
si le diagnostic est indisponible. Après génération, les détails utilisent exclusivement le rapport
du fichier produit. Le rapport est aussi présent dans la bibliothèque, le CLI JSON
et le plan machine, sous `input_analysis.quality`.

Les nombreuses nuances et les dégradés sont signalés séparément de la résolution.
La palette réduite et les JPEG sont identifiés, sans prétendre reconnaître
sémantiquement le sujet ou mesurer automatiquement le flou. Le nettoyage reste
local et contrôlé. Un accent opaque fin dont la couleur appartient au mélange
de deux aplats est conservé lorsqu’il se trouve à l’intérieur d’un seul aplat,
loin de la limite alpha. Un mélange au contact des deux peintures reste une
transition de bord ; leurs couleurs ailleurs dans le dessin ne suffisent plus
à supprimer un détail. Les palettes JPEG/photos suivent leurs règles existantes.

Le [corpus de diagnostic](benchmarks/source-quality-2026-10-13.json) couvre
résolutions, marges, taille physique, SVG, JPEG et logos réels. Il mesure la qualité
de la source et le temps d’analyse, pas la qualité d’une couture réelle.
Le [comparatif des accents](benchmarks/colour-accent-2026-10-13.json) conserve
la preuve avant/après de la correction des détails fins et la stabilité des
palettes et masques sur les logos de référence.

## Préserver les détails avant la palette

`interpretation/sampling.py` reçoit le RGBA recadré **après** normalisation,
retrait du fond et affinage de son contour, à la taille physique demandée ou
ajustée au cadre. Ce contrôle ne juge donc pas la segmentation du fond.
L'ancien thumbnail Lanczos à 12 pixels/mm reste le premier candidat. S'il
altère un détail significatif, le moteur essaie Lanczos à 24 pixels/mm, puis
le plus proche voisin à 24 pixels/mm pour une petite palette littérale ou estimée
à partir de noyaux fiables.
Au maximum trois grilles distinctes sont proposées, sans agrandir la source et avec une
dimension maximale de 2 048 pixels. Une source déjà assez petite reste inchangée.

Les comparaisons utilisent les composantes peintes en connectivité 4 et les
contreformes en connectivité 8. Les centres cible sont rapportés aux cellules
source : un trou perdu et un nouveau trou ailleurs ne s'annulent pas parce que
leur nombre est identique. Le seuil de pertinence est **0,01 mm²**, soit l'aire
d'un carré de 0,1 mm. C'est une politique de conservation graphique, pas une
largeur brodable. Des poussières cible sous ce seuil détachées d'un corps encore
présent ne suffisent pas à déclencher une adaptation.

Lorsque tous les pixels visibles de la source utilisent au plus `max_colors`
RGB distincts, chaque peinture littérale est auditée séparément. La réduction
doit aussi conserver assez de pixels intérieurs littéraux d'un petit aplat pour
qu'il ne soit pas ensuite confondu avec un mélange de bord par la palette. Les
RGB cachés sous l'alpha ne participent pas à la détection.

Depuis **0.6.1**, `interpretation/paint_reference.py` cherche aussi des noyaux
d'aplats sur les images antialiasées dont la palette n'est pas littérale. Un noyau
est opaque et partage le même RGB avec ses quatre voisins opaques. Le moteur
exige une couverture globale de noyaux d'au moins 50 %, au plus `max_colors`
couleurs de noyaux, puis des composantes d'au moins 0,01 mm² comportant au moins
neuf pixels de noyau. Un RGB identique ailleurs, sans noyau propre suffisamment
soutenu, ne devient pas une référence. Le calcul parcourt la source par tuiles,
sans palette photographique complète ni agrandissement de la source. Ce sont
des indices d'aplats probables, pas une reconnaissance sémantique.

Ce chemin compare les masques source soutenus par ces noyaux aux labels réels
de `bitmap_colors()` sur chaque candidat. Une attribution globale en RGB peut
confondre un mélange rouge/bleu avec un violet éloigné ; elle n'est donc pas
utilisée pour ces peintures estimées. Les essais restent Lanczos 12, Lanczos 24
puis plus proche voisin 24 pixels/mm. Ils n'injectent aucune nouvelle peinture
ni recoloration globale. Une couleur significative de travail sans référence de
noyau est signalée comme non corroborée, sans être effacée : elle peut aussi être
un vrai détail dont la source ne permet pas d'établir un noyau fiable.

Les JPEG à nuances variables, photos et dégradés sans support suffisant restent
au contrôle alpha seul. Leurs couleurs ne sont pas déclarées vérifiées. Les
seuils de noyaux ne sont pas relâchés pour leur inventer une palette. Le nettoyage
désactivé conserve aussi ce comportement antérieur.

Depuis **0.6.5**, une seconde preuve par **familles de couleurs** peut réunir les
îlots RGB d'un même aplat compressé. Elle intervient seulement si aucune preuve
littérale/noyaux exacte n'a réussi. Le catalogue partagé des noyaux est tuilé et
borné ; chaque ancre est un RGB réellement observé avec au moins neuf pixels de
noyau opaque. Les couleurs voisines sont regroupées dans un rayon Lab de 2 autour
d'une ancre fixe, jamais par une chaîne transitive de nuances. Des familles
séparées de moins de 8 en Lab sont refusées. Les pixels source sont attribués
seulement à moins de 8 de l'ancre, avec une marge de 2 sur le second voisin.
Chaque composante conservée exige une aire de 0,01 mm² et neuf pixels de noyau
RGB exact opaque propres ; un accent distant ne lui prête pas son ancre.
Au moins 50 % des pixels visibles doivent être soutenus globalement.

La palette **réellement interprétée** doit avoir une correspondance injective
avec ces familles, limitée à une distance Lab de 8 et à une marge de 2. Deux
nuances de travail proches d'une seule famille restent ambiguës. Les masques
connexes source/contreformes et les couleurs non corroborées sont de nouveau
audités sur les grilles proposées ; seule une tentative entièrement réussie
remplace le choix historique. Cette seconde preuve peut réévaluer les mêmes
grilles et ajoute donc du calcul. Elle n'injecte aucun fil, n'efface aucun accent
et ne recolore pas l'entrée. Un échec garde les résultats et l'audit ancien,
avec un résumé distinct `paint_family_retry` des grilles essayées, du minimum
d'écarts mesurés et de la palette estimée. Détails signale ce refus même lorsque
l'audit alpha historique réussit : la silhouette seule ne certifie pas les fils.
Les palettes littérales et les preuves par noyaux exacts déjà réussies restent
inchangées.

`reference=source_alpha_and_paint_families` et `paint_family_reference` exposent
ces règles estimées. Chaque tentative enregistre `palette_match` entre RGB
source et fil de travail. Après nettoyage, `interpreted_palette_match` permet
de calculer `missing_source_paints` sans confondre une faible dérive JPEG avec
un fil disparu. Ces contrôles vérifient présence et topologie des détails,
pas une fidélité photographique intégrale ou la qualité d'une couture réelle.

`input_analysis.resampling` enregistre les grilles source/travail, leur repère
physique incluant le padding historique, le mode choisi, les tentatives et les
composantes perdues, fusionnées, fragmentées ou créées. `passed` et
`unresolved_issues` portent sur les détails au-dessus du seuil. Une différence
de topologie sous le seuil peut donc coexister avec `passed=true`. Les écarts
alpha et couleur peuvent concerner le même détail ; leur somme n'est pas un
nombre de détails distincts. Le rapport reste déterministe, sans durée mesurée.

Si aucun candidat ne passe, le chemin littéral retient celui qui présente le
moins d'écarts avec un avertissement. Pour les noyaux estimés, le fallback
conserve le choix qu'aurait fait l'ancien contrôle **alpha seul** parmi les
candidats Lanczos, avec un avertissement. Il conserve ainsi les contreformes
qui nécessitent la grille 24 pixels/mm, même lorsque la palette reste ambiguë.
Après quantification et nettoyage, `interpreted_palette`
liste les peintures effectivement présentes et `missing_source_paints` signale
les peintures source significatives entièrement absentes. Ce dernier champ
vaut `null` lorsqu'aucune comparaison de palette source n'a été faite. Il ne
vérifie pas la conservation de chaque sous-région d'une même couleur. Pour les
noyaux estimés, la présence est comparée par HEX exact et peut donc aussi
signaler un fil dont la nuance a changé, plutôt qu'une disparition géométrique.
`reference=source_alpha_and_flat_paint_cores` et `flat_paint_reference` précisent
la couverture et les exigences de noyaux ; `baseline_retained` signale un
fallback ambigu. Les tentatives enregistrent les couleurs de travail non
corroborées dans `unverified_working_paints`.
L'API d'analyse, `generate()`, le CLI JSON et Détails utilisent le même rapport.
Les contrôles de tracé puis de points machine restent indépendants : une bonne
réduction ne prouve ni une interprétation parfaite ni une couture qualifiée.

Cette adaptation est automatique, sans nouveau réglage. Les SVG natifs Auto/Keep
et le chemin monochrome, qui conserve déjà sa grille source, sont inchangés.
Le mode SVG Remove utilise le même chemin bitmap couleur. Désactiver le nettoyage
conserve le contrôle alpha et celui des palettes littérales, mais désactive la
recherche des noyaux estimés et le nettoyage en aval.

Depuis **0.6.2**, les primitives de comptage et de comparaison sont accélérées
sans modifier ces règles. L'histogramme RGB utilise des entiers de 24 bits,
qui ont exactement le même ordre lexicographique que les triplets RGB. Les
noyaux comparent les quatre octets RGBA ensemble lorsque la disposition du
tableau autorise une vue sans copie ; les autres dispositions conservent les
comparaisons par canal. Les régions utilisent des histogrammes denses limités
à 65 537 cases, par tuiles de 65 536 pixels, puis le chemin sparse historique
au-delà. Aucun seuil, contrôle de contreforme ou budget d'image n'est réduit.

## Fond extérieur, peinture intérieure et transparence

Le fond n'est pas une couleur à effacer partout. Un badge blanc fermé peut être
une vraie partie du logo, même si son extérieur est également blanc. L'algorithme
estime le fond depuis le périmètre, puis propage uniquement dans les pixels
compatibles reliés à ce périmètre. À ce stade, les zones enfermées restent peintes.
La [propagation sous masque de SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.binary_propagation.html)
permet ce traitement sans reconnaissance de marque ni service externe.

| Réglage | Bitmap | SVG |
|---|---|---|
| Auto | Respecte un périmètre déjà transparent ; sinon essaie un fond uni ou un dégradé doux cohérent | Conserve les peintures vectorielles explicites |
| Keep / Conserver | Conserve tous les pixels opaques, même le canvas | Conserve les peintures |
| Remove / Retirer | Essaie le fond cohérent, ou la couleur dominante connectée au bord si le fond est ambigu | Rasterise, retire le fond connecté et retrace en conservant l'échelle physique |

Trois cas sont distingués : fond constant, champ affine RGB ajusté de façon
robuste, et dégradé non linéaire suivi par petites variations entre voisins.
Un champ affine n'est pas extrapolé aveuglément : les pixels extérieurs observés
doivent être compatibles avec lui. Pour un dégradé radial ou sinusoïdal, le fond
local provient des pixels extérieurs effectivement atteints. Un bord à ruptures
ou texturé est conservé par Auto. Si toute l'image correspond au dégradé et
qu'aucun premier plan distinct ne subsiste, Auto conserve l'image : le dégradé
peut lui-même être le motif à broder. Il n'y a aucune reconnaissance sémantique du
sujet d'une photo ; une bordure volontaire peut ressembler à un fond et doit
alors être conservée explicitement.

La tolérance du fond constant reste étroite (minimum de 2 unités de distance
RGB), afin de garder les peintures pâles. Elle ne suffit pas pour la compression
et l'antialiasing. Une seconde étape affine la bande extérieure de 24 pixels,
en évaluant le mélange `C = alpha * F + (1-alpha) * B` avec des références locales
de peinture et de fond. Les mélanges contenant moins de 50 % de peinture sont
rattachés au fond seulement s'ils sont accessibles depuis l'extérieur. Une
faible valeur négative explique les halos clairs produits par le ringing des
codecs : la projection est testée avant d'être bornée. Les aplats pâles stables
fournissent leurs propres références ; aucune érosion globale du logo n'est
appliquée. Une petite palette de peintures littérales est conservée sans matting :
un accent pâle de quelques pixels ne doit pas être traité comme du ringing.
Les RGB cachés sous la transparence ne participent pas à ce choix.

Les contours fortement contrastés forment une barrière fermée à l'échelle de
l'image entière. Seul son intérieur, avec une marge d'un pixel, est protégé :
protéger toute la bande contrastée conserverait aussi le halo gris extérieur.
Cette protection empêche le matting de traverser un liseré noir fin et
d'effacer le blanc du badge. Les calculs locaux utilisent des tuiles, mais la
fermeture et la propagation restent globales pour conserver la même topologie.

`bitmap_foreground()` conserve les RGB par défaut. La préparation couleur peut
ensuite récupérer la peinture de référence sur les mélanges conservés, dans une
bande de 3 pixels du contour final. C'est nécessaire lorsqu'un noir mélangé au
fond gris serait autrement quantifié en blanc. Le masque ne change pas pendant
cette récupération, et les pixels intérieurs ou transparents sont inchangés.
Désactiver le nettoyage bitmap conserve les RGB originaux avant quantification.

Le fond utilise huit voisins, complémentaires des quatre voisins des régions
peintes. Une ouverture diagonale reste donc une ouverture. Retirer est un choix
explicite de l'utilisateur, pas une suppression de toutes les couleurs du bord.

Les trous alpha restent des trous. Un blanc opaque enfermé est normalement une
couleur à broder. Le tracé couleur peut ensuite inférer des évidements sur un
logo noir/blanc : nettoyage activé, fond réellement retiré, deux peintures dont
la couleur exacte du fond et traits monochromes épais autour du blanc. Les
badges ambigus doivent rester opaques ; cette inférence géométrique est signalée
par `counters_inferred`, `counter_pixels_removed` et `counter_inference`.
Conserver le fond ou désactiver le nettoyage conserve les blancs originaux.
Depuis la 0.6.6, `background.counter_ambiguity` décrit les peintures intérieures
conservées qui correspondent au fond retiré : nombre, pixels, aire sur la grille
de travail et motif géométrique. Détails explique cette incertitude. Un grand
évidement opaque de lettre peut être identique à une peinture blanche de badge :
le moteur n'en déduit pas une intention certaine. Un PNG avec alpha ou un SVG
avec contreforme explicite retire cette ambiguïté sans effacer les vrais blancs.
Le retrait explicite d'un SVG n'applique pas cette inférence. En monochrome sans seuil, toutes les peintures visibles forment
la silhouette. Un seuil ou une inversion explicite utilise l'interprétation
manuelle de luminance et est signalé comme tel.

Le tracé conserve une silhouette alpha commune, peinte avec la couleur dominante
de ses contours, puis superpose les autres régions. Cela évite les fissures
transparentes créées par l'antialiasing de chemins de couleur indépendants,
sans remplir les trous alpha intentionnels ni ajouter de couleur de fil.
Le SVG bitmap utilise `crispEdges` pour le rendu de ces masques catégoriels :
recalculer un antialiasing après la palette créerait des îlots de couleurs
intermédiaires et pourrait casser un liseré satin fin. Les SVG vectoriels natifs
gardent leurs propriétés de rendu.

Les diagnostics distinguent `model` (`uniform` / `smooth_gradient`), `model_fit`,
`border_error_rgb` (erreur p95 du modèle au bord, absente pour une propagation
locale), `gradient_step_rgb`, `edge_refined_pixels` et `edge_recovered_pixels`.
Un score de compatibilité
du bord ne prouve pas une segmentation sémantique correcte.

Ce choix utilise les dépendances NumPy/SciPy existantes. [GrabCut](https://docs.opencv.org/4.13.0/d8/d83/tutorial_py_grabcut.html)
prévoit un rectangle ou des marqueurs de premier plan/fond, avec retouches
possibles. [rembg](https://github.com/danielgatis/rembg) propose des modèles de
segmentation et de matting ; leurs masques de sujets ne constituent pas une
garantie de conservation des peintures et contreformes d'un logo. Ils ne sont
pas ajoutés au moteur par défaut.

## Palette et parasites bitmap

Une compression ou un redimensionnement produit des nuances de bord qui ne
doivent pas devenir chacune un fil. La consolidation des logos plats est activée
seulement si les couleurs dominantes et leurs voisins proches représentent au
moins 85 % des pixels visibles, après inclusion des petits noyaux plats. Les noyaux de couleurs plates, accents contrastés
et palettes exactes restent distincts. Photos et dégradés conservent la
quantification bornée habituelle. Ce choix peut modifier des nuances fines :
désactiver `raster_cleanup` conserve l'interprétation de palette antérieure.

La proximité Lab globale ne suffit pas pour les bords : une nuance bleu/gris
compressée peut être plus proche du noir des lettres que du bleu et du blanc
voisins. Sur les aplats récupérés uniquement, les pixels éloignés de leur fil
assigné (**ΔE > 14**) sont réaffectés si ce fil n'a aucun pixel de confiance
(**ΔE ≤ 10**) dans un rayon de six pixels source et si au moins deux autres
peintures ont un support local. La nouvelle attribution choisit seulement parmi
ces voisins. Les pixels noirs ou gris neutres associés au noir restent protégés.
Cette règle n'efface pas de composante, ne change ni RGB ni alpha, ne touche pas
les palettes littérales/SVG ni les photos, et reste désactivable avec le nettoyage.
`palette_edge_pixels` compte les réaffectations dans les diagnostics.

### Représentants de couleur sur masques fixes

La 0.6.6 ajoute une correction bornée des moyennes median-cut sur les bitmaps
texturés. Elle est appliquée **après** les nettoyages et les inférences de trous,
avec nettoyage activé, palette réduite, récupération d'aplats non retenue et
référence `source_alpha` ou `source_unchanged`. Les peintures littérales et les
preuves par noyaux/familles déjà qualifiées gardent leur interprétation.

Pour chaque label, le candidat est son mode RGB réellement observé, avec au moins
neuf noyaux opaques égaux à leurs quatre voisins. Son déplacement doit atteindre
ΔE 3, et il doit rester plus proche de son ancien fil que des autres. Sur tous
les pixels visibles du masque, il doit réduire l'écart Lab moyen d'au moins
20 %, sans augmenter p95 ni somme des carrés. L'ensemble de la palette doit
rester injectif et séparé d'au moins ΔE 8. Sinon la couleur précédente reste.
Ces seuils sont des règles de fidélité graphique, pas un étalonnage de fils réels.

Les calculs utilisent les histogrammes RGB exacts de la grille de travail, sans
stride ni moyenne de pixels voisins ; Lab est converti par lots de 100 000 valeurs.
`cleanup.palette_refinement` enregistre candidats, refus, métriques et changements
`from`/`to`. **Les labels, l'alpha et les contours ne changent pas.** Cette voie
peut corriger une teinte brunie sans fragmenter le dessin, mais ne supprime pas
la texture et ne rétablit pas un accent absent de la segmentation.

L'affectation Lab des RGB identiques est réutilisée lorsque le nombre de valeurs
distinctes est au plus le quart des pixels. Les images à forte entropie gardent
la voie précédente. Le remapping est également tuilé ; aucune approximation de
couleur n'est introduite par cette optimisation.

### Repère de l'interprétation

Avant le tracé, `RasterArtwork` conserve une copie immuable des labels et de la
palette. Le SVG bitmap garde son padding d'un pixel par côté : la largeur
demandée désigne le document interprété, et sa silhouette visible peut être
plus petite, particulièrement sur les très petites images. Le nouveau rapport
`input_analysis.geometry` expose séparément `canvas_size_mm`,
`visible_bounds_mm`, `visible_size_mm`, `pixel_size_mm` et `source_crop_box_px`.
Le rectangle source est exprimé dans l'image après orientation EXIF ; ses bornes
maximales sont exclusives. Les centres de pixels restent aux indices entiers
dans le repère de contours existant. La taille historique n'est pas modifiée.

### Normalisation et contrôle du tracé

`interpretation/normalize.py` applique l'orientation EXIF, puis convertit un profil
ICC embarqué vers sRGB avec Pillow/LittleCMS avant l'analyse du fond et des
couleurs. Les canaux alpha, tables de transparence des PNG indexés et clés de
transparence sont conservés. Sans profil, le décodage historique est conservé.
Un profil invalide ou un Pillow sans LittleCMS déclenche un fallback signalé,
sans interdire une image encore décodable. Une entrée dans un mode non décodable
sans profil valide produit une erreur claire. Le rapport expose
`input_analysis.normalization` ; aucune dépendance Python supplémentaire n'est
requise.

`interpretation/tracing.py` sérialise les mêmes labels pour les deux chemins
bitmap. Le tracé simplifié est rendu une fois sur leur grille native, pour
contrôler l'alpha et chaque peinture. Un seul pixel modifié suffit à déclencher
une seconde tentative : contours marching squares non simplifiés, avec retrait
des seuls sommets colinéaires. Si ce tracé échoue aussi au contrôle, la conversion
est refusée au lieu de publier une interprétation silencieusement dégradée.
Les compteurs utilisent une connectivité 4 pour les régions peintes et 8 pour
les contreformes. Les peintures catégorielles monochromes adoptent aussi
`crispEdges`, comme le chemin multicolore, pour éviter un nouvel antialiasing.

`input_analysis.tracing` conserve les audits `initial` et `final`, le fallback,
la tolérance effective, le nombre de rendus, les pixels modifiés, les distances
de contour (p95/max), la topologie par couleur, le nombre de nœuds et les octets
SVG. Le SVG émis garde son viewBox historique ; seule la copie d'audit est
échantillonnée aux centres entiers (`viewBox=-0.5 -0.5 width height`). Les métriques
en mm se rapportent à `tracing.initial/final.canvas_size_mm` et `pixel_size_mm`
au moment du tracé ; `geometry` décrit séparément la taille finale du document.
Les deux snapshots peuvent partager la même référence mémoire avant export JSON.

Ce contrôle garantit les labels **interprétés après palette/nettoyage**, pas
l'identité à tous les pixels du fichier d'origine. Il ne prouve ni une aire
vectorielle identique à celle des cellules raster, ni la brodabilité d'un détail
à la résolution machine : les audits de points restent nécessaires. Un SVG de
plus de 10 MiB ou une grille d'audit de plus de 16,1 MP / 16 384 pixels par côté
est refusé avant le rendu. Le coût est d'un à deux rendus pour le dessin complet,
sans rendu indépendant par région.
Une limite de 8 192 contours par masque (régions peintes et contreformes) est
vérifiée avant marching squares ; une seule région percée de milliers de trous
ne peut plus contourner le budget par son faible nombre de composantes.

Un logo presque noir avec alpha explicite peut conserver un gris de matting sur
son bord. Le nettoyage récupère cette frange seulement si au moins 97 % du dessin
est sombre, son noyau varie peu, aucun accent chromatique n'existe, et tous les
gris concernés sont partiellement transparents à moins de trois pixels du bord
alpha. Les palettes exactes, gris opaques, gris intérieurs et photos ombrées
restent inchangés. `dark_ink_edge_pixels` compte les pixels normalisés ; le masque
ne change pas. Cette règle évite de créer des fils gris pour un simple contour
noir antialiasé, sans imposer le monochrome aux peintures vectorielles.

Après quantification, seuls les îlots **≤ 0,10 mm²**, de dimension **≤ 0,5 mm**, qui
touchent une région stable de couleur proche (**ΔE Lab ≤ 18**) peuvent être
réaffectés. Sur une palette réduite, un fragment peut aussi être corrigé si ses
RGB d'origine démontrent un mélange de peintures stables voisines, plutôt qu'un
noyau de sa propre peinture. `edge_blend_pixels` compte ces corrections. Les voisins sont évalués dans l'image initiale, sans cascade de
fusions. Aucune contreforme transparente n'est remplie, aucun accent opaque ou
isolé n'est effacé. Un nettoyage supplémentaire peut retirer un fragment alpha
partiel de quatre pixels maximum, ≤ 0,02 mm² et ≤ 0,25 mm, uniquement s'il touche
en huit-connectivité une grande région de la même peinture et ne contient aucun
pixel alpha ≥ 224. Les SVG explicites n'utilisent pas cette règle.
`alpha_fragments_removed` et `alpha_fragment_pixels` la signalent séparément.
L'aire est calculée à l'échelle finale,
y compris l'ajustement au cadre : une demande surdimensionnée ne change pas la
décision de nettoyage pour un même résultat physique. Ces seuils limitent les modifications sous l'aire d'une maille
de tatami typique de 0,4 × 0,4 mm ; ils ne sont pas une mesure de perceptibilité.

`GenerationResult.input_analysis` et le JSON machine enregistrent le fond,
l'aire modifiée et le nombre de régions avant/après. Le SVG interprété constitue
la référence des audits : une bonne couverture ne prouve pas que toute nuance du
bitmap d'origine a été conservée.

## Auto et types imposés

- **Auto** analyse largeur, géométrie, trous et couverture sur la grille machine.
  Le satin convient aux colonnes ; le tatami couvre les surfaces larges. Si le
  fill couvre au moins 70 % de l'aire des régions substantielles d'une couleur,
  les compagnons compacts pleins sont également remplis. Les colonnes étroites,
  lettres courbes, contreformes et petits détails ne sont pas convertis pour
  satisfaire cette règle d'homogénéité. Les homologues géométriques partagent leur
  stratégie et les vérifications finales.
  Un balayage satin sûr mais moins fidèle ne bloque plus les directions
  suivantes. Les traits et contreformes étroits peuvent ensuite être comparés
  au tatami final, après sa politique d'angle/sous-couche. L'adoption concerne
  toute la cohorte, sans plus de commandes ni disparition de fondation ; les
  limites physiques et contrôles de piqûres restent obligatoires. Le profil de
  forme précis est utilisé avant l'arrondi des valeurs affichées, pour éviter
  qu'une différence d'affichage fasse basculer un trait en surface compacte.
  Une seconde vérification compte les piqûres supérieures aux coordonnées
  machine, y compris entre colonnes. Un essai étroit qui crée un pic supérieur
  à `max(2, pic_du_tatami_final)` est écarté ; Détails indique alors la
  concentration entre colonnes. Deux piqûres au raccord peuvent rester utiles.
  Il s'agit d'une règle comparative conservatrice, pas d'une certification du
  tissu. La recommandation automatique des variantes compare également ce pic
  par fil ; couverture et esthétique ne suffisent pas à justifier sa hausse.
- **Satin** exige du satin partout. Les balayages trop larges peuvent être divisés
  en colonnes adjacentes, avec flottées bornées et coutures internes décalées.
  Les régions dont les rails échouent à couvrir proprement ou concentrent les
  piqûres provoquent une erreur claire. Aucun patch fill,
  détail omis ou flottée excessive ne sert à contourner ce choix.
- **Tatami (`fill`)** impose des rangées limitées à chaque région et ses trous,
  sans calcul d'axe médian préalable. Angle automatique commun par couleur quand
  approprié, ou angle global explicitement choisi.
- **Point droit (`running`)** produit contours pour les surfaces larges et axes
  pour les détails fins. C'est une broderie de contours ; une région pleine n'est
  pas présentée comme complètement couverte.

Ces quatre stratégies reposent sur les chemins déjà vérifiés du moteur. Les
remplissages décoratifs supplémentaires ne sont pas introduits sans validation.
La [documentation satin de Hatch](https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Stitches/stitch_basics/Satin_fills.htm)
explique l'intérêt du satin étroit et le risque des longues flottées. Forcer
du satin sur toute surface ne serait pas une amélioration physique fiable.

## Pourquoi certains points repassent

La couche supérieure donne le rendu. Une sous-couche espacée stabilise les
surfaces et le tissu ; elle est utile, même si elle est ensuite recouverte.
Les [fondations tatami décrites par Wilcom](https://docs.wilcom.com/embroiderystudio/26/en/OnlineHelp/Quality/underlays/Tatami_underlay_settings.htm)
emploient une direction croisée et un retrait au bord. Le moteur borne leur
densité et évite les fondations inutiles sur des régions de moins de 4 mm².

Les liaisons cousues joignent les rangées ou régions dans une zone autorisée.
Les ancrages sécurisent le fil avant/après les coupes. Des milliers de petites
îles de couleur multiplient ces opérations : c'est un problème d'interprétation
en amont, pas une raison de supprimer tous les ancrages ou sous-couches.

Le lecteur affiche la sous-couche avec le fil actif et le même diamètre que la
couverture : une fondation rouge ne doit pas apparaître comme du fil noir ou gris.
Les liaisons ambre, ancrages violets et sauts pointillés restent des repères
techniques activables. Les aperçus SVG/PNG statiques dessinent uniquement les
segments réellement cousus, dans la couleur active des commandes machine.
`direct.analysis.stitch_breakdown` compte les pénétrations
exactes par phase, sans doubler les points de contexte partagés entre chemins.
Les sauts restent des déplacements aiguille levée. Masquer une phase dans
l'aperçu ne la supprime pas du PES.

Consulter le [rapport de validation](QUALITY_REPORT.md) pour les mesures et le
[protocole de couture](SEWOUT.md) pour qualifier le résultat sur tissu.
