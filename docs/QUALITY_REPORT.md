# Qualité du moteur direct — 12 octobre 2026

**Le direct automatique reste le parcours recommandé**, avec un choix cohérent
par région visible : satin lorsque ses points sont réguliers et couvrants,
tatami sur toute la région lorsqu'ils ne le sont pas. Ink/Stitch reste disponible
pour inspection et finition. Aucun essai cousu Brother n'a encore été effectué.

## Faiblesses corrigées

- L'alpha fusionnait les couleurs. Chaque couleur visible a maintenant son
  masque, son MAT, ses régions, son fil et de vrais changements de couleur PES/DST.
- Les patches mélangeaient satin et fill dans une même région. Le moteur remplace
  une région insuffisante par un remplissage complet et conserve ses contreformes.
- La sous-couche et les trajets pouvaient masquer une couche supérieure incomplète
  dans les métriques. L'audit automatique ne mesure que les vrais points supérieurs
  quantifiés, par couleur. Le JSON permet de reconstruire cette mesure.
- Les éventails de squelette aux extrémités des colonnes droites et les piqûres
  répétées aux courbes produisaient des irrégularités. Les colonnes presque convexes
  utilisent des sections parallèles ; des bandes de points courts distribuent les
  piqûres intérieures. Le satin est contrôlé dans les deux sens de couture.
- Les petites îles disparaissaient sous la longueur minimale machine. Les détails
  compacts représentables sont conservés, avec une extension bornée et signalée.
- Des remplissages compensés gonflaient les petits contours. La compensation est
  limitée selon surface/périmètre, avec finition intérieure contrôlée et trous exclus.

## Protocole et sens des mesures

Le corpus comprend **29 SVG** : logos, trois couleurs superposées, colonnes,
courbes, angles, pointes, anneaux, jonctions, contreformes et petites îles.
Pas satin/fill 0,4 mm, compensation demandée 0,15 mm, sous-couche activée,
longueur maximale 8 mm et cadre de mesure 500 × 500 mm.

Deux protocoles sont séparés :

1. **Avant/après à largeur de document 80 mm** : révision `6b6c756` isolée par
   `git archive`, même code de mesure pour les deux versions, rendu voisin de
   305 DPI. Seulement satin/fill/running supérieurs, sans sous-couche/locks/travel.
2. **Comparaison des moteurs à taille originale** : exports réels Ink/Stitch
   3.3.0 et directs, empreinte commune à 12 pixels/mm de tous les segments cousus
   (sauts exclus), plus audit supérieur séparé pour le direct automatique.

Fil de référence **0,3 mm**. Couverture et IoU bruts n'ont aucune tolérance.
La couverture structurelle autorise **0,25 mm** de distance autour de cette
empreinte. Le plus grand manque est une composante source au-delà de cette
distance ; les trous intentionnels ne font pas partie de la source.
100 % structurels ne signifient donc pas une source entièrement recouverte au
pixel près. Les arrondis peuvent afficher 100 % malgré une très petite lacune.

Les palettes nouvelles respectent les couleurs ; l'ancien moteur et les rails
natifs sont monochromes. La mesure globale avant/après utilise la silhouette
commune. Des tests indépendants et les diagnostics exportés vérifient aussi la
couverture de chaque couleur, sans qu'un autre fil puisse la masquer.
Les temps sont ceux d'un passage local avec caches, sans étude statistique.

## Avant/après du direct sur les mêmes 29 SVG à 80 mm

| Mesure des points supérieurs | Avant | Après |
|---|---:|---:|
| Plans réussis | 29/29 | 29/29 |
| Couverture structurelle moyenne | 99,966 % | 99,999 % |
| Surface structurelle manquante moyenne | 0,182 mm² | 0,010 mm² |
| Plus grand manque dans le corpus | 0,20 mm² | 0,01 mm² |
| Couverture brute moyenne | 92,91 % | 87,32 % |
| IoU brut moyen | 84,75 % | 79,53 % |
| Débordement moyen | 57,87 mm² | 57,00 mm² |
| Coupes totales | 737 | 956 |
| Temps médian complet | 0,206 s | 0,313 s |
| Point cousu maximal | 7,88 mm | 5,20 mm |

