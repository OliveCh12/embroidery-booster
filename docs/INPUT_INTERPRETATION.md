# Interprétation du fond et stratégie de couture

## Fond extérieur, peinture intérieure et transparence

Le fond n'est pas une couleur à effacer partout. Un badge blanc fermé peut être
une vraie partie du logo, même si son extérieur est également blanc. L'algorithme
part de la couleur dominante du périmètre, puis propage uniquement dans les
pixels compatibles reliés à ce périmètre. Les zones enfermées restent peintes.
La [propagation sous masque de SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.binary_propagation.html)
permet ce traitement sans reconnaissance de marque ni service externe.

| Réglage | Bitmap | SVG |
|---|---|---|
| Auto | Respecte un périmètre déjà transparent ; sinon retire le fond si au moins 85 % du bord visible concorde | Conserve les peintures vectorielles explicites |
| Keep / Conserver | Conserve tous les pixels opaques, même le canvas | Conserve les peintures |
| Remove / Retirer | Essaie la couleur dominante connectée au bord, même si le bord est ambigu | Rasterise, retire le fond connecté et retrace en conservant l'échelle physique |

La tolérance dépend des variations mesurées sur le bord, avec un minimum de
2 unités de distance RGB : un extérieur blanc uniforme ne doit pas absorber un logo gris
très pâle. Le fond utilise huit voisins, complémentaires des quatre voisins des
régions peintes. Une ouverture diagonale reste donc une ouverture. Retirer est
un choix explicite de l'utilisateur, pas une segmentation sémantique d'une photo.
Une bordure volontaire peut ressembler à un fond ; Conserver est prévu pour ce cas.

Les trous alpha restent des trous. À l'inverse, un blanc opaque enfermé est une
couleur à broder. En monochrome sans seuil, toutes les peintures visibles forment
la silhouette. Un seuil ou une inversion explicite utilise l'interprétation
manuelle de luminance et est signalé comme tel.

## Palette et parasites bitmap

Une compression ou un redimensionnement produit des nuances de bord qui ne
doivent pas devenir chacune un fil. La consolidation des logos plats est activée
seulement si les couleurs dominantes et leurs voisins proches représentent au
moins 85 % des pixels visibles. Les noyaux de couleurs plates, accents contrastés
et palettes exactes restent distincts. Photos et dégradés conservent la
quantification bornée habituelle. Ce choix peut modifier des nuances fines :
désactiver `raster_cleanup` conserve l'interprétation de palette antérieure.

Après quantification, seuls les îlots **≤ 0,10 mm²**, de dimension **≤ 0,5 mm**, qui
touchent une région stable de couleur proche (**ΔE Lab ≤ 18**) peuvent être
réaffectés. Les voisins sont évalués dans l'image initiale, sans cascade de
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
- **Satin** exige du satin partout. Une surface trop large, branchée ou dont les
  rails échouent à couvrir proprement provoque une erreur claire. Aucun patch fill,
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
