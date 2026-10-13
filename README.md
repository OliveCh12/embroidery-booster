# Embroidery Booster

Generate **PES and DST embroidery directly from SVG or bitmap artwork**. The
application chooses satin, running stitches or tatami for each visible colour
region, then produces inspectable machine points. Automatic proposals compare
a balanced strategy, safe satin emphasis and uniform tatami on the same
interpreted artwork, with shared colours and material settings.

## Installation

Python **3.10+** is required by the SVG renderer. Development versions are pinned
in `.mise.toml`: Python 3.12, Node.js 24 and pnpm 12.4.2. Inkscape and Ink/Stitch
are not required.

```bash
git clone https://github.com/OliveCh12/embroidery-booster.git
cd embroidery-booster
uv sync --extra web --extra dev
pnpm install --frozen-lockfile
pnpm dev
```

Open <http://127.0.0.1:3000>. Import an SVG or image on the preview side by file
selection, drag-and-drop or clipboard paste. Choose its physical size, machine,
fabric, thread and stabilizer; generate, review the interpreted artwork and
stitch playback, then download PES. The floating **Fil/Fils** control lists thread passes with descriptive
colour names, stitch counts and estimated start times; HEX values are available
on hover. Select a pass to seek to its start. The compact Play/Pause control uses
**Continu** by default at **×150**, or **Par fil** to pause before the next colour.
Preview options contain simulation speed, command stepping and phase visibility.
**Détails** opens a right-hand panel for quality checks, warnings and logs.
Parameters are grouped into five collapsible sections, from design/hoop and
materials to stitch strategy, image interpretation and advanced settings.
The viewer uses the hoop and millimetre rulers directly, with separators instead
of a surrounding card. The canvas follows the applied HeroUI palette and displays
real thread colours by default. **Contraste** adapts only poorly visible colours
for on-screen reading (dark threads on dark fabric, pale threads on light fabric).
The list always shows real spool colours; machine files are unchanged. This display
choice persists when switching stitch variants. Turn it off to return to real colours.
Underlay uses the active thread colour and diameter, just like the machine;
it can be hidden to inspect the top layer. Optional travel/jump/lock markers
use technical colours. Static SVG/PNG previews show sewn thread only, using
the actual command order and spool changes, without needle-up jump lines.
In **Auto**, **Comparer les stratégies** generates qualified alternatives and
selects a recommendation. The compact variant selector switches playback,
diagnostics and PES/DST downloads together. Identical machine plans are shown
once; their equivalent strategies are listed in Détails. Turn comparison off
to generate just the usual balanced plan.
Thread weight is shared across all passes. Times exclude spool changes and travel. The interface has light, dark and system
modes. The header provides **Contribuer** (GitHub) and **Réglages**: save your
default machine, fabric profile, thread and stabilizer locally for the next
atelier. These defaults reuse the engine's current presets; artwork and machine
files are not stored in browser preferences. The workspace fills the available
height below the header, without a footer. See [frontend development](frontend/README.md) for separate processes and
production builds.

`pnpm dev` starts Next.js on port 3000 and the Python API on port 8000.
`FRONTEND_PORT` and `API_PORT` override them. Core-only installation: `uv sync`.
Build the Python wheel with `uv build`.

## Inputs and physical size