La baisse de l'IoU brut est réelle : davantage de régions passent entièrement en
tatami, dont le pas de 0,4 mm dépasse le diamètre de référence du fil (0,3 mm).
La régularité des rangées et l'absence de grandes lacunes progressent, sans prouver
une fidélité visuelle supérieure sur chaque dessin. Les coupes augmentent aussi.
Un remplissage qui évite les raccords de patches ne supprime pas le coût des trous
et de la fragmentation du dessin.

Dans ce passage, aucun satin retenu ne présente de piqûre locale trop rapprochée
selon le contrôle à distance minimale moins 0,05 mm. Les contreformes restent
exclues. La fleur passe de 99,69 % à 99,98 % de couverture supérieure ; 33 détails
compacts sont ajustés de 0,08 mm maximum par extrémité. Son avertissement reste
visible : un détail minuscule atteint encore 0,901 mm de distance au fil, malgré
une lacune de seulement 0,01 mm². L'agrandissement reste conseillé pour sa fidélité.

Données : [direct-top-layer.json](benchmarks/direct-top-layer.json).

## Quatre méthodes à taille originale

**116 plans réussis**, dont 29 exports du moteur natif officiel. Moyennes non
pondérées ; les sous-couches et trajets cousus sont inclus dans ce tableau commun.

| Méthode | Couverture structurelle | IoU brut | Coupes | Temps médian | Point maximal |
|---|---:|---:|---:|---:|---:|
| Direct manuel · fill | 97,06 % | 74,74 % | 1527 | 0,115 s | 7,94 mm |
| Direct manuel · satin subdivisé | 97,05 % | 80,21 % | 930 | 0,112 s | 7,93 mm |
| Direct automatique | 100,00 % | 77,88 % | 1112 | 0,242 s | 6,45 mm |
| Ink/Stitch · réglages explicites | 91,91 % | 75,72 % | 793 | 1,499 s | 12,65 mm |

L'audit **supérieur uniquement** du direct automatique atteint 99,9997 % en
moyenne, avec un manque maximal de 0,05 mm². La fleur à sa taille originale
conserve un détail très éloigné du fil (1,277 mm) et des avertissements.

Le natif est comparé sur nos rails générés, pas sur une numérisation experte.
Il reste meilleur sur certains contours/courbes selon l'IoU. Ses dépassements
effectifs du maximum sont signalés, malgré les paramètres top/sous-couche.
Ces observations soutiennent le choix direct pour l'automatisation, sans établir
qu'un moteur produit toujours le meilleur rendu physique.

Données : [quality-comparison.json](quality-comparison.json). La galerie `/quality`
montre la source, les points machine et l'empreinte commune, avec la couverture
supérieure du direct affichée séparément.

## Validation

**185 tests Python**, **11 tests frontend**, TypeScript/ESLint et build Next.js.
Le wheel et le sdist sont construits. PES/DST relus préservent les coordonnées
cousues, palettes et changements de couleur du plan. Les SVG historiques sont
comparés entre appels originaux et `both`. Les régressions couvrent aussi alpha,
PNG opaque, peintures pâles/proches, accents, gradients, chevauchements, trous,
taper étroit, densité des courbes, absence de faux audit par sous-couche,
budgets/hoops et téléchargement web.

Un test navigateur importe le SVG multicolore, génère trois fils avec deux
changements de couleur et télécharge le PES Brother. Sa lecture retrouve exactement
les couleurs et tous les points du JSON. L'interface permet une palette bornée et
l'override monochrome, et distingue la couverture structurelle du rendu physique.

## Reproduire

```bash
uv run python scripts/benchmark_direct.py --baseline-ref 6b6c756 --design-width-mm 80
uv run python scripts/compare_quality.py --inkstitch /path/to/inkstitch
uv run python scripts/compare_quality.py --reuse
uv run pytest -q
pnpm check
pnpm test:frontend
pnpm build
uv build
```

Les presets tissu/fil/stabilisateur restent modifiables et ne simulent pas tension,
déformation ou étalement du fil. Les photos sont quantifiées, sans reconnaissance
sémantique. Certaines petites pointes ou formes complexes nécessitent agrandissement
ou finition. **La qualité physique exige encore un essai cousu sur le tissu cible.**

Rapport antérieur : [instantané du 11 octobre](benchmarks/QUALITY_REPORT_2026-10-11.md).
Références : [satin Ink/Stitch](https://inkstitch.org/docs/stitches/satin-column/),
[CLI Ink/Stitch](https://inkstitch.org/docs/command-line/),
[pyembroidery](https://github.com/EmbroidePy/pyembroidery/blob/main/README.md).
