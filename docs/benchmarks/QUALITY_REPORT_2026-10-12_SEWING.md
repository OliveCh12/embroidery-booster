# Qualité de couture du moteur direct — 12 octobre 2026

**Le direct automatique reste recommandé pour un premier plan complet.** Il
conserve une stratégie supérieure par région de couleur : satin régulier lorsque
la géométrie le permet, sinon tatami complet. Ink/Stitch reste disponible pour
inspection et finition. Aucun essai cousu Brother n'a encore été effectué.

## Constats et corrections

- Le buffer circulaire de compensation ajoutait aussi des rangées perpendiculaires
  aux points. La compensation agit désormais dans leur axe, avec limitation
  surface/périmètre et trous conservés.
- La sous-couche du fill touchait les bords. Les fondations sont en retrait de
  0,3–0,5 mm, avec contour et rangées croisées espacées. Jersey et éponge reçoivent
  plus de soutien, sans densifier le dessus. Les petits détails évitent une
  fondation complète qui ajouterait du volume.
- Un détail de 0,1 × 0,1 mm pouvait exporter une seule piqûre sans couture.
  Le filtrage se fait avant émission sur la grille machine réelle. Les régions
  non cousables sont déclarées `omitted` et signalées ; une couleur entièrement
  non cousable provoque une erreur demandant un agrandissement.
- Le filtrage pouvait perdre une extrémité ou couper un angle. L'extrémité est
  conservée lorsque possible et les nouvelles cordes sont contrôlées après arrondi.
- Une largeur satin évaluée par percentile pouvait cacher une extrémité large.
  Le maximum de chaque colonne est contrôlé, avec réserve pour compensation et
  arrondi sous la longueur maximale, afin d'éviter les subdivisions dans sa face.
- Un candidat running invalide abandonnait la génération. Le fallback de région
  entière s'applique maintenant aussi à ces candidats.

MAT par couleur, contreformes, vrais changements de fil, absence de patches
satin/fill, contrôle dans les deux sens et audit supérieur indépendant des
sous-couches restent en place. L'API et les SVG Ink/Stitch sont préservés.

## Avant/après sur 30 SVG à 80 mm

Révision `6bde1eb` isolée par `git archive`, même code de mesure des **points
supérieurs quantifiés** pour les deux versions. Document de 80 mm de large,
cadre de mesure 500 × 500 mm, pas satin/fill 0,4 mm, compensation demandée 0,15 mm,
longueur maximale 8 mm. Corpus : logos, multicolore, courbes, pointes, trous,
petites îles et nouveau coupon. Temps d'un passage local avec caches.

| Mesure | Avant | Après |
|---|---:|---:|
| Plans réussis | 30/30 | 30/30 |
| Couverture structurelle supérieure moyenne | 99,9993 % | 99,9993 % |
| Plus grand manque | 0,05 mm² | 0,05 mm² |
| Couverture brute moyenne | 87,29 % | 87,15 % |
| IoU brut moyen | 79,60 % | 80,05 % |
| Débordement moyen | 57,31 mm² | 52,07 mm² |
| Coupes totales | 979 | 903 |
| Temps médian complet | 0,327 s | 0,412 s |
| Point cousu maximal | 5,20 mm | 5,20 mm |

Le débordement simulé baisse d'environ 9 %. Les coupes diminuent en partie par
suppression des piqûres sans couture. **72 microdétails sont désormais déclarés
non cousables**, principalement dans la fleur : cette suppression ne les rend
pas fidèles. Leurs avertissements recommandent l'agrandissement. La fondation
plus complète et les contrôles coûtent du temps ; ce passage ne constitue pas
une étude statistique de performance.

Données : [sewing-quality.json](benchmarks/sewing-quality.json).

## Quatre méthodes à taille originale

**120 plans réussis sur 30 SVG**, dont 30 exports réels d'Ink/Stitch officiel
3.3.0. La galerie `/quality` contient les aperçus et empreintes actuels. Le cadre
de mesure 500 × 500 mm ne signifie pas que chaque taille originale tient dans
le Skitch.

