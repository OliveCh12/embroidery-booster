# Consolidation du moteur direct

Le moteur produit des plans géométriquement contrôlés, pas une certification du
rendu cousu. Chaque lot compare ses sources à `main` et au lot précédent : mêmes
images, taille physique, tissu, fil, stabilisateur et paramètres machine. Les
contrôles de couche supérieure excluent sous-couche et déplacements ; les PES/DST
sont relus pour vérifier les points réellement exportés.

## Priorités

| Ordre | Travail | Bénéfice attendu | Condition de validation |
|---|---|---|---|
| 1 | Nettoyage spatial des peintures et contreformes JPEG | Moins de micro-régions, de blancs parasites et de teintes déplacées sur les logos texturés | Oracles indépendants couleur/alpha ; préserver les vrais accents et les contreformes, ne pas gagner en palette en fragmentant les chemins |
| 2 | Rails de bordures et jonctions pilotés par courbure | Plus de liserés satin et moins de concentrations aux raccords de lettres | Contrôle de toutes les piqûres entre colonnes, contreformes protégées, couverture/débordement comparés au tatami réel ; aucune relaxation de sécurité |
| 3 | Calibrer les profils textile par des coupons PP1 | Densité, compensation et sous-couche justifiées par la couture | Coupons identiques coton/jersey/éponge, mesures avant/après et photos ; distinguer paramètres proposés et paramètres validés |
| 4 | Tracing haute qualité et fond photographique optionnels | Contours plus lisses et extraction d'objet sur images difficiles | Adaptateurs VTracer/rembg optionnels, audit contre la silhouette/couleurs source, fallback géométrique, temps et mémoire mesurés |
| 5 | Progression structurée de la génération | Comprendre la durée et localiser un échec | Événements backend par étape, état de tâche borné, polling frontend ; conserver le parcours actuel |

L'ordre n'implique pas qu'un futur adaptateur résout toutes les images. VTracer
ne remplace pas la séparation des couleurs ; une suppression de fond apprise
peut retirer une zone blanche intentionnelle. Ces composants ne sont pas encore
intégrés et ne deviennent pas des dépendances obligatoires.

## Déjà disponible

Le premier lot est livré en **0.6.3** : profils géométriques explicites, essai
satin élargi sur traits/contreformes étroits, comparaison de fidélité au tatami
et protection des petits détails arrondis déjà qualifiés. Il ne crée pas encore
des rails continus optimaux sur tous les anneaux ou toutes les jonctions.

La **0.6.4** ajoute un candidat satin continu issu du même passage d'axe médian,
avec contreforme et fermeture périodique pour les vrais cycles. Il remplace
uniquement des régions déjà satin, après comparaison de leurs points exportés
et adoption commune des homologues. Les anciens fragments restent disponibles
lorsque leur couverture est meilleure au-delà de la tolérance du projet. Les
sauts sont désormais bornés après arrondi machine, depuis l'origine comprise.
Les jonctions ramifiées et la calibration textile restent des travaux distincts.

La **0.6.5** poursuit les directions satin lorsque la première perd en fidélité
et recompare les options étroites au tatami réellement généré. Elle adopte une
option commune pour toute une cohorte, à budget non croissant. Jungly à 80 mm
passe ainsi ses six lettres en satin ; à 95 mm une lettre conserve le tatami.
Un nouveau contrôle des piqûres entre colonnes bloque les promotions dont le
pic dépasse à la fois deux piqûres et le pic de la référence tatami.
Il protège aussi la recommandation automatique des variantes.

Les familles de couleurs ancrées dans les noyaux opaques source récupèrent
deux accents JPEG supplémentaires sur dix-neuf contrôles positifs ; cinq
restent non résolus. Ce mécanisme ne remplace pas une interprétation spatiale
des peintures texturées : les micro-régions et la teinte orange de Jungly ne
sont pas corrigées par ce lot. Les essais de bordure satin échouent encore aux
contrôles de piqûres en courbe. Ce sont les deux priorités suivantes, avant
d'élargir automatiquement la promotion satin.

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
