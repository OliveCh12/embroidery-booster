# Interface Next.js

Next.js 16.4, React 19.3, HeroUI 3.2 et Tailwind 4.3. TypeScript strict,
TanStack Query pour les requêtes, `next-themes` pour clair / sombre / système.

## Lancement

Depuis la racine, avec Node.js 24 et pnpm 12.4.2 :

```bash
uv sync --extra web
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrir <http://127.0.0.1:3000>. L’API tourne sur le port 8000. Pour modifier les ports :

```bash
API_PORT=8766 FRONTEND_PORT=8765 pnpm dev
```

On peut aussi lancer `uv run embroidery-rungs-web`, puis `pnpm dev:frontend`.
`frontend/.env.local` peut préciser `PYTHON_API_URL`, par défaut
`http://127.0.0.1:8000`. Les rewrites Next.js relaient les API, aperçus et
fichiers sur la même origine. Pour une API différente en production, définir
cette variable **avant le build**.

```bash
pnpm check
pnpm test:frontend
pnpm build
pnpm start
```

Le serveur Python est distribué dans le wheel ; le frontend se déploie séparément.
Le moteur direct produit PES et DST sans application externe.

## Atelier

Le header donne accès à l’atelier, aux contrôles qualité, à **Réglages** et au
lien GitHub **Contribuer**. `/settings` enregistre dans ce navigateur la machine,
le profil de tissu, le fil et le stabilisateur par défaut. À l’ouverture de
l’atelier, les profils du moteur sont appliqués une seule fois ; les changements
effectués ensuite restent propres au dessin. Les images et les fichiers machine
ne font pas partie des préférences. L’apparence reprend le même thème que le
menu du header. **Réinitialiser** restaure les préférences de matériel d’origine.

L’import reste dans le panneau d’aperçu : glisser-déposer, sélection de fichier
ou collage avec Ctrl+V / Cmd+V après avoir cliqué dans la zone. SVG, PNG, JPEG,
WebP, TIFF, GIF et BMP sont acceptés jusqu’à 10 Mio. Un import invalide conserve
le dessin et les résultats précédents.

Les réglages occupent le panneau gauche : machine, cadre physique en millimètres,
taille du dessin, tissu, fil et stabilisateur.
Ces réglages sont classés en cinq sections repliables avec icônes et résumés :
dessin/cadre, tissu/fils, stratégie, interprétation et réglages avancés. Les deux
premières sont ouvertes au départ. Une erreur de validation ouvre sa section
et, sur mobile, le panneau de paramètres avant de focaliser le champ concerné.
L’ajustement automatique adapte
les paramètres au dessin et au matériau. Les réglages effectivement appliqués,
leurs modifications et les mesures de couverture figurent dans les détails du
résultat. Désactiver l’ajustement permet de régler les points manuellement.
La PP1 est sélectionnée par défaut, avec un cadre de 100 × 100 mm et six couleurs
maximum proposées. Satin et tatami peuvent se succéder dans le même fichier PES ;
le changement de bobine concerne la couleur, pas le type de points.

Le bouton **Détails**, dans l’en-tête de l’aperçu, ouvre un panneau à droite :
remarques, contrôles de qualité, interprétation du dessin, décisions par région,
fichiers de travail et journal. Il reste fermé par défaut pour laisser toute la
place au rendu. Son contenu défile indépendamment ; Échap ou le bouton de
fermeture ramène à l’aperçu. Un point discret signale les remarques à consulter.

Le type de points peut rester en **Auto**, ou être fixé à Satin, Tatami ou Point
droit. Les colonnes larges peuvent être divisées en satins adjacents ; le panneau
Détails les identifie comme **satin divisé**. Le satin forcé reste refusé si la
région échoue aux contrôles de couverture ou de piqûres serrées. Le point droit convient aux lignes
fines ; il ne remplit pas un aplat.

Dans « Interprétation de l’image », **Fond : Auto / Conserver / Supprimer**
contrôle le fond relié au bord, en préservant les aplats intérieurs. Auto conserve
un bord ambigu ; les couleurs explicites d’un SVG sont préservées. Supprimer
sur un SVG effectue une conversion contrôlée du dessin. « Réduire les parasites »
nettoie les petits îlots raster selon leur taille physique ; désactiver cette
option conserve tous les détails de couleur. Les détails du résultat indiquent
le fond réellement traité, les nuances de compression consolidées, le nombre
d’îlots avant/après et la surface modifiée. Les poches de fond entre traits épais
d’un logo noir/blanc peuvent devenir des évidements transparents ; cette
interprétation est signalée et se désactive avec le nettoyage. Les badges à
contour fin et les aplats blancs multicolores sont conservés. Le nombre de nuances de l’image est
distingué du nombre de couleurs de fil retenues.

