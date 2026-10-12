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

La simulation lit les commandes du **plan machine schema 3**, à 0,1 mm près :
points, déplacements aiguille levée, coupes et changements de fil. Le dessin
reste centré dans son cadre physique ; la grille et les graduations sont en
millimètres, espacées de 10 mm. Le premier point est vert, l’aiguille rouge.
Le lecteur propose lecture/pause, retour au départ, pas par commande, affichage
complet et déplacement sur la timeline. Il montre l’ordre des fils et peut
s’arrêter à chaque changement de couleur. Sous-couches et sauts sont affichables.

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
- `src/features/embroidery/stitch-player` : validation du plan, timeline et rendu Canvas.
- `src/features/quality` : contrôle du corpus direct généré côté Python.
- `src/lib` : HTTP, erreurs et formatage.

La route `/quality` lit `output/quality/comparison.json` (schema 3) et les images
du corpus. Elle expose source, points exportés, empreinte et mesures de couverture.
Les tests Vitest couvrent import, réglages, erreurs HTTP, coordonnées physiques,
commandes machine, changements de fil et lecture. La CI vérifie types, lint,
tests et build. `pnpm check` génère d’abord les types Next.js ; `next-env.d.ts`
et `.next/` restent des fichiers de travail exclus de Git.
