# Embroidery Booster

Automatically turn an SVG or bitmap into **PES / DST stitches**, or
editable **Ink/Stitch satin columns**. Both paths share a deterministic Medial
Axis Transform and the same `generate()` entry point.

**Recommended workflow:** direct automatic generation, with the actual design
size, fabric and thread selected by the user. Keep Ink/Stitch for inspection and
manual finishing. The library and CLI retain `inkstitch` as their default for
backward compatibility; the web UI defaults to direct generation.

## Install and run

Python **3.10+** is required by the native SVG renderer; development uses 3.12.
The application uses **Node.js 24**, **pnpm 12.4.2**, Next.js **16.4** and HeroUI **3.2**.
No Inkscape or Ink/Stitch installation is needed for direct generation.

```bash
git clone https://github.com/OliveCh12/embroidery-booster.git
cd embroidery-booster
uv sync --extra web
pnpm install --frozen-lockfile
pnpm dev
```

Open <http://127.0.0.1:3000>, upload an SVG or image, choose its physical size,
hoop, fabric, thread weight and stabilizer, then generate. Review the interpreted
artwork and stitch preview before downloading PES or DST. Choose **Comparer
les deux moteurs** to inspect both approaches side by side. Real native stitch previews
and native machine downloads are available when Ink/Stitch is installed.

Core only: `uv sync`. Development: `uv sync --frozen --extra dev --extra web`.
A normal installation also works: `python -m pip install ".[web]"`.
Build distributable packages with `uv build`. `.mise.toml` and `.envrc` support
mise and direnv without requiring them.

`pnpm dev` runs the Next.js application on port 3000 and the Python API on port
8000. `FRONTEND_PORT` and `API_PORT` override these ports together. The app includes
light, dark and system themes, responsive controls and a comparison gallery.
See [frontend development](frontend/README.md) for separate processes and production builds.

## Input and sizing

SVGs retain their physical size unless resizing is requested. Transforms,
shifted viewBoxes, separate components and holes are preserved. Convert text to
paths and remove unwanted backgrounds first.

PNG, JPEG, WebP, TIFF, GIF and BMP use local tracing in the library, CLI and web
UI. Direct automatic generation separates visible colors, preserves alpha and
removes a uniform opaque perimeter background. Flat logo colors retain their RGB
values; photos and gradients use a bounded thread palette (12 colors by default).
Blank margins are cropped, intentional holes are preserved and the default
longest side is **80 mm**. Inspect the interpreted artwork before sewing.

The original Ink/Stitch and manual paths retain monochrome silhouette tracing.
Explicit threshold/inversion or `--single-color` also selects monochrome tracing.
PDF/EPS/PS/AI require Inkscape. Photo quantization does not reconstruct the subject
or guarantee stitchable photographic detail.

`design_width_mm` / `--design-width` sets the prepared document width in mm.
`fit_to_hoop` / `--fit-to-hoop` permits proportional shrinking to the selected
hoop with a margin. The UI enables fitting by default; library/CLI calls do not
resize implicitly. Actual compensated stitch bounds are checked separately.

## CLI

```bash
# Automatic machine stitches from an image
uv run embroidery-rungs logo.png --method direct --design-width 70 --fit-to-hoop --fabric stretch --thread-weight 40 --stabilizer cutaway --auto-optimize

# Both export paths from the same prepared artwork
uv run embroidery-rungs examples/direct-quality.svg --method both --auto-optimize -o output/comparison

# Preserve logo colors, export Brother PES and DST
uv run embroidery-rungs examples/quality/multicolor.svg --method direct --max-colors 8 -o output/color-logo

# Skitch PP1: 100 × 100 mm, practical palette and satin recommendations
uv run embroidery-rungs examples/quality/sewout.svg --method direct --machine brother-skitch-pp1 --fabric stable --thread-weight 40 --stabilizer cutaway --fit-to-hoop -o output/sewout-cotton

# Explicit monochrome override
uv run embroidery-rungs logo.png --method direct --single-color --thread-color '#176d9c'

# Existing editable Ink/Stitch workflow
uv run embroidery-rungs examples/satin-demo.svg --auto-optimize -o output/rails

# Machine-readable result
uv run embroidery-rungs logo.svg --method direct --json
uv run embroidery-rungs --help
```

The automatic direct engine uses **one top stitch strategy per connected color
region**: regular satin for suitable columns, running stitches for fine details,
or whole-region clipped tatami for broad, branched or incompletely covered shapes.
Satin candidates must pass coverage and crowding checks in both sewing directions.
It never patches a deficient satin region with a different top stitch type.
Small compact details can receive a bounded minimum-length adjustment, reported
in warnings. Decisions and candidate diagnostics are recorded in JSON.
Details that cannot form a sewn segment after machine rounding are explicitly
marked `omitted`; an entirely unsewable design fails with an enlargement message.

