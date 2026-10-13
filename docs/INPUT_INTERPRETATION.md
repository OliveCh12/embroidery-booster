# Interprétation du fond et stratégie de couture

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

Après quantification, seuls les îlots **≤ 0,10 mm²**, de dimension **≤ 0,5 mm**, qui
touchent une région stable de couleur proche (**ΔE Lab ≤ 18**) peuvent être
réaffectés. Sur une palette réduite, un fragment peut aussi être corrigé si ses
RGB d'origine démontrent un mélange de peintures stables voisines, plutôt qu'un
noyau de sa propre peinture. `edge_blend_pixels` compte ces corrections. Les voisins sont évalués dans l'image initiale, sans cascade de
fusions. Aucun alpha n'est supprimé, aucune contreforme transparente n'est
remplie, aucun accent isolé n'est effacé. L'aire est calculée à l'échelle finale,
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

Le lecteur distingue couverture, sous-couche grise, liaison ambre, ancrage violet
et saut pointillé. `direct.analysis.stitch_breakdown` compte les pénétrations
exactes par phase, sans doubler les points de contexte partagés entre chemins.
Les sauts restent des déplacements aiguille levée. Masquer une phase dans
l'aperçu ne la supprime pas du PES.

Consulter le [rapport de validation](QUALITY_REPORT.md) pour les mesures et le
[protocole de couture](SEWOUT.md) pour qualifier le résultat sur tissu.
