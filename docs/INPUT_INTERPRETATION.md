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
