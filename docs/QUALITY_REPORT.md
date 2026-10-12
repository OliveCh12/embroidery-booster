# Couverture et fidélité des points

28 SVG : les 24 cas précédents et quatre nouveaux contrôles (anneau fin, jonction fine, contreforme de 0,8 mm et îles de 0,9 mm). **112 plans réussis**, dont 28 exports réels du moteur officiel Ink/Stitch 3.3.0. Un second passage teste les 28 dessins à une largeur de document de 80 mm. Instantané du 11 octobre 2026.

## Décision

**Le direct automatique reste recommandé.** Il conserve les rails fins, compare satin et fill en donnant priorité à la couverture, puis répare les manques constatés dans les points quantifiés. Le workflow Ink/Stitch, les SVG éditables et les défauts historiques de la bibliothèque/CLI restent disponibles.

La comparaison native porte sur nos rails générés, pas sur une numérisation manuelle optimale. Ces résultats ne prouvent pas le meilleur rendu sur tissu : aucun sew-out Brother n’a été réalisé.

## Causes corrigées

- Le seuil historique de 1,5 mm transformait des colonnes fines en simples lignes centrales. Le direct automatique conserve désormais leurs rails : satin fin vers 0,6 mm avec du fil 40 wt, selon la longueur minimale et le fil choisi. Le seuil Ink/Stitch reste inchangé.
- Les résidus sans intérieur de 1,5 mm étaient ignorés. Les candidats satin incluent maintenant les résidus significatifs étroits.
- Les coupes pouvaient faire gagner un candidat moins couvrant. La couverture doit maintenant rester à 0,25 point de pourcentage du meilleur candidat avant de comparer les coûts.
- La couverture des rails ne mesurait pas les points effectivement exportés. Un audit plus fin du SVG vérifie les points quantifiés, avec deux passes de réparation au maximum. Les patches restent dans la silhouette, sans sous-couche supplémentaire ; les blancs fins utilisent des chemins de squelette. Les trous du dessin sont exclus.

Les réparations ne sont conservées que si elles réduisent la surface manquante. Un échec conserve le plan valide avec son diagnostic. Les contrôles manuels et `fill_gaps=False` désactivent ces réparations. L’interface affiche la couverture géométrique et le plus grand manque ; les défauts résiduels significatifs génèrent un avertissement.

## Protocole

- Taille physique originale, MAT déterministe à 150 DPI et cadre de comparaison 500 × 500 mm. L’audit direct utilise un rendu voisin de 305 DPI lorsque le masque MAT est trop grossier, limité à 4 MP.
- Pas satin/fill 0,4 mm, compensation 0,15 mm, sous-couche activée, fil de référence 40 wt. Chaque moteur calcule sa propre sous-couche.
- Direct : coordonnées JSON à 0,1 mm, vérifiées par round-trip PES/DST. Natif : coordonnées relues du PES et recalées par son aperçu.
- Mesure indépendante : zoom uniforme, empreinte de fil de 0,3 mm à 12 pixels/mm, résolution réduite au-delà de 2400 pixels par côté. Sous-couches, locks et trajets cousus inclus ; sauts exclus.
- Couverture/IoU bruts : empreinte sans tolérance. Couverture structurelle : proportion de la source à au plus 0,25 mm d’un fil. Le plus grand manque mesure une composante source au-delà de cette distance ; les trous intentionnels ne font pas partie de la source.
- Les espaces réguliers entre rangées expliquent une partie des différences entre couverture brute et structurelle. Une couverture structurelle de 100 % ne signifie pas une empreinte brute identique au SVG.
- Temps observés sur un passage avec caches actifs. Direct : préparation, MAT, audit et exports ; natif : deux appels CLI après géométrie commune. Ce ne sont pas des benchmarks statistiques.

## Résultats des 28 SVG

Moyennes non pondérées : chaque dessin compte une fois.

| Méthode | Couverture structurelle | IoU brut | Coupes totales | Temps médian | Point maximal |
|---|---:|---:|---:|---:|---:|
| Direct manuel · fill | 96.95% | 74.13% | 1307 | 0.188 s | 7.92 mm |
| Direct manuel · satin subdivisé | 96.94% | 79.45% | 807 | 0.186 s | 7.94 mm |
| Direct automatique | 99.97% | 84.37% | 983 | 0.316 s | 7.94 mm |
| Ink/Stitch · réglages explicites | 92.43% | 75.85% | 786 | 2.699 s | 12.65 mm |

