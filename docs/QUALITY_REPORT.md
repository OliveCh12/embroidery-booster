# Validation du moteur direct — 12 octobre 2026

Version 0.4.0 : une seule chaîne de génération, sans logiciel de bureau externe.
Le pipeline ne calcule plus de squelette/rails préalable à la numérisation directe.
Les guides et leur optimiseur ont été supprimés ; `stitching/rails.py` ne produit
que la géométrie effectivement utilisée par le satin.

## Mesures reproductibles

Le [benchmark avant/après](benchmarks/direct-only-80mm.json) compare la révision
`3d5dd9d` à cette version sur **31 SVG**, tous redimensionnés à 80 mm : logos,
courbes, anneaux, trous intentionnels, angles, petites îles, multicolore et drapeau.
Les paramètres physiques et l’audit sont identiques : grille 305 DPI, fil modèle
0,3 mm, couche supérieure quantifiée, tolérance structurelle 0,25 mm.

| Mesure | Avant | Direct uniquement |
|---|---:|---:|
| Générations réussies | 31/31 | 31/31 |
| Couverture structurelle moyenne | 99,9994 % | 99,9994 % |
| Couverture structurelle minimale | 99,98 % | 99,98 % |
| Plus grand manque | 0,02 mm² | 0,02 mm² |
| Points trop courts détectés | 0 | 0 |
| Pénétrations satin trop proches | 0 | 0 |
| Coupes | 1069 | 1069 |
| Temps total mesuré | 25,267 s | 21,221 s |

Les durées sont indicatives : les suites de tests tournaient aussi pendant cette
mesure. Les empreintes et les commandes machine sont des validations géométriques,
pas une simulation de la déformation du tissu.

```bash
uv run python scripts/benchmark_direct.py --baseline-ref 3d5dd9d \
  --design-width-mm 80 --output docs/benchmarks/direct-only-80mm.json
uv run python scripts/compare_quality.py --design-width-mm 80 \
  --machine brother-skitch-pp1
```

La deuxième commande produit la galerie `/quality` dans `output/quality`.
Elle montre le dessin interprété, les points exportés et leur empreinte supérieure.
Elle mesure à une résolution indépendante de 12 pixels/mm : de petits écarts
avec le benchmark 305 DPI sont attendus. Le JSON est versionné en schema 3.

## Drapeau fourni en WebP

Le fichier Union Jack fourni par l’utilisateur, à 80 mm sur le profil PP1,
produit **9669 points**, **3 fils**, **2 changements de couleur**, sans détail omis,
point trop court ni pénétration satin trop proche. La couverture structurelle
mesurée est 100 % ; le plus grand manque est 0 mm². L’étendue compensée est
80,2 × 48,2 mm, dans le cadre 100 × 100 mm.

Les homologues détectés utilisent tous la même méthode, densité, compensation et
sous-couche. Les huit triangles bleus appartiennent à deux groupes de quatre :
fill, angle canonique 165°, sous-couche bord + croisée. Les correspondances sont
évaluées dans leur repère géométrique, sans imposer une symétrie inexistante aux
diagonales rouges du véritable drapeau.

## Régressions couvertes

- **311 tests Python passent** : extraction médiale, géométrie, satin/fill/running,
  symétrie, palette, couverture supérieure, trous intentionnels, petits détails,
  commandes quantifiées, aller-retour PES/DST, profils machine, API et CLI.
- Les grandes régions au diamètre intérieur clairement supérieur à la largeur
  satin sûre passent directement au fill. Un test prouve l’absence de calcul MAT,
  tout en contrôlant la couverture et la conservation d’un trou.
- Les presets habituels ne changent pas. Les valeurs extrêmes sont bornées par
  tissu/fil ; la demande et chaque ajustement sont enregistrés explicitement.
- Les requêtes invalides et les erreurs d’export préservent les anciens fichiers,
  libèrent la capacité du serveur et retirent les jobs incomplets.
- Le JSON machine schema 3 fournit coordonnées 0,1 mm centrées sur le cadre,
  commandes, fils, sous-couches et régions. Les points relus dans PES et DST sont
  comparés aux coordonnées du plan.
- Les limites du cadre sont vérifiées après centrage et quantification. Une
  petite couleur défectueuse déclenche une revue même si la moyenne du dessin
  masque son défaut. Au-delà de 4096 régions visibles, l’entrée est refusée
  avant les calculs coûteux, avec une demande explicite de simplification.
- **29 tests frontend passent**, ainsi que TypeScript, ESLint et le build Next.js.
  Le navigateur valide le cadre physique, la lecture, la pause au changement de
  fil, le téléchargement PES, les thèmes clair/sombre et le mobile à 390 px.
  Les 9669 pénétrations du PES téléchargé sont identiques au plan affiché.

## Limites physiques

Une couverture structurelle de 100 % ne signifie pas que chaque pixel est recouvert
par du fil : un tatami conserve un espacement volontaire. Les trous présents dans
le dessin restent ouverts ; les détails inférieurs à la résolution machine sont
signalés, jamais déclarés parfaits.

Le lecteur montre les commandes du plan exporté, y compris sauts, coupes et
changements de couleur. Le rythme nominal PP1 est 400 points/min, avec un cadre
100 × 100 mm ([Brother](https://www.brother-usa.com/p/sewing-embroidery/PP1)).
Le temps affiché compte seulement les cycles d’aiguille ; il exclut les
changements de bobine, déplacements et accélérations.

La validation professionnelle finale exige un [essai sur tissu](SEWOUT.md).
Aucun résultat cousu physiquement n’est revendiqué dans ce rapport.
