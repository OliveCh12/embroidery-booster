# Validation du moteur direct — 12 octobre 2026

Version **0.5.0** : interprétation du fond, consolidation des couleurs bitmap,
nettoyage borné des parasites et choix Auto/Satin/Tatami/Point droit. Le moteur
reste entièrement direct, avec PES/DST exportés par pyembroidery.

## Corpus géométrique de référence

Le [benchmark à 80 mm](benchmarks/input-strategy-80mm.json) compare la révision
`f8dacbc` à cette version sur **31 SVG** : logos, lettres, courbes, anneaux, trous
intentionnels, angles, petites îles, multicolore et Union Jack. Paramètres et
mesure identiques : grille 305 DPI, fil modèle 0,3 mm, couche supérieure
quantifiée, tolérance structurelle 0,25 mm.

| Mesure | 0.4.0 | 0.5.0 |
|---|---:|---:|
| Générations réussies | 31/31 | 31/31 |
| Couverture structurelle moyenne | 99,9994 % | 99,9994 % |
| Couverture minimale | 99,98 % | 99,98 % |
| Plus grand manque | 0,02 mm² | 0,02 mm² |
| Points trop courts | 0 | 0 |
| Pénétrations satin trop proches | 0 | 0 |
| Coupes | 1069 | 1068 |

Les homologues conservent une stratégie commune. L'angle par couleur concerne
les surfaces substantielles ; les détails fins gardent leur angle géométrique.
Les temps sont enregistrés à titre indicatif, avec des validations concurrentes.
L'ancien [benchmark du passage au direct uniquement](benchmarks/direct-only-80mm.json)
reste disponible comme mesure historique.

```bash
uv run python scripts/benchmark_direct.py --baseline-ref f8dacbc \
  --design-width-mm 80 --output docs/benchmarks/input-strategy-80mm.json
uv run python scripts/compare_quality.py --design-width-mm 80 \
  --machine brother-skitch-pp1
```

## Images fournies : Pepsi et aigle

Le [benchmark des images](benchmarks/input-interpretation-80mm.json) contient
leurs empreintes SHA-256 et une comparaison complète avec `f8dacbc`, à largeur
80 mm, profil générique, 12 couleurs maximum. Les fichiers utilisateur restent
locaux ; ils ne sont pas ajoutés au dépôt.

| Mesure | Pepsi avant | Pepsi après | Aigle avant | Aigle après |
|---|---:|---:|---:|---:|
| Fils | 8 | 4 | 11 | 11 |
| Points | 18 030 | 15 084 | 18 502 | 18 590 |
| Coupes | 1291 | 304 | 1999 | 1043 |
| Sauts | 1868 | 486 | 2192 | 1242 |
| Couverture structurelle par couleur | 99,71 % | 99,99 % | 99,43 % | 99,51 % |
| Plus grand manque par couleur | 0,03 mm² | 0,01 mm² | 0,16 mm² | 0,24 mm² |
| Régions trop petites omises | 891 | 45 | 1258 | 2394 |

**Pepsi :** le fond extérieur gris `#f2f2f2` est retiré ; le badge blanc, le
contour noir, le rouge et le bleu restent peints. La consolidation passe de
2976 à 150 îlots avant tracé, avec quatre couleurs de fil. Les 83 211 pixels
signalés correspondent aux nuances réaffectées à ces couleurs, pas à des pixels
alpha effacés. Les derniers petits fragments contrastés de compression restent
visibles dans les diagnostics, plutôt que d'être confondus avec un vrai accent.

**Aigle :** l'alpha indique déjà un fond transparent. Le nettoyage fusionne
3628 pixels de couleur proche, soit 91,05 mm² à cette taille : 4538 → 1512 îlots
avant tracé. Aucun alpha n'est supprimé. Les coupes baissent de **48 %** ; le
nombre total de points augmente légèrement. Le recadrage avant échantillonnage
conserve davantage de contours et de très petits détails que l'ancien tracé.
Les masques interprétés diffèrent donc : les couvertures avant/après ne sont
pas des mesures de fidélité au même bitmap brut. Les régions omises et le plus
grand manque augmentent aussi sur cet exemple ; le résultat reste explicitement
**à contrôler**, sans promesse de broderie parfaite. Réduire la palette peut
simplifier ces dégradés ; le preset PP1 propose six fils maximum.

