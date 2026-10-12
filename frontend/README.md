# Interface Next.js

Next.js 16.4, React 19.3, HeroUI 3.2 et Tailwind 4.3. TypeScript strict,
TanStack Query pour les requêtes, `next-themes` pour clair / sombre / système.
Les composants suivent la [documentation HeroUI](https://heroui.com/en/docs/react/getting-started).

## Lancement

Depuis la racine, avec Node.js 24 et pnpm 12.4.2 :

```bash
uv sync --extra web
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrir <http://127.0.0.1:3000>. L'API tourne sur le port 8000.
Pour changer les deux ports :

```bash
API_PORT=8766 FRONTEND_PORT=8765 pnpm dev
```

Pour des processus indépendants, lancer `uv run embroidery-rungs-web`, puis
`pnpm dev:frontend`. `frontend/.env.local` peut préciser `PYTHON_API_URL`, par
défaut `http://127.0.0.1:8000`. Cette URL reste côté serveur. Les rewrites Next.js
relaient les API, aperçus et téléchargements sur la même origine.

## Build et production

```bash
pnpm check
pnpm test:frontend
pnpm build
pnpm start
```

L'API doit aussi tourner. Pour une API sur une autre adresse, définir
`PYTHON_API_URL` **avant le build** ; les rewrites sont enregistrés pendant celui-ci.
Le serveur Python est distribué dans le wheel, l'application Next.js se déploie
séparément. Aucune installation d'Inkscape n'est nécessaire pour le moteur direct.

## Organisation

- `src/app` : routes, layout, providers et imports CSS.
- `src/components/layout` : navigation et thème partagés.
- `src/features/embroidery` : formulaire, réglages, import et résultats.
- `src/features/quality` : comparaison du corpus généré côté Python.
- `src/lib` : client HTTP, erreurs et formatage.

L'atelier conserve les téléchargements SVG, PES/DST et exports natifs optionnels.
Les densités par matériau proviennent de `/api/capabilities` ; elles ne sont pas
recopiées en JavaScript. Les résultats sont invalidés au changement de fichier.
Les aperçus utilisent un fond blanc pour distinguer le dessin de l'interface.

À partir de 768 px, l'atelier occupe la hauteur disponible entre le header et le
footer. Les réglages défilent séparément et le bouton de génération reste visible.
Les aperçus s'adaptent à l'espace restant ; les mesures et diagnostics sont
repliables. Sur mobile, les réglages sont repliés au départ et les panneaux
s'empilent. Les grands blocs partagent un espacement de 16 px.

La galerie `/quality` lit `output/quality-comparison/comparison.json` et les images
du même dossier. Si le corpus est absent, elle donne la commande pour le générer.
Les tests Vitest couvrent validation des fichiers, sérialisation des réglages,
presets et erreurs HTTP. La CI vérifie types, lint, tests et compilation production.
`pnpm check` génère d'abord les types Next.js ; `next-env.d.ts` et `.next/`
sont des fichiers de travail générés, exclus de Git et de l'archive source.