Le direct respecte le maximum demandé de 8 mm dans les 28 cas. Le natif atteint 12,65 mm malgré les réglages séparés top/sous-couche ; l’application signale les dépassements effectifs.

## Avant / après sur les mêmes 24 sources

Les métriques et réglages sont identiques. Les quatre nouveaux cas sont exclus de ce tableau pour conserver une comparaison comparable.

| Direct automatique | Avant | Après |
|---|---:|---:|
| Couverture structurelle moyenne | 98.70% | 99.97% |
| IoU brut moyen | 83.37% | 86.76% |
| Coupes totales | 886 | 968 |
| Points totaux | 90054 | 96353 |

La couverture et l’IoU progressent avec davantage de points et de coupes : cette consolidation privilégie la fidélité. La fleur demeure fragmentée ; ses petits détails ne justifient pas une promesse de résultat parfait.

Instantané précédent : [quality-before-coverage-repairs.json](benchmarks/quality-before-coverage-repairs.json).

## Cas sensibles et effet de la taille

| SVG | Structure avant | Structure après | IoU après | Structure à 80 mm | Plus grand manque à 80 mm |
|---|---:|---:|---:|---:|---:|
| `quality/thin.svg` | 89.48% | 100.00% | 74.52% | 100.00% | 0.00 mm² |
| `quality/tight-curve.svg` | 99.02% | 100.00% | 90.17% | 100.00% | 0.00 mm² |
| `arabian.svg` | 93.54% | 99.87% | 74.26% | 99.99% | 0.01 mm² |
| `flower.svg` | 96.84% | 99.90% | 80.78% | 99.68% | 0.22 mm² |
| `margot.svg` | 93.89% | 99.50% | 51.38% | 100.00% | 0.02 mm² |
| `satin-demo.svg` | 97.40% | 99.99% | 88.12% | 100.00% | 0.01 mm² |

Le fichier Margot mesure environ 10 mm à sa taille originale : certaines régions sont trop fines pour un satin régulier. À 80 mm, sa structure atteint 100 % avec un IoU de 87,1 %. La fleur à 80 mm conserve 99,68 % de couverture structurelle et un plus grand manque de 0,22 mm² : elle reste à inspecter.

Le second passage redimensionne la largeur du document, sans adaptation au cadre ; certaines hauteurs dépassent donc 100 mm. Les tests du parcours utilisateur couvrent aussi l’adaptation proportionnelle à un cadre de 100 × 100 mm. Résultats complets : [quality-80mm.json](benchmarks/quality-80mm.json).

## Validation et matériaux

166 tests Python passent, dont les régressions sur traits fins, jonctions, contreformes, logos à taille pratique, réparation d’une couture de 1,3 mm, conservation des trous PNG transparents/opaques et limites machine. La lecture PES/DST préserve les coordonnées cousues. Le frontend passe le contrôle TypeScript/ESLint et ses neuf tests.

L’utilisateur précise tissu, fil et stabilisateur ; les presets proposent densité, compensation et sous-couche modifiables. Le stabilisateur est enregistré, sans modèle mécanique calibré. Les bitmaps deviennent des silhouettes monochromes inspectables, pas des photos multicolores numérisées.

Tension, déformation du tissu, étalement du fil et brillance du satin ne sont pas simulés. Des détails plus petits que le fil, des régions fragmentées et certains angles peuvent nécessiter un agrandissement ou une retouche. Un essai cousu reste nécessaire pour valider le rendu physique.

## Reproduire

```bash
uv run python scripts/compare_quality.py --inkstitch /path/to/inkstitch
uv run python scripts/compare_quality.py --output output/quality-80mm --design-width-mm 80 --modes direct-auto
uv run python scripts/compare_quality.py --reuse
uv run pytest -q
pnpm dev
```

La galerie Next.js `/quality` compare source, points exportés et empreinte du fil. Elle consomme le JSON et les aperçus produits par le script ; les données actuelles sont dans [quality-comparison.json](quality-comparison.json).

Sources des réglages natifs : [paramètres satin](https://inkstitch.org/docs/stitches/satin-column/), [CLI](https://inkstitch.org/docs/command-line/), [implémentation officielle 3.3.0](https://github.com/inkstitch/inkstitch/blob/v3.3.0/lib/elements/satin_column.py).
