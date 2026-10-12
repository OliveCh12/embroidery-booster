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

L’import reste dans le panneau d’aperçu : glisser-déposer, sélection de fichier
ou collage avec Ctrl+V / Cmd+V après avoir cliqué dans la zone. SVG, PNG, JPEG,
WebP, TIFF, GIF et BMP sont acceptés jusqu’à 10 Mio. Un import invalide conserve
le dessin et les résultats précédents.

Les réglages occupent le panneau gauche : machine, cadre physique en millimètres,
taille du dessin, tissu, fil et stabilisateur. L’ajustement automatique adapte
les paramètres au dessin et au matériau. Les réglages effectivement appliqués,
leurs modifications et les mesures de couverture figurent dans les détails du
résultat. Désactiver l’ajustement permet de régler les points manuellement.

Le type de points peut rester en **Auto**, ou être fixé à Satin, Tatami ou Point
droit. Le satin forcé est refusé si la région ne permet pas une couverture
régulière dans les limites de la machine. Le point droit convient aux lignes
fines ; il ne remplit pas un aplat.

Dans « Interprétation de l’image », **Fond : Auto / Conserver / Supprimer**
contrôle le fond relié au bord, en préservant les aplats intérieurs. Auto conserve
un bord ambigu ; les couleurs explicites d’un SVG sont préservées. Supprimer
sur un SVG effectue une conversion contrôlée du dessin. « Réduire les parasites »
nettoie les petits îlots raster selon leur taille physique ; désactiver cette
option conserve tous les détails de couleur. Les détails du résultat indiquent
le fond réellement traité, les nuances de compression consolidées, le nombre
d’îlots avant/après et la surface modifiée. Le nombre de nuances de l’image est
distingué du nombre de couleurs de fil retenues.

La simulation lit les commandes du **plan machine schema 3**, à 0,1 mm près :
points, déplacements aiguille levée, coupes et changements de fil. Le dessin
reste centré dans son cadre physique ; la grille et les graduations sont en
millimètres, espacées de 10 mm. Pendant la lecture, le premier point est vert et
l’aiguille rouge ; ces marqueurs disparaissent sur l’aperçu terminé.
Le lecteur propose deux actions explicites : **Tout lire** traverse tous les
changements de couleur ; **Lire par fil** s'arrête avant de commencer la couleur
suivante et demande d'installer la bobine correspondante. Pause, retour au
départ, pas par commande, affichage complet et timeline restent disponibles.
La liste à gauche donne le nom descriptif, le HEX, le nombre de points et le
début estimé de chaque passage. Les noms ne sont pas des références fabricant.
Cliquer sur une ligne rejoint son début ; le passage actif reste visible dans
la liste. Sur les petites largeurs, cette liste passe sous le cadre.

Le titrage commun (30, 40 ou 60 wt) est affiché une fois pour tous les fils ;
le moteur ne prévoit pas de changement d'épaisseur en cours de broderie. Les
horaires de début et la durée totale comptent uniquement les cycles d'aiguille.

Le cadre, la grille, les graduations et les phases utilisent des contrastes
adaptés au thème clair/sombre. Le textile neutre garde visibles le noir et le
blanc sans changer les couleurs des fils. Le menu d’affichage distingue couverture
dans la couleur du fil, sous-couche neutre, liaisons cousues ambre, sauts pointillés
et ancrages violets. La sous-couche est masquable ; liaisons, sauts et ancrages
se masquent ensemble. Les détails de
qualité séparent le nombre de points de couverture, de sous-couche, de liaison
et d’ancrage ; les commandes machine et les exports restent identiques.

La cadence indicative est de 400 points/min, avec une accélération ×60 par défaut.
×1 représente uniquement les cycles d’aiguille ; le temps des déplacements,
coupes et changements manuels de fil n’est pas simulé. L’aperçu est géométrique :
il ne prédit pas la déformation du tissu. Contrôler un essai sur le support choisi.

Le rendu Canvas utilise des tableaux typés et ajoute seulement les nouveaux
segments pendant la lecture. Les déplacements sur la timeline sont recalculés
par blocs de 8 000 commandes pour conserver une interface réactive sur les grands
plans. Aucune liste de milliers de points React n’est créée.

À partir de 768 px, l’atelier occupe l’espace entre header et footer. Les paramètres
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
- `src/lib` : HTTP, erreurs et formatage.

La route `/quality` lit `output/quality/comparison.json` (schema 3) et les images
du corpus. Elle expose source, points exportés, empreinte et mesures de couverture.
Les tests Vitest couvrent import, réglages, erreurs HTTP, coordonnées physiques,
commandes machine, changements de fil et lecture. La CI vérifie types, lint,
tests et build. `pnpm check` génère d’abord les types Next.js ; `next-env.d.ts`
et `.next/` restent des fichiers de travail exclus de Git.
