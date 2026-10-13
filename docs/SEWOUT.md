# Validation sur tissu — Brother Skitch PP1

Le moteur contrôle géométrie, longueurs, densité demandée, palette et formats.
Un essai physique reste indispensable pour calibrer tension, soutien, compensation
et couverture selon le fil et le tissu. Les presets sont des points de départ.

## Coupon reproductible

`examples/quality/sewout.svg` réunit trois couleurs : colonne droite de 4 mm,
courbe, variation de largeur, tatami avec une contreforme et détails de
0,4 / 0,8 / 1,5 mm. Le document mesure 80 × 80 mm ; les points occupent environ
60 × 62 mm. Les décisions indiquent le type retenu pour chaque région.

```bash
uv run embroidery-rungs examples/quality/sewout.svg \
  --machine brother-skitch-pp1 \
  --fabric stable --thread-weight 40 --stabilizer cutaway \
  --fit-to-hoop -o output/sewout-cotton
```

Pour le jersey, remplacer `--fabric stable` par `--fabric stretch` et garder un
support à découper adapté. Pour l'éponge, choisir `textured` et prévoir un film
hydrosoluble de surface compatible avec le tissu. Noter séparément support et
film : le champ stabilisateur du projet décrit seulement le support principal.

## Import et préparation

Le [Skitch PP1](https://www.brother-usa.com/p/sewing-embroidery/PP1) a une surface
maximale de 100 × 100 mm, une vitesse annoncée de 400 points/minute et fonctionne via Artspira. Le profil valide cette surface
et propose six fils et un satin de 7 mm ; palette et largeur restent modifiables.
[Artspira accepte PES et DST pour la broderie](https://support.brother.com/g/s/hf/mobileapp_info/artspira/plan/func1/en.html).
Importer `sewout_direct.pes` ; le SVG est la source, pas un fichier de points.
Vérifier la disponibilité de l'import dans son offre Artspira et sa région.

Satin et tatami peuvent se succéder dans le même fichier PES : aucun réglage
mécanique ne choisit entre ces deux trajets de points. Avec l'unique aiguille,
le changement de bobine correspond à la couleur. La largeur de 7 mm est une
recommandation de numérisation du projet, pas une interdiction matérielle de
broder une région plus large. Le moteur peut la diviser en colonnes adjacentes ;
contrôler leurs coutures internes et leur relief sur tissu avant production.

Utiliser les aiguilles, fils de canette et supports compatibles avec les
[instructions Brother](https://support.brother.com/g/b/manualtop.aspx?c=us&lang=en&prod=hf_pp1eus).
Encercler le tissu sans l'étirer. Activer **Jump Stitch Trimming** dans les
réglages machine d'Artspira avant l'envoi. Les commandes TRIM du PES ne garantissent
pas à elles seules la coupe réelle sur toutes les machines.

## Contrôle après couture

1. Enregistrer le tissu, fil supérieur, canette, aiguille, stabilisateur,
   éventuel film, tension et paramètres JSON. Utiliser une chute du tissu cible.
2. Examiner après désencerclage et retrait du support prévu : bords plats,
   courbes sans amas de piqûres, fils de canette invisibles en surface, zones
   opaques sans tissu apparent, contreforme libre et fils de saut coupés.
3. Mesurer colonne droite, grand tatami et contour de la contreforme. Comparer
   aux dimensions source, pas à la seule image de preview.
4. Si le tissu fronce, contrôler d'abord encerclage, support et tension ; ne pas
   densifier automatiquement. Si la sous-couche paraît, augmenter son retrait ou
   corriger la couverture supérieure. Une perte de largeur dans l'axe des points
   justifie une petite correction de compensation, par exemple 0,05 mm par côté.
5. Ne modifier qu'un paramètre à la fois et recoudre le coupon. Une zone large
   est remplie en tatami ; augmenter la largeur satin pour éviter ce choix peut
   créer des flottés longs ou des piqûres au milieu du satin.

Les ajustements de densité se font avec `--stitch-spacing` et `--fill-spacing`.
Un pas plus petit ajoute des rangées et davantage de pénétrations. Les valeurs
extrêmes sont bornées par défaut ; pour une calibration explicite, utiliser
`--no-auto-adjust` et vérifier les valeurs effectives/demandées dans le JSON. Ne pas faire
croire qu'un simple passage plus dense corrige un tissu mal soutenu.

Les quatre combinaisons stable/40, stretch/40, textured/30 et stable/60 sont
vérifiées numériquement sur ce coupon : trois fils, deux changements, longueur
maximale bornée, pas de points courts et coordonnées PES/DST exactement conservées.
**Aucun coupon n'a encore été cousu dans cette validation.** Les résultats observés
sur tissu devront être ajoutés ici avant de qualifier un preset de calibré.