Le [test supplémentaire PP1](benchmarks/input-pp1-80mm.json) donne 13 180 points,
6 fils et 818 coupes sur le même aigle à 80 mm. Aucun point court, crowding ou
connexion dangereuse ; couverture par couleur 99,60 %, plus grand manque
0,31 mm². Cette réduction simplifie les opérations machine mais ne valide pas
les petits détails manquants : le statut reste à contrôler.

Le benchmark distingue la couverture de silhouette (`top_metrics`) et les audits
par couleur (`stats`). La silhouette globale peut être entièrement couverte
alors que de minuscules îles d'une couleur restent manquantes. Les audits par
couleur et omissions déterminent la nécessité de revue ; une moyenne globale
ne les masque pas.

Pour répéter sur les fichiers d'origine :

```bash
uv run python scripts/benchmark_direct.py --baseline-ref f8dacbc \
  --design-width-mm 80 --input /chemin/pepsi.png --input /chemin/aigle.png \
  --output output/input-benchmark.json
```

## Régressions et fichiers machine

- **357 tests Python passent** sur la version finale (80,30 s).
- Fond fermé blanc conservé ; fond extérieur retiré par propagation ; ouverture
  alpha et canal diagonal respectés. Rotation/reflet ne changent pas ce choix.
- Logo JPEG compressé : quatre aplats récupérés, un vrai accent vert isolé
  conservé. Nettoyage borné, opt-out, alpha inchangé et taille finale du cadre
  vérifiés. La limite de 4096 régions est vérifiée avant le tracé coûteux.
- Satin forcé valide sur colonnes sûres et refusé sur formes incompatibles.
  Fill forcé évite le MAT ; running signale sa couverture de contours.
- Une frange de l'aigle révélait un ancrage débordant après son second arrondi.
  Un contour réduit à sept sommets reproduit le défaut ; l'ancrage corrigé
  reste dans la géométrie autorisée, sans omission ni point trop court.
- Les rejets géométriques des candidats restent distincts des erreurs fatales de
  budget/cadre. Les omissions sont signalées et restent dans l'audit.
- Les points réimportés depuis PES/DST sont comparés au plan quantifié. Plages de
  couverture, sous-couche, liaisons et ancrages ne se recouvrent pas dans leur
  comptage. `underlay_stitches` exclut désormais les nœuds de contexte.
- **32 tests frontend passent**, ainsi que TypeScript, ESLint et le build Next.js.
  Les réglages sont sérialisés explicitement. Le lecteur distingue les phases
  et masque les marqueurs de début/aiguille sur le résultat terminé.
- L'atelier est vérifié avec le Pepsi fourni : refus explicite du satin forcé,
  Tatami uniforme sur les régions cousables, puis Auto avec quatre fils. Les
  filtres d'aperçu et la lecture pas à pas fonctionnent. Le PES téléchargé depuis
  l'interface retrouve exactement les 15 084 pénétrations du plan quantifié
  (79,8 × 80,3 mm dans le cadre PP1), y compris leurs coordonnées.
- Les distributions Python 0.5.0 (`sdist` et `wheel`) se construisent avec succès.

## Limites physiques

Une couverture structurelle de 100 % ne signifie pas que chaque pixel est
recouvert de fil : le tatami conserve un espacement volontaire. Les trous
intentionnels restent ouverts ; les détails sous la résolution machine sont
signalés. Le nettoyage modifie seulement l'interprétation documentée, jamais
une mesure pour faire artificiellement réussir un audit.

Le lecteur montre les commandes réelles, y compris sauts, coupes et changements
manuels de fil. Le profil PP1 utilise 400 points/min et un cadre 100 × 100 mm
([Brother](https://www.brother-usa.com/p/sewing-embroidery/PP1)). Le temps affiché
exclut les changements de bobine, déplacements et accélérations.

La validation professionnelle finale exige un [essai sur tissu](SEWOUT.md).
Aucun résultat cousu physiquement n'est revendiqué dans ce rapport.
