# Architecture

La version 0.6 utilise un seul moteur direct. `generate()` prépare l'entrée,
applique la taille demandée et publie les fichiers après réussite des exports.
La classification, les rails internes, les points et les contrôles machine
appartiennent au package `stitching/`.

```text
src/embroidery_rungs/
  pipeline.py              API generate(), préparation et publication des résultats
  inputs.py                Tracé bitmap, formats acceptés et taille physique
  interpretation/
    types.py               Masques immuables, palette et repère physique du bitmap
    normalize.py           Orientation EXIF et profils ICC vers sRGB, alpha conservé
    paint_reference.py     Noyaux source opaques, palette estimée bornée et comptage
    sampling.py            Réduction bornée, contrôle des détails source et adaptation
    tracing.py             Sérialisation commune et fallback vers contours exacts
    audit.py               Fidélité catégorielle, topologie et distances de contours
  svg_manager.py           Validation SVG et transformations physiques
  background.py            Fond connecté, gradients doux et affinage des contours
  colors.py                Palette déterministe et régions visibles
  image_processor.py       Rendu borné, axe médian et branches du squelette
  geometry_utils.py        Opérations géométriques partagées
  routing.py               Routage des chemins géométriques
  cli.py                   Commande embroidery-rungs
  stitching/
    params.py              Paramètres physiques et presets tissu/fil/machine
    analysis.py            Analyse des régions et ajustements bornés
    regions.py             Repères locaux et équivalences géométriques
    rails.py               Colonnes internes issues de l'axe médian
    satin_geometry.py      Rubans directionnels, branches et contreformes
    selection.py           Candidats satin/running/tatami et angle surfacique
    consistency.py         Politique commune aux homologues, audit machine final
    paths.py               Échantillonnage des points supérieurs
    underlay.py            Fondations en retrait et soutien du satin
    planner.py             Trajets, verrouillages, coupes et grille de 0,1 mm
    digitizer.py           Couleurs, plans régionaux et changements de fil
    variants.py            Comparaison bornée et recommandation de stratégies auditées
    quality.py             Couverture des vrais points supérieurs et crowding
    export.py              PES/DST, JSON schema 3 et previews
  web/app.py               API Flask et jobs isolés
frontend/
  src/app/                 Routes Next.js, thème et styles HeroUI
  src/components/layout/   Header et menu des thèmes
  src/features/embroidery/ Import, réglages, résultats et lecture des points
  src/features/quality/    Galerie de validation
  src/lib/                 Client API et fonctions partagées
examples/                  Cas SVG reproductibles et coupon de couture
scripts/                   Développement, validation et benchmarks directs
tests/                    Géométrie, symétrie, points, formats, CLI et API
docs/                     Règles du moteur et protocoles de validation
output/                   Jobs et artefacts générés, ignorés par Git
```

## Flux de génération

1. Valider les réglages et le fichier ; orienter le bitmap et appliquer son
   profil ICC vers sRGB avant de séparer les peintures. Interpréter le fond connecté au bord,
   affiner ses mélanges avec le contour avant tout redimensionnement. Comparer
   la silhouette et les petites palettes littérales avant/après réduction.
   Pour les aplats antialiasés, exploiter des noyaux source opaques et constants
   si leur support est suffisant ; vérifier les couleurs réellement interprétées
   sur chaque grille. Adapter uniquement si les contrôles passent, sinon conserver
   l'adaptation historique de silhouette avec un diagnostic d'incertitude.
   Consolider la palette bitmap et réduire les petits parasites adjacents avant
   le tracé. Auditer les contours sur la grille du contrat immuable ; revenir
   aux contours non simplifiés si des pixels ou des contreformes changent.
   Exposer chaque modification dans `input_analysis`.
2. Appliquer le redimensionnement explicite et charger le SVG sécurisé.
3. Borner les réglages physiques, puis rendre les couleurs visibles à 305 DPI,
   sous le budget mémoire du renderer.
4. Séparer les couleurs et leurs composantes connexes ; établir des repères
   locaux canoniques pour les translations, rotations et réflexions pertinentes.
5. Extraire les rails, comparer les candidats et appliquer une politique commune
   aux régions équivalentes et aux couleurs dominées par le fill. Un mode forcé
   remplace la sélection automatique sans contourner les contrôles satin.
   Chaque contour du SVG interprété reste intact.
