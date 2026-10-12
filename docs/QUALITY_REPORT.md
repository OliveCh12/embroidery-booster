# Fiabilité et homogénéité du moteur direct — 12 octobre 2026

Le moteur direct automatique est recommandé pour préparer une broderie complète.
Cette itération stabilise surtout les régions homologues, les couleurs et les
règles de couture. Les SVG Ink/Stitch, l’API publique, la CLI et les exports PES/DST
sont conservés. Aucun essai cousu Brother n’a encore été réalisé.

## Défauts reproduits et règles corrigées

- Le MAT déterministe n’était pas invariant sous rotation ; la simplification
  des contours et l’origine des rangées dépendaient aussi du repère global.
  Les régions sont désormais calculées dans un repère local canonique, puis
  replacées dans leur géométrie source avant l’arrondi machine commun.
- Un satin pouvait être accepté puis renversé par le routage. Le routage conserve
  désormais sa direction et sa phase validées, en déplaçant des régions entières.
- De petites différences de masque faisaient choisir satin d’un côté et fill de
  l’autre. Les régions rigides équivalentes partagent une décision conservatrice,
  les densités, la compensation bornée, l’angle local, l’underlay et la finition.
  Chaque membre conserve son contour et doit passer l’audit sur la grille réelle.
- L’angle fill dépendait d’un coût de trajet échantillonné à un pas physique fixe.
  Il suit maintenant l’axe des moments surfaciques, trous soustraits, arrondi par
  bandes de 15°. Les formes presque isotropes conservent l’angle configuré.
- Un échantillonnage de pixels pouvait perdre une couleur ou dépendre de la
  rotation. La palette utilise l’histogramme complet et des quantiles pondérés
  bornés pour les photos. Les accents fins isolés/distincts sont conservés.
- La parité des bounds raster pouvait rejeter une symétrie correcte. Une recherche
  d’alignement ±1 pixel corrige ce biais, sans relâcher les limites de surface,
  de distance aux bords ou de topologie. Le fond utilise huit voisins, dual du
  premier plan à quatre voisins : un canal diagonal ouvert n’est plus un trou.
- Les détails non cousables restent explicitement omis. Une couleur entièrement
  non cousable est signalée, conserve une couverture nulle et n’abandonne plus
  les autres couleurs. Aucun export ne se réduit à une piqûre isolée.
- Une fondation pouvait être annoncée sans points effectivement émis. Si un
  homologue n’a aucun point de soutien après filtrage, le profil commun est
  désactivé et contrôlé à nouveau. Les petits détails évitent du volume inutile.
- Le buffer de sécurité était recalculé pour chaque rangée ; sa mise en cache
  par région conserve exactement les commandes et accélère les logos complexes.

Les règles et tolérances sont détaillées dans [DIRECT_STITCHES.md](DIRECT_STITCHES.md).
L’organisation des responsabilités figure dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Drapeau fourni : huit paires à 180°

Image WebP originale de 3840 × 2304 pixels, trois fils, tissu stable, fil 40,
cutaway, profil Skitch PP1. La comparaison porte sur la révision `e5ad164` et le
moteur corrigé. Le Union Jack possède une symétrie à 180°, pas une symétrie miroir.

| Largeur | Types divergents avant → après | Angles fill divergents avant → après | Écart médian p95 entre pénétrations homologues avant → après |
|---|---:|---:|---:|
| 60 mm | 0 → 0 | 3 → 0 | 0,660 → 0,260 mm |
| 80 mm | 1 → 0 | 3 → 0 | 0,681 → 0,240 mm |
| 94 mm | 1 → 0 | 2 → 0 | 0,683 → 0,265 mm |

Toutes les paires partagent type, angle local, densités, compensation et profil
underlay. Aucun point court ; couverture structurelle supérieure de 100 % aux
trois tailles. Répéter le WebP et utiliser sa version PNG de 960 pixels donnent
exactement les mêmes commandes et décisions à 80 mm. Le contour interprété
présente néanmoins un peu de bruit raster ; les positions ne sont pas clonées.

Le SVG public [union-jack.svg](../examples/quality/union-jack.svg), recréé
indépendamment, ajoute un second cas de rasterisation aux tests. Ses huit paires,
les angles réellement cousus et les PES/DST relus sont vérifiés à 80 et 94 mm.
Données détaillées : [flag-consistency.json](benchmarks/flag-consistency.json).

## Corpus de 31 SVG à 80 mm

