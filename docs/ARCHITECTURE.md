# Architecture

La version 0.4 utilise un seul moteur direct. `generate()` prépare l'entrée,
applique la taille demandée et publie les fichiers après réussite des exports.
La classification, les rails internes, les points et les contrôles machine
appartiennent au package `stitching/`.

```text
src/embroidery_rungs/
  pipeline.py              API generate(), préparation et publication des résultats
  inputs.py                Tracé bitmap, formats acceptés et taille physique
  svg_manager.py           Validation SVG et transformations physiques
  colors.py                Fond bitmap, palette déterministe et régions visibles
  image_processor.py       Rendu borné, axe médian et branches du squelette
  geometry_utils.py        Opérations géométriques partagées
  routing.py               Routage des chemins géométriques
  cli.py                   Commande embroidery-rungs
  stitching/
    params.py              Paramètres physiques et presets tissu/fil/machine
    analysis.py            Analyse des régions et ajustements bornés
    regions.py             Repères locaux et équivalences géométriques
    rails.py               Colonnes internes issues de l'axe médian
    selection.py           Candidats satin/running/tatami et angle surfacique
    consistency.py         Politique commune aux homologues, audit machine final
    paths.py               Échantillonnage des points supérieurs
    underlay.py            Fondations en retrait et soutien du satin
    planner.py             Trajets, verrouillages, coupes et grille de 0,1 mm
    digitizer.py           Couleurs, plans régionaux et changements de fil
    quality.py             Couverture des vrais points supérieurs et crowding
    export.py              PES/DST, JSON schema 3 et previews
  web/app.py               API Flask et jobs isolés
frontend/
  src/app/                 Routes Next.js, thème et styles HeroUI
  src/components/layout/   Header, footer et menu des thèmes
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

1. Valider les réglages et le fichier ; tracer le bitmap si nécessaire.
2. Appliquer le redimensionnement explicite et charger le SVG sécurisé.
3. Borner les réglages physiques, puis rendre les couleurs visibles à 305 DPI,
   sous le budget mémoire du renderer.
4. Séparer les couleurs et leurs composantes connexes ; établir des repères
   locaux canoniques pour les translations, rotations et réflexions pertinentes.
5. Extraire les rails, comparer les candidats et appliquer une politique commune
   aux régions équivalentes. Chaque contour source reste intact.
6. Construire sous-couches et points, retrouver les coordonnées du dessin,
   quantifier une seule fois sur une grille commune et vérifier la couverture.
7. Assembler les couleurs, encoder PES/DST et écrire previews/JSON en staging.
   Publier les fichiers seulement après réussite de la génération.

Le pipeline ne calcule aucun squelette legacy à 150 DPI. Les rails servent
uniquement à construire et vérifier les points directs ; ils ne constituent
plus un export séparé. Les programmes externes et leur découverte ont été retirés.

## Contrats et responsabilités

`GenerationParams` décrit l'interprétation de l'entrée : largeur physique,
ajustement au cadre, seuil et inversion bitmap. `StitchParams` décrit la couture.
Le moteur conserve les valeurs demandées et expose les valeurs effectives avec
chaque ajustement. La sélection du type est automatique ; désactiver
`auto_adjust` conserve les réglages explicites sans contourner les contrôles
physiques et géométriques.

`GenerationResult` contient `input_path`, `original_path`, `direct`,
`artwork_size_mm`, `params`, `warnings` et `timings`. `direct` est obligatoire ;
`original_path` désigne le SVG interprété, pas une copie systématique de l'entrée.
Le résultat direct rassemble fichiers, métriques, décisions, palette, paramètres
effectifs/demandés, ajustements et analyse. Le JSON schema 3 ajoute les commandes
et les plages nécessaires à la lecture de couture.

Les composants front ne calculent pas de points et ne redéfinissent pas les
presets. Next.js relaie l'API Python sur la même origine. Flask valide les
réglages, borne les uploads/jobs, produit un répertoire UUID et sert les fichiers.
Les previews SVG sont proposées au téléchargement ; les aperçus de fichiers
importés sont rendus en PNG.

## Validation

Les tests vérifient les transformations, homologues, trous intentionnels,
longueurs, connexion des régions, couleurs et coordonnées réimportées depuis
PES/DST. L'audit de couverture exclut sous-couches, verrouillages et trajets.
Le [rapport courant](QUALITY_REPORT.md) décrit les résultats mesurés ;
`docs/benchmarks/` conserve les mesures directes historiques identifiées.
Le [protocole de couture](SEWOUT.md) reste nécessaire pour qualifier un rendu
physique : la simulation lit les commandes sans modéliser le tissu.
