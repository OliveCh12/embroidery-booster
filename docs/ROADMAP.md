# Consolidation du moteur direct

Le moteur produit des plans géométriquement contrôlés, pas une certification du
rendu cousu. Chaque lot compare ses sources à `main` et au lot précédent : mêmes
images, taille physique, tissu, fil, stabilisateur et paramètres machine. Les
contrôles de couche supérieure excluent sous-couche et déplacements ; les PES/DST
sont relus pour vérifier les points réellement exportés.

## Priorités

| Ordre | Travail | Bénéfice attendu | Condition de validation |
|---|---|---|---|
| 1 | Auto guidé par la géométrie : traits, contreformes, courbes et petits détails ronds | Satin utile conservé, moins de tatami choisi par défaut sur des colonnes cousables | Couverture réelle, régularité et symétrie mesurées à plusieurs tailles et positions ; maintien des refus de sécurité |
| 2 | Lisser les rails satin et réduire les jonctions de fragments | Reflets plus continus sur anneaux, courbes et lettrages | Comparer les coutures et excursions hors contour, pas seulement le pourcentage de satin ; aucun manque ni amas supplémentaire |
| 3 | Affiner les accents JPEG et la séparation des peintures | Moins de détails perdus et de fils parasites | Oracles couleur/alpha sur images nettes, compressées et floutées ; préserver les vrais petits accents contrastés |
| 4 | Calibrer les profils textile par des coupons PP1 | Densité, compensation et sous-couche justifiées par la couture | Coupons identiques coton/jersey/éponge, mesures avant/après et photos ; distinguer paramètres proposés et paramètres validés |
| 5 | Tracing haute qualité et fond photographique optionnels | Contours plus lisses et extraction d'objet sur images difficiles | Adaptateurs VTracer/rembg optionnels, audit contre la silhouette/couleurs source, fallback géométrique, temps et mémoire mesurés |
| 6 | Progression structurée de la génération | Comprendre la durée et localiser un échec | Événements backend par étape, état de tâche borné, polling frontend ; conserver le parcours actuel |

L'ordre n'implique pas qu'un futur adaptateur résout toutes les images. VTracer
ne remplace pas la séparation des couleurs ; une suppression de fond apprise
peut retirer une zone blanche intentionnelle. Ces composants ne sont pas encore
intégrés et ne deviennent pas des dépendances obligatoires.

## Déjà disponible

Le premier lot est livré en **0.6.3** : profils géométriques explicites, essai
satin élargi sur traits/contreformes étroits, comparaison de fidélité au tatami
et protection des petits détails arrondis déjà qualifiés. Il ne crée pas encore
des rails continus optimaux sur tous les anneaux ou toutes les jonctions.

- Import SVG et bitmap, normalisation EXIF/ICC, fond uniforme ou dégradé connecté
  au périmètre, nettoyage couleur local et contrôle du tracing.
- Protection des contreformes et accents source, diagnostics des détails non
  résolus ; la version 0.6.2 réduit le coût d'interprétation sans en changer le résultat.
- Satin, tatami et point droit, sous-couche/compensation bornées, décisions
  communes aux formes équivalentes, contrôle après quantification machine.
- Comparaison de variantes sur une interprétation commune, preview à l'échelle
  du cadre, lecture des points/couleurs et diagnostics dans Détails.

Le playback décrit le plan terminé. Il ne constitue pas encore une progression
temps réel de la génération. Les profils textile sont des propositions
conservatrices ; aucun coupon physique PP1 n'a encore été validé dans ce projet.

Les principaux points de branchement restent `stitching/rails.py` et
`satin_geometry.py` pour les rails, `interpretation/paint_reference.py` et
`colors.py` pour les détails couleur, puis `interpretation/tracing.py` et
`background.py` pour les adaptateurs optionnels. Le tracing actuel reste le
fallback audité. Tout nouveau modèle doit expliciter sa licence, sa mémoire,
ses téléchargements et ses erreurs ; aucun téléchargement de modèle n'est
déclenché par l'import ordinaire. Le suivi de tâches devra être exposé par
`web/app.py` puis affiché dans le flux TanStack Query existant.

## Règle pour Auto

Mélanger satin et tatami est utile **entre régions** : liseré satin étroit autour
d'une surface tatami, par exemple. Une même région connectée garde une seule
stratégie de surface ; un satin incomplet n'est pas réparé par des îlots tatami.
Un anneau et un disque plein demandent des raisonnements différents : un satin
radial convergeant au centre d'un disque peut concentrer les pénétrations.

Ces choix suivent les principes de [satin pour les formes étroites et bordures](https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Stitches/stitch_basics/Satin_fills.htm),
de [raccourcissement dans les courbes serrées](https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Editing/edit_advanced/Apply_stitch_shortening.htm)
et de [remplissages radiaux](https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Stitches/stitch_effects/Radial_fills.htm).
Ils servent de références de digitisation ; le projet utilise exclusivement son
moteur direct.

Les résultats et limites observés restent dans [QUALITY_REPORT.md](QUALITY_REPORT.md).
