# Organisation du projet

`generate()` reste le point d'entrée commun. Préparation des fichiers et géométrie
ne sont calculées qu'une fois ; les exports Ink/Stitch et directs partagent ces résultats.

```text
src/embroidery_rungs/
  inputs.py                Conversion bitmap et taille physique
  external.py              Découverte / appels bornés des outils optionnels
  pipeline.py              Orchestration, résultats et publication des fichiers
  svg_manager.py           Lecture, transformations, rendu et SVG Ink/Stitch
  image_processor.py       Masque, MAT, branches et topologie
  geometry_utils.py        Opérations géométriques partagées
  rung_generator.py        Rails et directions de satin
  optimizer.py             Raffinement local des guides
  routing.py               Ordre des régions
  debug_utils.py           Diagnostics visuels
  stitching/
    params.py              Réglages validés et presets tissu/fil
    paths.py               Échantillonnage satin, running, tatami et sous-couches
    planner.py             Connexions, coupes, locks, quantification et invariants
    selection.py           Choix automatique sur les régions source complètes
    quality.py             Empreinte réelle des segments cousus et métriques
    coverage.py            Audit des points exportés et réparation des zones oubliées
    export.py              Plan physique, PES/DST et aperçus
  web/
    app.py                 API Flask, validation des requêtes et fichiers
    services.py            Adaptation web / exports natifs optionnels
  cli.py                   Interface en ligne de commande
frontend/
  src/app/                 Routes Next.js, providers et styles HeroUI
    quality/               Galerie de comparaison des moteurs
  src/components/layout/   Header, footer et menu des thèmes
  src/features/
    embroidery/            Import, réglages, génération et résultats
    quality/               Rapport, métriques et aperçus comparés
  src/lib/                 Client API et formatage partagés
  public/                  Assets statiques de l'application
examples/                  SVG reproductibles ; quality/ contient les cas contrôlés
tests/                     Géométrie, points, formats, entrées, CLI et web
scripts/                   Comparaisons, benchmarks et helpers Ink/Stitch
docs/                      Architecture, décisions et rapports
  benchmarks/              Mesures historiques identifiées
output/                    Fichiers générés et jobs web ; ignorés par Git
notebooks/                 Exemple exploratoire utilisant l'API publique
```

Le moteur direct vit uniquement dans `stitching/`, l'API Flask dans le package
`web/` et l'interface dans `frontend/`. Les anciens lanceurs, réexports Python
et fichiers `requirements.txt` ont été retirés. `generate()` et les deux commandes
`embroidery-rungs` / `embroidery-rungs-web` constituent les entrées publiques.
La galerie comparative existe uniquement dans Next.js ; son rapport est un JSON
servi par l'API avec les aperçus associés.

Les dépendances et extras vivent dans `pyproject.toml`, avec résolution dans
`uv.lock`. Le wheel Python embarque la bibliothèque, la CLI et l'API. Le frontend
dispose de son workspace pnpm, de versions exactes et de `pnpm-lock.yaml`.
Next.js 16, React 19, HeroUI 3 et Tailwind 4 portent l'interface ; TanStack Query
gère capacités, génération et rapport. `next-themes` applique les modes clair,
sombre et système sans duplication des styles HeroUI.

`pnpm dev` lance les deux processus locaux avec arrêt coordonné. Next.js expose
`/api/*` et `/quality-assets/*` via des rewrites vers l'API Python ; le navigateur
utilise une seule origine. Aucun calcul de broderie ne migre côté frontend.
Les presets physiques sont fournis par le serveur pour garder une seule
définition des densités et compensations. La page `/quality` consomme directement
les artefacts reproductibles produits par `scripts/compare_quality.py`.

Les composants HeroUI assurent formulaires, onglets, cartes et menus. Les seules
compositions applicatives correspondent au parcours métier : import d'un dessin,
choix du matériau et inspection des résultats. Les réglages avancés et diagnostics
restent repliés. Le shell partagé contient header, main et footer ; les pages
commencent par leur contenu utile.

Les artefacts volumineux, rendus, exports de test et jobs restent dans `output/`.
Les JSON de mesure publiés dans `docs/` sont des instantanés explicites,
reproductibles avec `scripts/compare_quality.py` et `scripts/benchmark.py`.