| Méthode | Couverture structurelle commune | IoU brut | Coupes | Point maximal |
|---|---:|---:|---:|---:|
| Direct manuel · fill | 97,08 % | 75,58 % | 1514 | 7,92 mm |
| Direct manuel · satin subdivisé | 97,08 % | 80,55 % | 973 | 7,93 mm |
| Direct automatique | 100,00 % | 79,33 % | 1105 | 6,45 mm |
| Ink/Stitch · réglages explicites | 91,73 % | 75,66 % | 803 | 12,65 mm |

L'empreinte commune inclut sous-couches et trajets cousus, sauts exclus. L'audit
**supérieur seulement** du direct automatique donne 99,9993 % en moyenne et un
manque maximal de 0,08 mm². Il déclare 39 détails omis à ces tailles. Le direct
automatique sépare les couleurs ; rails natifs et direct manuel sont monochromes.
Les exports natifs utilisent nos rails, pas une numérisation professionnelle.
Certains contours restent plus fidèles dans le natif ou le satin manuel. Les
longueurs natives dépassant le maximum demandé restent affichées comme telles.

Données : [quality-comparison.json](quality-comparison.json).

## Sens des mesures et limites

Fil de référence 0,3 mm. Couverture, IoU et débordement bruts n'ont aucune
tolérance. La couverture structurelle admet 0,25 mm autour du fil pour distinguer
l'espacement régulier des lacunes importantes. 100 % ne prouve donc pas l'opacité
du tissu ni la reproduction au pixel près. Chaque couleur est contrôlée aussi
indépendamment dans le JSON. Inspecter omissions et distance maximale au fil,
même lorsque la surface manquante est petite.

La grille de 0,1 mm et la longueur minimale ne reproduisent pas tous les détails
d'une scène. Les photos sont quantifiées sans reconnaissance sémantique. Les
presets sont modifiables ; aucune simulation de tension, déformation ou étalement
du fil n'est revendiquée.

Le profil `brother-skitch-pp1` valide **100 × 100 mm** et propose six fils/7 mm de
satin, avec overrides pour ces deux recommandations.
[Brother indique cette surface et l'utilisation d'Artspira](https://www.brother-usa.com/p/sewing-embroidery/PP1).
[Artspira accepte PES et DST pour la broderie](https://support.brother.com/g/s/hf/mobileapp_info/artspira/plan/func1/en.html),
selon l'offre et la disponibilité locale. Vérifier la coupe des fils de saut
sur la machine ; une commande TRIM relue ne suffit pas.

Le [coupon et protocole](SEWOUT.md) couvrent satin droit, courbe, taper, fill troué
et détails fins. Stable/40, stretch/40, textured/30 et stable/60 passent les
contrôles numériques. Stable/40 contient 2347 points, trois fils et deux changements,
sans point court ni détail omis. **La validation sur tissu reste à réaliser.**

## Validation et reproduction

**210 tests Python, 12 tests frontend**, Ruff, TypeScript/ESLint, build Next.js,
wheel et sdist. PES/DST relus conservent exactement positions cousues et palettes.
Tests : fondations en retrait, compensation directionnelle, minimum configurable,
extrémités, absence de faux segment, erreurs machine, dimensions et API/CLI.

L'API locale relancée traite le coupon Skitch et fournit ses quatre téléchargements.
Le contrôle visuel navigateur de cette itération a été bloqué après redémarrage
sur une page d'erreur interne ; aucun nouveau test visuel complet de l'interface
n'est revendiqué. Le build et le contrat frontend passent.

```bash
uv run python scripts/benchmark_direct.py --baseline-ref 6bde1eb --design-width-mm 80 --output docs/benchmarks/sewing-quality.json
uv run python scripts/compare_quality.py --inkstitch /path/to/inkstitch
uv run python scripts/compare_quality.py --reuse
uv run pytest -q
pnpm test:frontend
pnpm check
pnpm build
uv build
```

Historique : [itération couleurs](benchmarks/QUALITY_REPORT_2026-10-12_COLORS.md),
[rapport du 11 octobre](benchmarks/QUALITY_REPORT_2026-10-11.md).
Références : [satin Ink/Stitch](https://inkstitch.org/docs/stitches/satin-column/),
[tatami et sous-couche](https://inkstitch.org/docs/stitches/fill-stitch/),
[pyembroidery](https://github.com/EmbroidePy/pyembroidery/blob/main/README.md).
