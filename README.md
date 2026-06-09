# Embroidery Auto Rung Generator

Automatic rung placement for embroidery satins. It uses the **Medial Axis
Transform (MAT)** to generate optimal rung patterns from an SVG shape, ready to
finish in Inkscape / Ink-Stitch.

## Features

- **Library-first**: a single `generate()` entry point; the CLI and web UI are thin clients.
- **Automatic optimization**: searches spacing/density for a clean result (≤25 rungs, no intersections).
- **Web interface**: drag-and-drop SVG upload with live preview and debug images.
- **Command line**: full manual control over spacing, density, and DPI.
- **Debug visualization**: skeleton, distance map, graph, and coverage overlays.

## Project structure

```
stich/
├── pyproject.toml              # packaging, dependencies, CLI entry point
├── src/
│   └── embroidery_rungs/       # the package
│       ├── __init__.py         # public API: generate(), GenerationParams, GenerationResult
│       ├── pipeline.py         # core orchestration (the one entry point)
│       ├── optimizer.py        # automatic parameter search
│       ├── cli.py              # command-line wrapper
│       ├── svg_manager.py      # SVG load / save / open
│       ├── image_processor.py  # rasterization + medial axis
│       ├── rung_generator.py   # rung placement algorithm
│       ├── geometry_utils.py   # skeleton graph + geometry helpers
│       └── debug_utils.py      # debug image generation
├── web/                        # Flask web interface (thin client of the package)
│   ├── app.py
│   └── index.html
├── examples/                   # sample SVG inputs
├── notebooks/                  # exploration notebooks
└── scripts/                    # helper scripts (e.g. Ink/Stitch export)
```

Generated files go to `output/` (git-ignored), never into the source tree.

## Installation

Requires Python ≥ 3.9 and [Inkscape](https://inkscape.org/) (for high-precision
rasterization; a pure-PIL fallback is used if Inkscape is absent).

```bash
python -m venv venv && source venv/bin/activate
pip install -e .          # core (CLI + library)
pip install -e ".[web]"   # also install the web server
```

## Usage

### Library

```python
from embroidery_rungs import generate, GenerationParams

result = generate("examples/nike.svg",
                  params=GenerationParams(auto_optimize=True, debug=True))
print(result.rungs_count, result.bridges_count, result.coverage)
```

### Command line

```bash
# Auto-optimized
embroidery-rungs examples/nike.svg --auto-optimize --debug

# Manual parameters
embroidery-rungs examples/nike.svg --spacing 3.0 --density 1.0 --debug

# (equivalent module form)
python -m embroidery_rungs.cli examples/nike.svg --auto-optimize
```

### Web interface

```bash
cd web
python app.py
```

Then open <http://localhost:8000>.

## Parameters

| Parameter         | Default | Description                                  |
|-------------------|---------|----------------------------------------------|
| `--spacing`       | `3.0`   | Rung spacing in mm                           |
| `--density`       | `1.0`   | Density multiplier (higher = more rungs)     |
| `--dpi`           | `150`   | Processing DPI (higher = better quality)     |
| `--output-dir`    | `output`| Where generated files are written            |
| `--auto-optimize` | off     | Search for optimal spacing/density           |
| `--debug`         | off     | Save debug images                            |
| `--no-preview`    | off     | Don't open Inkscape automatically            |
| `--verbose`       | off     | Verbose logging                              |

## Output files

For input `example.svg`, the following appear in the output directory:

- `example.svg` — copy of the original
- `example_rungs.svg` — rungs only (visual guide)
- `example_ready.svg` — original + rungs, ready to edit in Inkscape
- `example_satin.svg` — **Ink/Stitch satin columns**, machine-ready

Debug images are written to `output/debug/` when `--debug` is set.

## Ink/Stitch satin & preview

`example_satin.svg` contains real Ink/Stitch *satin columns* (two rails built
from the rung endpoints), tagged so Ink/Stitch stitches them as satin — no
manual conversion needed.

To preview the stitches (or export embroidery files) headlessly on macOS:

```bash
# Renders <name>_plan.svg + <name>_plan.png (the rendered stitch plan)
scripts/inkstitch_preview.sh output/example_satin.svg

# Also export .dst/.pes/threadlist
ZIP=1 scripts/inkstitch_preview.sh output/example_satin.svg
```

The script drives Ink/Stitch's bundled binary (`--extension=stitch_plan_preview`
/ `--extension=zip`) and Inkscape's CLI — there is no REST API, but both run
headless. The satin columns are automatically ordered (nearest-neighbour + 2-opt)
to minimize travel/jump stitches between them, so the design stitches in an
efficient sequence out of the box.

## Algorithm

1. **Load** — parse SVG paths and extract endpoints.
2. **Rasterize** — render to a high-resolution binary mask (Inkscape, PIL fallback).
3. **Skeletonize** — compute the medial axis with scikit-image.
4. **Generate rungs** — place rungs along the skeleton with curvature-adaptive spacing.
5. **Optimize** (optional) — try candidate configs to minimize intersections and maximize coverage.

## Dependencies

`numpy`, `scipy`, `scikit-image`, `pillow`, `svgelements`, `networkx`; plus
`flask` for the web UI, and Inkscape for rasterization.