6. Construire sous-couches et points, retrouver les coordonnées du dessin,
   quantifier une seule fois sur une grille commune et vérifier la couverture.
7. Assembler les couleurs, encoder PES/DST et écrire previews/JSON en staging.
   Publier les fichiers seulement après réussite de la génération.

Avec `compare_strategies=True`, la préparation d'image et de palette est commune
aux propositions équilibrée, priorité satin, tout satin, tatami uniforme et
contours au point droit. Les repères canoniques, contours, décompositions
directionnelles et axes médians réutilisables sont mis en cache uniquement
pour cette génération. Chaque proposition construit et audite son propre plan ;
aucun plan mutable n'est partagé. `variants.py` classe les diagnostics avant les
préférences de texture, conserve le choix équilibré à égalité et déduplique les
commandes machine identiques. Le résultat principal pointe vers la recommandation,
les alternatives conservent leurs propres fichiers et diagnostics. Un mode forcé
ne déclenche pas de comparaison.
Au-delà de 256 régions visibles, seule la proposition équilibrée est calculée
et les quatre alternatives non calculées sont signalées. Ce budget opérationnel
borne la répétition des audits ; il ne modifie ni l'image ni les limites machine.

Le visualisateur choisit une proposition sans requête de génération supplémentaire.
Cette sélection change ensemble les commandes, la liste de fils, les contrôles et
les liens PES/DST. Le dessin interprété reste commun. Les explications détaillées
restent dans le panneau Détails ; le sélecteur principal est compact.

Le pipeline ne calcule aucun squelette legacy à 150 DPI. Les rails servent
uniquement à construire et vérifier les points directs ; ils ne constituent
plus un export séparé. Les programmes externes et leur découverte ont été retirés.

## Contrats et responsabilités

`interpretation.RasterArtwork` fige les labels et leur palette après nettoyage,
avant sérialisation SVG. Les labels sont copiés sur un buffer non modifiable,
avec zéro pour le transparent et les centres de pixels aux indices entiers.
Le padding et les coordonnées historiques restent inchangés. La conversion
pixels→mm utilise le canvas interprété ; `input_analysis.geometry` distingue
ce canvas des bornes et de la taille visibles, et conserve le rectangle source
recadré après orientation EXIF. Le rapport est ajusté à la taille finale par
`complete_input_analysis`, sans changer le dessin ni les décisions de couture.
Ce contrat interne prépare les adapters de tracing ; il ne remplace pas encore
la rasterisation commune du digitizer.

`GenerationParams` décrit l'interprétation de l'entrée : largeur physique,
ajustement au cadre, seuil et inversion bitmap, `background_mode` et
`raster_cleanup`. `StitchParams` décrit la couture, dont `stitch_type`.
Le moteur conserve les valeurs demandées et expose les valeurs effectives avec
chaque ajustement. La sélection du type est automatique par défaut ; désactiver
`auto_adjust` conserve les réglages explicites sans contourner les contrôles
physiques et géométriques.

`GenerationResult` contient `input_path`, `original_path`, `direct`,
`artwork_size_mm`, `params`, `warnings`, `timings` et `input_analysis`. `direct` est obligatoire ;
`original_path` désigne le SVG interprété, pas une copie systématique de l'entrée.
Le résultat direct rassemble fichiers, métriques, décisions, palette, paramètres
effectifs/demandés, ajustements et analyse. Le JSON schema 3 ajoute les commandes
et les plages nécessaires à la lecture de couture, y compris liaisons cousues
et ancrages. `analysis.stitch_breakdown` compte chaque pénétration une seule fois.

Les composants front ne calculent pas de points et ne redéfinissent pas les
presets. Next.js relaie l'API Python sur la même origine. Flask valide les
réglages, borne les uploads/jobs, produit un répertoire UUID et sert les fichiers.
Les previews SVG sont proposées au téléchargement ; les aperçus de fichiers
importés sont rendus en PNG.

Le shell se limite au header et au main, sans footer. La route `/settings`
mémorise quatre préférences locales versionnées : machine, tissu, titrage et
stabilisateur. Le parseur valide les identifiants et ignore les champs obsolètes.
Le stockage est lu après hydratation via `useSyncExternalStore` ; à l'ouverture
de l'atelier, les recommandations machine et matière de l'API sont appliquées
une seule fois. Une modification utilisateur garde la priorité sur cette
initialisation. Aucun dessin, résultat ou réglage avancé n'est persisté.