| Setting | Default | CLI |
|---|---:|---|
| Satin same-edge row pitch | 0.4 mm | `--stitch-spacing` |
| Fill row pitch | 0.4 mm | `--fill-spacing` |
| Pull compensation per rail | 0.15 mm | `--pull-compensation` |
| Running length | 2.5 mm | `--running-length` |
| Maximum sewn segment | 8 mm | `--max-stitch` |
| Maximum automatic satin width | 8 mm | `--max-satin-width` |
| Underlay | enabled | `--no-underlay` |
| Hoop | 100 × 100 mm | `--hoop-width`, `--hoop-height` |
| Automatic stitch-type selection | enabled | `--no-auto-select` |
| Automatic fill angle | enabled | explicit `--fill-angle` overrides it |
| Maximum thread colors | 12 | `--max-colors` |
| Preserve visible colors | enabled in auto | `--single-color` disables it |
| Bitmap threshold | automatic | `--raster-threshold`, `--invert-image` |
| Machine profile | custom hoop | `--machine generic\|brother-skitch-pp1` |

`--wide-mode split|fill` explicitly switches to manual per-rail selection.
`--spacing`, `--density` and `--auto-optimize` control **direction guides**,
independently of machine stitch density. `--debug` saves geometry diagnostics;
`--preview` optionally opens Inkscape. `--no-preview` remains accepted.

## Library

```python
from embroidery_rungs import GenerationParams, StitchParams, generate

settings = StitchParams.for_fabric(
    "stretch", thread_weight=40, stabilizer="cutaway",
    machine="brother-skitch-pp1",
    hoop_width_mm=100, hoop_height_mm=100,
)
result = generate(
    "logo.png", "output/logo",
    GenerationParams(auto_optimize=True, design_width_mm=70, fit_to_hoop=True),
    method="direct",  # "inkstitch" (existing default), "direct", or "both"
    stitch_params=settings,
)
print(result.direct.pes_path, result.direct.dst_path)
print(result.artwork_size_mm, result.direct.stats)
print(result.direct.decisions, result.warnings)
print(result.direct.threads)  # ordered RGB palette; PES contains color changes
```

Set `preserve_colors=False, thread_color="#176d9c"` on `StitchParams` for a
monochrome direct plan. `max_colors` bounds the palette from 1 to 32.

Presets `custom`, `stable`, `stretch` and `textured`, plus thread weights 30/40/60,
propose editable density, compensation and underlay. The server owns these values;
the UI uses the same presets. Explicit numeric overrides take precedence.
Stabilizer selection is recorded; it is not a calibrated mechanical model.
Fill pull compensation extends along the sewn rows, retaining intentional holes.
Its underlay is inset, with edge support and sparse cross rows; unstable fabrics
receive closer support. Auto satin reserves room for compensation and rounding
before the maximum stitch length, avoiding split penetrations across its face.