Même préparation et même audit des points supérieurs quantifiés pour les deux
versions ; baseline isolée par `git archive`. Cadre de mesure 500 × 500 mm,
pas satin/fill 0,4 mm, compensation demandée 0,15 mm, point maximal 8 mm.
Ce cadre de mesure n’est pas une recommandation de taille pour le Skitch.
Les temps correspondent à un passage local, sans garantie statistique.

| Mesure | Avant | Après |
|---|---:|---:|
| Plans réussis | 31/31 | 31/31 |
| Couverture structurelle supérieure moyenne | 99,9994 % | 99,9994 % |
| Plus grand manque structurel | 0,05 mm² | 0,02 mm² |
| Points courts / crowding satin détecté | 0 / 0 | 0 / 0 |
| Point cousu maximal | 5,20 mm | 5,20 mm |
| Couverture brute moyenne | 87,06 % | 84,46 % |
| IoU brut moyen | 80,18 % | 77,92 % |
| Débordement moyen | 51,19 mm² | 48,98 mm² |
| Coupes totales | 1001 | 1069 |
| Microdétails omis | 72 | 73 |
| Temps médian complet | 0,422 s | 0,437 s |
| Temps cumulé des 31 cas | 29,81 s | 20,85 s |
| Cas complexe flower | 7,59 s | 4,68 s |

L’amélioration démontrée concerne l’homogénéité, la stabilité des règles et le
contrôle des points émis. Les directions changent volontairement : couverture
brute et IoU simulés baissent sur ce corpus, et les coupes augmentent légèrement.
Les omissions ne sont pas assimilées à une reconstruction fidèle. Le nouveau
moteur ne prétend pas améliorer toutes les métriques sur chaque dessin.
Données : [consistent-digitizing.json](benchmarks/consistent-digitizing.json).

La galerie `/quality` contient 31 dessins et les nouveaux plans directs ; les
30 comparaisons manuelles et Ink/Stitch précédentes sont conservées. Leur présence
ne signifie pas une nouvelle validation de couture native. Voir le
[rapport JSON](quality-comparison.json).

## Validation et limites pratiques

289 tests Python couvrent couleurs, D4, formes réellement différentes, trous,
canaux ouverts, cadres rectangulaires, angles, translation, répétabilité,
densité, sous-couches réelles, omissions, géométrie et contrats API/CLI.
Ruff valide ; wheel et sdist sont construits. Les PES/DST relus conservent les
positions quantifiées et les changements de fil. L’API locale relancée a importé
le SVG du drapeau via Next.js et généré un plan à trois couleurs avec succès.

Le fil simulé fait 0,3 mm ; la couverture structurelle admet une distance de
0,25 mm au fil. 100 % ne prouve donc pas une surface opaque, ni l’absence de
fronces sur tissu. Sous-couches, locks et trajets cousus sont exclus de l’audit
supérieur. Les couleurs omises restent comptées dans les manques.

La normalisation couvre translations, réflexions et rotations de 90° ; les
motifs à rotations arbitraires ne sont pas encore explicitement regroupés.
Redimensionner peut changer satin en fill lorsque les limites physiques ou le
contrôle de crowding l’exigent ; les homologues restent cohérents à chaque taille.
Un changement proche d’une frontière de classification reste possible.
Les photos sont quantifiées sans reconnaissance sémantique. Tension, étalement
du fil, stabilisation et déformation du tissu ne sont pas simulés.

Le profil Skitch PP1 valide le cadre de 100 × 100 mm et propose six fils / 7 mm
satin, recommandations modifiables. Les [spécifications Brother](https://www.brother-usa.com/p/sewing-embroidery/PP1)
et le [protocole de sew-out](SEWOUT.md) précisent l’import Artspira et les essais.
La validation sur le tissu, le fil et le stabilisateur réels reste indispensable.

```bash
uv run pytest -q
uv run python scripts/benchmark_direct.py --baseline-ref e5ad164 --design-width-mm 80 --output docs/benchmarks/consistent-digitizing.json
uv run python scripts/compare_quality.py --modes direct-auto
uv run embroidery-rungs examples/quality/union-jack.svg --method direct --design-width 80 --machine brother-skitch-pp1 --fabric stable --thread-weight 40 --stabilizer cutaway -o output/flag
uv build
```

Historique : [couture physique précédente](benchmarks/QUALITY_REPORT_2026-10-12_SEWING.md),
[couleurs](benchmarks/QUALITY_REPORT_2026-10-12_COLORS.md),
[rapport du 11 octobre](benchmarks/QUALITY_REPORT_2026-10-11.md).
Références : [satin Ink/Stitch](https://inkstitch.org/docs/stitches/satin-column/),
[pyembroidery](https://github.com/EmbroidePy/pyembroidery/blob/main/README.md).