For logos, prefer the **original vector SVG**, or a crisp PNG with a transparent
background. A photo placed inside an SVG is not vector artwork. Before generating,
the web app analyses the interpreted image at its requested embroidery size:
useful pixels after background removal, thread-colour complexity and actual
physical dimensions. A suggested target for fine contours is **12 pixels/mm**
(about 305 dpi): roughly **960 useful pixels for an 80 mm motif**, excluding
blank margins. Lower-resolution simple graphics remain accepted; advice below
6 pixels/mm, and especially below 3, suggests a better original or a smaller
physical design. Source resolution does not determine stitch density, and
upsampling cannot recover lost details. See [source-quality rules and sources](docs/INPUT_INTERPRETATION.md#qualité-de-source-et-résolution-utile).

SVG dimensions, transforms, viewBoxes and intentional holes are preserved. Text
must be converted to vector paths; scripts, external resources and embedded
images are rejected. PDF, EPS, PS and AI must be exported to SVG before import.

PNG, JPEG, WebP, BMP, GIF and TIFF are traced locally. GIF/TIFF use the first
frame. EXIF orientation and embedded ICC profiles are normalized before colour
analysis; alpha and indexed PNG transparency are preserved. Invalid profiles
fall back to decoded colours with a diagnostic. **Auto background** removes only a sufficiently
uniform or smoothly varying background connected to the perimeter: a white badge enclosed by a
logo remains white embroidery. Choose **Keep** to retain a deliberate canvas or
**Remove** to explicitly attempt exterior removal. Background blending and codec
ringing at contours are refined before tracing, rather than becoming stray
embroidery regions. Ambiguous or textured photo backgrounds are kept by Auto;
this is not semantic object extraction. SVG Auto/Keep
retain explicit vector paints; SVG Remove rasterizes and retraces at the original
physical scale. Blank margins are cropped. Flat artwork retains its colours; photos
and gradients use a bounded palette, with 12 threads by default and six in the
Skitch preset. This is colour quantization, not semantic photo recognition.
Small adjacent colour speckles can be merged into a similar stable region;
transparent holes and isolated or contrasting details are preserved. This is
enabled by default and can be disabled. Diagnostics report changed area and
region counts. Review the interpreted SVG to confirm important details and
backgrounds. See [input interpretation](docs/INPUT_INTERPRETATION.md).

Bitmap tracing checks every interpreted paint and counter on its native pixel
grid. Simplification that alters this reference falls back to exact contours;
the diagnostics in **Détails** report the correction. This protects interpreted
geometry, while the separate machine audits still identify details too small
to sew at the requested size. See [tracing checks](docs/INPUT_INTERPRETATION.md#normalisation-et-contrôle-du-tracé).

Compressed flat artwork uses local colour-mixture evidence to clean tiny edge
fragments. Weak edge shades are assigned to locally supported paints rather
than borrowing an unrelated remote thread, such as black lettering beside a
blue/white badge. Détails reports the number of reassigned edge pixels. Literal
paints and real black accents remain protected.
For black/white logos, background-coloured pockets beside thick strokes
can be interpreted as transparent counters; thin outlined badges and multicolour
white paint are retained. This is a reported geometric inference, not object
recognition. Disable raster cleanup to retain the original interior paint.

Bitmap artwork defaults to an **80 mm longest side**. SVGs keep their original
size. `--design-width` sets the interpreted document width, while `--fit-to-hoop`
allows proportional shrinking to leave **1 mm per side**. The web interface
requests fitting by default; the library and CLI require the explicit option.
Actual compensated stitch bounds are also checked against the selected hoop.

## CLI

```bash
# Colour logo, automatically fitted to the chosen hoop
uv run embroidery-rungs logo.png --design-width 70 --fit-to-hoop --fabric stable -o output/logo

# Compare automatic stitch strategies on exactly the same artwork
uv run embroidery-rungs logo.png --machine brother-skitch-pp1 --fit-to-hoop --compare-strategies -o output/variants

# Brother Skitch PP1 and a reproducible material coupon
uv run embroidery-rungs examples/quality/sewout.svg --machine brother-skitch-pp1 --fabric stable --thread-weight 40 --stabilizer cutaway --fit-to-hoop -o output/sewout

# Explicit monochrome interpretation
uv run embroidery-rungs logo.png --single-color --thread-color '#176d9c'

# Keep an intentional background, with uniform tatami top stitches
uv run embroidery-rungs logo.png --background keep --stitch-type fill

# Require satin, dividing wide columns; unsuitable junctions still fail audits
uv run embroidery-rungs narrow-lettering.svg --stitch-type satin

# Keep every bitmap colour detail, or generate outline embroidery
uv run embroidery-rungs logo.png --no-raster-cleanup
uv run embroidery-rungs logo.svg --stitch-type running

# Expert settings without automatic material adjustments
uv run embroidery-rungs logo.svg --no-auto-adjust --stitch-spacing 0.45 --fill-spacing 0.45

uv run embroidery-rungs logo.svg --json
uv run embroidery-rungs --help
```

Automatic adjustment bounds excessively dense/sparse settings, compensation and
satin width, and enables underlay on stretch/textured fabrics. Requested and
effective values, with reasons, are included in the result. `--no-auto-adjust`
keeps explicit settings; geometric coverage, machine-length and hoop checks
still apply. Underlay may be omitted on a tiny region when it cannot form useful
support without excess penetrations.

| Control | Starting value | CLI |
|---|---:|---|
| Satin / fill row pitch | 0.4 / 0.4 mm | `--stitch-spacing`, `--fill-spacing` |
| Running stitch length | 2.5 mm | `--running-length` |
| Maximum stitch length | 8 mm | `--max-stitch` |
| Pull compensation per side | 0.15 mm | `--pull-compensation` |
| Maximum satin width | 8 mm before automatic bounds | `--max-satin-width` |
| Hoop | 100 × 100 mm | `--hoop-width`, `--hoop-height` |
| Thread palette | 12 colours | `--max-colors`, `--single-color` |
| Material | custom / 40 wt | `--fabric`, `--thread-weight`, `--stabilizer` |
| Fill direction | geometry-driven | `--fill-angle` overrides it |
| Bitmap silhouette | automatic | `--raster-threshold`, `--invert-image` |
| Background | automatic exterior removal | `--background auto/keep/remove` |
| Small colour speckles | bounded cleanup | `--no-raster-cleanup` disables it |
| Top stitch strategy | automatic geometry/coherence | `--stitch-type auto/satin/fill/running` |

`stable`, `stretch` and `textured` presets propose density and support for 30,
40 or 60 wt thread. They are starting points, not calibrated fabric models.

## Library

```python
from embroidery_rungs import GenerationParams, StitchParams, generate

result = generate(
    "logo.png",
    "output/logo",
    GenerationParams(design_width_mm=70, fit_to_hoop=True, background_mode="auto"),
    stitch_params=StitchParams.for_fabric(
        "stretch",
        thread_weight=40,
        stabilizer="cutaway",
        machine="brother-skitch-pp1",
        density_percent=100,
    ),
    compare_strategies=True,
)
print(result.direct.pes_path, result.direct.dst_path)
print(result.artwork_size_mm, result.direct.stats)
print(result.direct.params, result.direct.adjustments)
print(result.direct.decisions, result.direct.threads)
print(result.input_analysis, result.direct.analysis["stitch_breakdown"])
print(result.recommended_variant)
for variant in result.variants:
    print(variant.id, variant.direct.pes_path, variant.quality, variant.reasons)
```

`generate(input, output, params)` keeps its three positional arguments.
`GenerationParams` contains `design_width_mm`, `fit_to_hoop`,
`raster_threshold`, `raster_invert`, `background_mode` and `raster_cleanup`.
Set `StitchParams(stitch_type="fill")` for uniform tatami, or pass `stitch_type`
to `StitchParams.for_fabric()`. `GenerationResult.direct` is mandatory;
`input_path` identifies the untouched source and `original_path` the interpreted
SVG. Results also contain physical dimensions, input settings, warnings and
stage timings. Missing files raise `FileNotFoundError`, invalid inputs/settings
raise `ValueError`, and file errors raise `OSError`. Strict satin never silently
falls back to fill. Running outlines are intentionally not solid coverage.
Failed generation preserves
previous outputs.

Use `StitchParams(auto_strategy="satin_preferred")` to generate the satin-emphasis
Auto proposal alone. It retains tatami fallback and all safety checks. With
comparison enabled, the engine evaluates balanced Auto, satin-preferred Auto,
strict all-satin, uniform tatami and running outlines. Identical plans are
exported once and list their equivalent strategies. Running outlines remain a
deliberate contour style and are never recommended as a solid surface.

Strict satin can divide branched silhouettes into paired directional rails
when the medial axis leaves caps or junctions uncovered. Wide rails become
adjacent safe-width columns; every candidate still passes the final machine-grid
coverage and penetration checks. It never disguises tatami as satin. Genuinely
unsewable details or excessive decomposition still produce an explicit refusal.

Set `density_percent=80` through `120` (web default `100`) or CLI
`--density-percent 110` to adjust surface density relative to the fabric/thread
preset. Higher percentages put rows closer together. With `auto_adjust=False`,
explicit satin/fill spacing takes precedence.
Without a density request (`None`), existing library/CLI spacing is preserved
within material bounds; explicit `100` selects the material's reference pitch.
Density does not add extra underlay layers, and it is not a 3D-puff setting: foam embroidery needs dedicated
construction and a physical sew-out.

**Migration from 0.3:** editable rail/rung exports and external embroidery
workflows have been removed. The API accepts only `method="direct"`, which is
the default. CLI `--method`, rung `--spacing`/`--density`/`--dpi`, optimizer/debug
options, external-preview controls and manual gap-fill switches are removed.
Use `result.direct.stats` instead of the old rung/column counts or coverage
fields. `StitchParams.auto_select`/`fill_gaps` are replaced by the unified engine
and `auto_adjust`. A lower-level `build_stitch_plan()` remains available for
explicit physical paths; it does not interpret SVGs.

## Outputs and machine playback

Each successful generation produces:

- `design_artwork.svg`: interpreted artwork at the requested physical size.
- `design_direct.pes`: PES v6, with thread colours and colour changes.
- `design_direct.dst`: extended DST.
- `design_direct.svg` and `.png`: stitch previews.
- `design_direct.json`: exact commands, decisions, diagnostics and settings.

JSON **schema 3** stores integer coordinates in **0.1 mm**, centred in the hoop.
It declares command codes, hoop/machine bounds, first stitch, colour changes,
and command ranges for top stitches, underlay, sewn travel and locks. Exact needle
counts distinguish these phases in `analysis.stitch_breakdown`. Machine files are
encoded with [pyembroidery](https://github.com/EmbroidePy/pyembroidery); round-trip
tests verify sewn coordinates. Playback follows these commands and displays
needle-up travel. Underlay in the active thread colour can be hidden; themed connections, jumps and
locks share a separate visibility control. Its timing counts needle cycles only, excluding manual thread
changes, machine acceleration and cutting.

Brother specifies the [Skitch PP1](https://www.brother-usa.com/p/sewing-embroidery/PP1)
for **100 × 100 mm** embroidery at **400 stitches/minute**, through Artspira.
The web interface starts with this profile; the library/CLI retain their generic
default. The preset validates the hoop limit; its six-colour palette and 7 mm
satin width are project recommendations. Satin and tatami can follow each other
in one PES without changing a machine stitch mode: they are needle coordinates.
Only a thread-colour change requires a new spool on the single-needle PP1.
[Artspira imports PES and DST](https://support.brother.com/g/s/hf/mobileapp_info/artspira/plan/func1/en.html);
availability depends on the account and region. Use PES for its thread metadata.
Follow the [physical sew-out protocol](docs/SEWOUT.md) before using a new material.

## Engine and validation

Mixing satin and tatami in one design is a standard digitizing practice:
satin gives borders and lettering sheen, while tatami stabilizes broad surfaces.
The choice should follow each region's geometry and the intended texture.
[Wilcom demonstrates this combination](https://wilcom.com/resources/blog/mastering-basic-stitch-types-satin-stitch-and-tatami-stitch).
The engine keeps one top-layer strategy per connected region rather than
patching incomplete satin with a different stitch type.

Optional comparison evaluates **balanced**, **satin_preferred** and
**uniform_fill**. The satin proposal attempts more complete columns but keeps
the same coverage, float-length, crowding and symmetry controls; unsuitable
regions still use tatami. Uniform fill uses the configured global tatami angle.
Image interpretation, thread palette, physical scale and material parameters
are shared, as are reusable geometric analyses and skeletons. Every resulting
plan is checked independently after machine rounding. The recommendation
favours qualified coverage and machine geometry before a safe satin gain;
balanced wins when no meaningful improvement is demonstrated. Stitch count is
a workload measurement, not a beauty score. Failed alternatives are reported
without invalidating a successful primary plan.

Above **256 visible colour regions**, comparison generates only the balanced
plan and reports the uncomputed alternatives. This operational budget avoids
repeating costly independent audits on very fragmented images; it does not
change the design, thread palette, density or the 4096-region input limit.
Explicit stitch modes remain available. Reduce colour count or image noise to
compare a less fragmented interpretation.

`compare_strategies=False` remains the library/CLI default. Explicit Satin,
Fill and Running requests retain their existing meaning and generate one plan.
The recommended candidate keeps the normal `design_direct.*` filenames;
distinct alternatives use `design_<strategy>_direct.*`. A comparison may still
require review: an image cannot reveal the user's intended treatment of every
colour pocket or predict fabric deformation. A sew-out remains the way to
qualify physical appearance and settings on the PP1.

In Auto, each connected colour region uses one coherent top strategy. Colours
dominated by broad fill regions also use fill for compact solid companions;
narrow columns, lettering and counters retain their useful satin treatment.
Explicit Fill applies tatami throughout; explicit Satin requires audited columns
throughout, dividing broad sweeps into adjacent satin columns when needed.
Automatic selection considers this division for elongated strokes up to twice
the width recommendation, while broad solid bodies retain tatami. Satin candidates
must pass coverage/crowding checks on the final machine grid and honour the
maximum stitch length; unsuitable regions receive clipped tatami in Auto. Fine details use
running stitches where they retain coverage. Rigidly equivalent regions share
strategy, density, direction, compensation and underlay policy, while retaining
their original outlines. Unsewable details are reported rather than silently
removed from quality measurements.

Audits measure exported **top stitches only**. The reference model uses a 0.3 mm
thread and 0.25 mm structural tolerance; near-complete geometric coverage does
not demonstrate sewn opacity or simulate fabric deformation. Stitch playback
is a preview of machine commands, not a fabric simulation. No physical sew-out
has yet validated these presets.

See [algorithm rules](docs/DIRECT_STITCHES.md), [architecture](docs/ARCHITECTURE.md)
and the [current quality report](docs/QUALITY_REPORT.md). The `/quality` gallery
reads reproducible artifacts from `output/quality`.

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
pnpm check
pnpm test:frontend
pnpm build
uv run python scripts/compare_quality.py --design-width-mm 80
uv run python scripts/benchmark_direct.py --design-width-mm 80
uv build
```

The Flask API runs independently with `uv run embroidery-rungs-web --host
127.0.0.1 --port 8000`. `POST /api/convert` accepts multipart artwork and direct
settings; `GET /api/capabilities` supplies formats, machine profiles and material
presets. The API bounds uploads to 10 MiB, bitmaps to 16 MP and simultaneous jobs
to two. Jobs live under `output/web`; `EMBROIDERY_OUTPUT_DIR` overrides storage.
Next.js proxies API/download requests on the same origin. Public deployments
need access control and a storage-retention policy.