`input_quality.py` sépare l’échantillonnage de la source des audits de couverture
du moteur. `inputs.py` conserve les dimensions avant réduction, après recadrage
et sur la grille de travail ; le pipeline complète le rapport avec la taille
physique finale. L’API `/api/analyze` et `/api/convert` partagent le parseur de
réglages et la préparation d’image, sans lancer le digitizer pendant l’analyse.
Les uploads d’analyse restent dans un répertoire temporaire supprimé à la fin.
Le front limite les demandes aux changements d’interprétation et de taille ;
chaque sélection de fichier a sa propre révision, indépendante du nom du fichier.

Le modèle du lecteur dérive chaque passage des commandes `COLOR_CHANGE`, avec
plage de curseur, compte exact des points et temps cumulés de cycles d'aiguille.
La liste des fils et les modes de lecture partagent ces limites ; aucun
changement de bobine ne peut être déduit d'une simple différence de HEX.
Le titrage global vient des paramètres du JSON, sans valeur inventée pour
les anciens plans. La palette de contraste du Canvas ne modifie jamais les
couleurs des fils ni les commandes machine. Le poids du fil et les pauses
de lecture restent distincts du calcul de couture côté Python.

Le lecteur expose une seule commande Lire/Pause et un mode Continu/Par fil.
Continu à ×150 est le défaut. Le bouton flottant Fil/Fils ouvre une liste compacte
avec heures de passage et comptes de points ; elle ne réserve aucune colonne du
visualisateur. Les panneaux et les barres de commandes utilisent des séparateurs,
sans card autour de l'aperçu. Seul le cadre physique est peint, avec ses graduations
depuis 0 jusqu'à sa dimension exacte ; l'extérieur du canvas reste transparent.
Le canvas résout les tokens HeroUI après l'application de la classe de thème.
Les couleurs réelles sont le défaut. Le mode Contraste dérive une palette de
lecture pour les couleurs peu visibles, sans modifier le modèle ou les exports.
Ce choix est conservé entre variantes ; la liste affiche toujours les vrais fils.
Les réglages utilisent cinq sections
Accordion avec icônes. La validation rouvre la section et le panneau mobile
avant la focalisation native d'un champ invalide.
La timeline garde les commandes exactes et les interactions clavier React Aria,
avec une présentation compacte. Les diagnostics restent dans le composant
résultat, accessibles dans un Drawer HeroUI à droite, fermé par défaut ; les
événements de son portail sont isolés de la zone d'import.

`background.py` modifie l'alpha extérieur et conserve les RGB par défaut.
La préparation couleur active aussi la récupération des peintures contaminées
par le fond sur une bande de 3 pixels du contour final, si le nettoyage bitmap
est activé. Ni les trous alpha ni leurs RGB cachés ne sont modifiés. L'ancien
import `colors.bitmap_foreground` reste disponible comme réexport. L'extraction
précède la quantification, afin qu'un halo ne devienne pas un fil blanc.
Les diagnostics du modèle, de l'affinage et de la récupération sont additifs
au JSON existant. Les calculs de distance et de RGB utilisent des tuiles de
512 pixels avec contexte ; la propagation extérieure reste globale.

## Validation

Les tests vérifient les transformations, homologues, trous intentionnels,
longueurs, connexion des régions, couleurs et coordonnées réimportées depuis
PES/DST. L'audit de couverture exclut sous-couches, verrouillages et trajets.
Le [rapport courant](QUALITY_REPORT.md) décrit les résultats mesurés ;
`docs/benchmarks/` conserve les mesures directes historiques identifiées.
Chaque nouveau lot compare son résultat à la référence `main` identifiée par
commit, puis au lot précédent. La fidélité des peintures et contreformes, les
commandes/exportations machine, le temps de préparation et le pic RSS sont
rapportés séparément. Une amélioration de diagnostic ou un XML réorganisé n'est
pas assimilé à un gain de couture. Les mesures de performance excluent le rendu
indépendant ajouté par le benchmark ; elles restent contextualisées par la
machine, les versions, les paramètres et les empreintes source.
Le [protocole de couture](SEWOUT.md) reste nécessaire pour qualifier un rendu
physique : la simulation lit les commandes sans modéliser le tissu.