La simulation lit les commandes du **plan machine schema 3**, à 0,1 mm près :
points, déplacements aiguille levée, coupes et changements de fil. Le dessin
reste centré dans son cadre physique ; la grille et les graduations sont en
millimètres, espacées de 10 mm. Pendant la lecture, le premier point est vert et
l’aiguille rouge ; ces marqueurs disparaissent sur l’aperçu terminé.
Le bouton **Lire / Pause** démarre en mode **Continu** à **×150**. **Continu** traverse tous les
changements de couleur ; **Par fil** s'arrête avant de commencer la couleur
suivante et signale la bobine à installer sans masquer le dessin. Retour au
départ, affichage complet et timeline restent disponibles sur une barre compacte.
Les options regroupent vitesse de simulation, affichage des couches et passage
à la commande suivante.
Le bouton flottant **Fil/Fils** ouvre une liste avec le nom descriptif, le nombre de points et le début estimé
de chaque passage ; le HEX reste consultable au survol. Les noms ne sont pas des
références fabricant.
Cliquer sur une ligne rejoint son début ; le passage actif reste visible dans
la liste. Elle reste repliée pour laisser toute la surface au cadre.

Le titrage commun (30, 40 ou 60 wt) est affiché une fois pour tous les fils ;
le moteur ne prévoit pas de changement d'épaisseur en cours de broderie. Les
horaires de début et la durée totale comptent uniquement les cycles d'aiguille.

Le cadre, la grille, les graduations et les phases utilisent les tokens du thème
HeroUI appliqué. Les couleurs réelles sont le défaut ; **Contraste** ajuste
uniquement les couleurs peu lisibles à l’écran. La liste affiche toujours les
vraies couleurs de fils et les exports restent inchangés.
Le menu d’affichage distingue couverture dans la couleur du fil, sous-couche
neutre, liaisons, sauts pointillés et ancrages. La sous-couche est masquable ; liaisons, sauts et ancrages
se masquent ensemble. Les détails de
qualité séparent le nombre de points de couverture, de sous-couche, de liaison
et d’ancrage ; les commandes machine et les exports restent identiques.

La cadence indicative est de 400 points/min, avec une accélération ×150 par défaut.
×1 représente uniquement les cycles d’aiguille ; le temps des déplacements,
coupes et changements manuels de fil n’est pas simulé. L’aperçu est géométrique :
il ne prédit pas la déformation du tissu. Contrôler un essai sur le support choisi.

Le rendu Canvas utilise des tableaux typés et ajoute seulement les nouveaux
segments pendant la lecture. Les déplacements sur la timeline sont recalculés
par blocs de 8 000 commandes pour conserver une interface réactive sur les grands
plans. Aucune liste de milliers de points React n’est créée.

À partir de 768 px, l’atelier occupe toute la hauteur disponible sous le header,
sans footer. Les paramètres
défilent séparément ; le bouton de génération et les exports PES/DST restent
accessibles. Sur mobile, l’import et la simulation précèdent les réglages repliés.
Les grands blocs utilisent un espacement de 16 px.

## Organisation et validation

- `src/app` : routes, layout, providers et CSS.
- `src/components/layout` : navigation et thème.
- `src/features/embroidery` : import, paramètres et résultats.
- `src/features/embroidery/stitch-player` : modèle du plan et séquence de fils,
  liste de passages, timeline, rendu Canvas et palette des thèmes.
- `src/features/quality` : contrôle du corpus direct généré côté Python.
- `src/features/preferences` : profils par défaut locaux et page Réglages.
- `src/lib` : HTTP, erreurs et formatage.

La route `/quality` lit `output/quality/comparison.json` (schema 3) et les images
du corpus. Elle expose source, points exportés, empreinte et mesures de couverture.
Les tests Vitest couvrent import, réglages, erreurs HTTP, coordonnées physiques,
commandes machine, changements de fil et lecture. La CI vérifie types, lint,
tests et build. `pnpm check` génère d’abord les types Next.js ; `next-env.d.ts`
et `.next/` restent des fichiers de travail exclus de Git.