The Skitch factory preset proposes six thread colors and a 7 mm satin width;
these are editable recommendations. Its **100 × 100 mm** hoop limit is validated
even with manual overrides, following the [Brother specifications](https://www.brother-usa.com/p/sewing-embroidery/PP1).
The Skitch uses Artspira: import the generated **PES** (or DST), rather than the
source SVG. [Artspira supports these embroidery formats](https://support.brother.com/g/s/hf/mobileapp_info/artspira/plan/func1/en.html);
import availability depends on the account/region. Enable Jump Stitch Trimming
in the machine settings; PES trim commands alone do not prove physical cutting.
See the [sew-out protocol](docs/SEWOUT.md) and the reproducible three-color coupon.

The original positional API and result fields remain available. `direct` is
`None` for original-only calls. Added fields include warnings, stage timings and
prepared document dimensions. Missing files raise `FileNotFoundError`, invalid
inputs/settings raise `ValueError`, and file failures raise `OSError`.
Generation validates and stages outputs before publication.

## Outputs

Every method retains the existing SVG outputs:

- `design.svg`: original SVG copy, or the prepared bitmap regions. If an input already
  occupies this output path and is resized, `design_prepared.svg` preserves it.
- `design_rungs.svg`: direction guides.
- `design_ready.svg`: artwork with editable guides.
- `design_satin.svg`: ordered paired-node satin columns and running paths.

Direct generation adds `design_direct.pes`, `.dst`, `.json`, `.svg` and `.png`.
JSON schema 2 stores exact integer positions in **0.1 mm**, commands, ordered
threads, per-color diagnostics, effective parameters, region decisions and warnings.
`top_layer_runs` identifies the exported top stitches independently of underlay
and travel. PES v6 and extended DST are encoded with
[pyembroidery](https://github.com/EmbroidePy/pyembroidery). The preview uses the
source thread colors with gray underlay; dotted lines indicate needle-up travel.
Sewn coordinates round-trip exactly through both machine formats in tests.

The application calculates its own points with NumPy and geometric checks.
It does not delegate direct generation to another stitch calculator.
See [direct algorithm details](docs/DIRECT_STITCHES.md).

## Optional Ink/Stitch

Open `design_satin.svg` in Inkscape and adjust it with Ink/Stitch. Paired rails
use its documented [node method](https://inkstitch.org/docs/stitches/satin-column/).
Explicit guides remain in the other SVGs. Native export in the comparison UI
applies the selected material settings, top/underlay length controls and trims.
The configured SVG is also downloadable.

Set `INKSCAPE_BIN` / `INKSTITCH_BIN`, or put the executables on `PATH`. Standard
macOS installation paths are detected. Helper scripts remain available:

```bash
uv run bash scripts/inkstitch_preview.sh output/rails/satin-demo_satin.svg
uv run bash scripts/run_inkstitch.sh output/rails/satin-demo_satin.svg output/rails/design.zip
```

A native export failure leaves the editable SVGs available with a clear warning.
The app reads native PES statistics and flags excessive actual stitch lengths.

## Web and API

Next.js owns the interface in `frontend/`; Flask remains a standalone Python
API, served by Waitress without debug mode on localhost by default. The Python
wheel contains the library, CLI and API. Run the interface from the repository:

```bash
pnpm dev
# API only, for library integrations or a separately managed frontend:
uv run embroidery-rungs-web --host 127.0.0.1 --port 8000
```

Limits: 10 MiB uploads, 16 MP bitmaps, two simultaneous jobs, persistent UUID
folders under `output/web/`. `EMBROIDERY_OUTPUT_DIR` changes storage.
For public deployment, provide access control in front of the local application.

`POST /api/convert` accepts multipart `file`, `method`, `design_width`,
`fit_to_hoop`, `fabric`, `thread_weight`, `stabilizer` and generation settings.
API default remains `method=inkstitch`; boolean values use `true` / `false`.
Responses retain `files`, `preview`, `stats`, `params`, `warnings` and `logs`,
and add `artwork_preview`, `artwork_svg`, `artwork_size_mm` and optional `direct`.
Invalid inputs return 400, oversized uploads 413, busy workers 503.
`GET /api/capabilities` exposes optional tools and shared material presets.
Next.js proxies these endpoints and downloads on the same origin; no public API
URL or CORS configuration is needed. The API root returns service metadata.

## Quality evidence and development

The reproducible corpus contains **29 SVGs**: curves, corners, tapers, rings,
holes, junctions, tiny islands, multicolor artwork and complex logos. At a common
document width of 80 mm, the new direct engine improves mean top-layer structural
coverage from **99.966% to 99.999%**, with the largest missing component falling
from **0.20 to 0.01 mm²**. Underlay, locks and travel cannot hide missing top stitches.

Structural coverage uses a 0.3 mm reference thread and **0.25 mm tolerance**;
it does not mean pixel-perfect coverage or a validated physical sew-out. Coherent
tatami selection lowers raw IoU in some cases and increases cuts. The report
includes those tradeoffs, per-color audits and a separate native Ink/Stitch
comparison on our generated rails. Significant remaining issues produce warnings.

See the [quality report](docs/QUALITY_REPORT.md), [raw measurements](docs/quality-comparison.json),
[architecture](docs/ARCHITECTURE.md) and [initial engineering audit](docs/AUDIT.md).

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
pnpm check
pnpm test:frontend
pnpm build
uv run python scripts/compare_quality.py --inkstitch /path/to/inkstitch
uv run python scripts/compare_quality.py --reuse
uv run python scripts/compare_quality.py --output output/quality-80mm --design-width-mm 80 --modes direct-auto
uv run python scripts/benchmark_direct.py --baseline-ref 6b6c756 --design-width-mm 80
uv build
```

Generated previews and plans live in `output/`, outside source control. The
application comparison gallery is at `/quality`, reading generated JSON and previews.
Historical MAT timing snapshots are in `docs/benchmarks/`.

Tiny details, sharp branch transitions and dense motifs can still require
finishing. Geometric checks and valid machine files do not simulate tension,
fabric deformation or thread spread. A sew-out on the chosen material remains
necessary to establish physical rendition; arbitrary photos cannot be promised
perfect automatic embroidery.
