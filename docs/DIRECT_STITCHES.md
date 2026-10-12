# Dual pipeline: design and quality evidence

Version: 0.3.0. Default generation and its four SVGs are preserved.
The minimum remains Python 3.10 because resvg-py 0.5 requires it.

## Architecture

`generate(input, output, params, *, method="inkstitch", stitch_params=None)` is
the single public entry point. Existing positional arguments and result fields
are unchanged. Default calls never calculate machine points. Direct/both modes
reuse the same rendered mask, deterministic MAT, routed paired rails and running
paths, then calculate a separate physical stitch plan before publishing files.

- `inputs.py`: common bitmap tracing, physical sizing and opt-in hoop fitting.
- `pipeline.py`: shared geometry, existing SVG outputs and staged writes.
- `stitching/params.py`: validated physical settings and material presets.
- `stitching/paths.py`: satin/running/tatami sampling and underlay.
- `stitching/planner.py`: locks, safe connectors, jumps/trims, quantization,
  resource/hoop limits and final geometric invariants.
- `stitching/export.py`: raster-to-mm transform, residual fills, PES/DST and previews.
- `stitching/selection.py`: complete satin/fill candidates on connected source regions.
- `stitching/quality.py`: thread-footprint diagnostics shared with comparisons.
- `stitching/coverage.py`: source-clipped repairs after quantization and coverage feedback.
- CLI, packaged web API and Next.js UI: adapters around the same entry point.

Engine internals live in `stitching/`; obsolete compatibility modules and the
root web launcher have been removed. See the [directory map](ARCHITECTURE.md).
No second MAT pass or desktop subprocess is needed. A bounded, finer SVG render
audits the actual stitch footprint at about 12 pixels/mm when the MAT mask is coarser.
Rung density remains independent of machine density. All four editable SVGs are
retained in direct mode as useful geometry diagnostics.

## Algorithm decisions

Satin uses paired-rail interpolation, parameterized by the greater local arc
length of the two rails. The requested row pitch bounds outer-edge gaps; each
successive penetration advances half a pitch and alternates rails. Inner-rail
crowding is handled with short stitches inset into the column rather than
repeatedly piercing a stationary corner. Pull compensation extends both rails,
bounded by local width. Long strands are split with staggered phases.

Satin underlay is a center walk and, for widths of at least 3 mm, an inset coarse
zigzag in the reverse direction. Running paths retain bends before subdivision.
Automatic selection compares complete satin and full-source tatami when regions
are broad or poorly covered. The satin candidate includes qualifying residual
fills before scoring, avoiding an unfair comparison with a complete fill. Whole-source fills preserve contours/holes and avoid MAT patch
seams; well-covered tapered columns can retain split satin. Tatami uses staggered
needle positions, an absolute row grid and sparse cross-row underlay. Intersections clip rows
to polygons with holes. Direct auto retains narrow rails instead of discarding
their widths: approximately 0.6 mm columns with 40 wt thread can use fine satin.
The limit varies with thread weight and minimum stitch length. Finer features
remain running. The legacy Ink/Stitch 1.5 mm cutoff and SVG outputs are preserved.
Residual fills precede satin and receive no extra compensation or duplicate
underlay against adjacent regions. Manual mode retains the original broad-gap fallback.

After quantization, a separate audit detects actual source pixels more than
0.25 mm from the thread, excluding intentional holes and regular row spacing.
At most two repair passes add source-clipped fills or skeleton runs for narrow
blanks, with a 0.3 mm seam overlap and no extra underlay. A repair is accepted
only if measured missing area decreases. Failed repairs preserve the valid plan
and report the reason. `fill_gaps=False` or `auto_select=False` disables automatic
repairs. Export statistics include structural coverage, largest blank area and
measurement resolution; significant remaining blanks produce warnings.

Existing bounded routing supplies the region order. Short connectors are sewn
only when the whole connector lies within allowed regions. Underlay passes within
the same region may connect over two running lengths before a covering top layer;
inter-region travel retains the configured trim distance. Longer/outside
connectors get locks, trims and needle-up jumps. A trim finishes the plan.
No machine-specific automatic density or tie command is delegated to the writer.

Positions are quantized to integer tenths of a millimetre before preview/export.
Near-duplicate sequential penetrations are removed; long segments reserve room
for coordinate rounding. The final sewn segments must satisfy the configured
maximum length and stay in buffered stitch regions (0.08 mm quantization
tolerance). Unsafe pre-quantization connections are split and reported; unsafe
post-quantization plans fail with clear feedback. Actual dimensions must fit the
configured hoop. Physical resizing occurs only when `design_width_mm` or
`fit_to_hoop` is requested; the web UI enables proportional hoop fitting by default.
The original input file is preserved. Rasterization uses a uniform resvg zoom,
preventing rounded dimensions from compressing very narrow SVGs.

Ambiguous candidates use actual 0.1 mm plans, including underlay and travel.
The geometric cost is `10 × missing_structural_fraction + max(0, spill/area − .08)
+ .01 × trims + .000002 × stitches + .003 × unsafe_connections` at processing
resolution. Structural coverage allows 0.25 mm distance from a 0.3 mm thread
footprint. Candidates must be within 0.25 percentage points of the best structural
coverage before the cost ranks them. These explicit heuristic weights balance gaps and fragmentation;
they are not learned or calibrated against physical sew-outs. Regular columns
avoid candidate search. Decisions retain features, metrics and failures.

The default 0.4 mm spacing, 0.15 mm compensation and underlay are starting values.
`StitchParams.for_fabric()` and UI material/thread choices propose adjustable
initial settings; stabilizer choice is recorded. They are not experimentally
calibrated fabric profiles. Explicit overrides and manual stitch-type/angle
controls remain available. Fill rows prefer nearby safe endpoints, penalize outside/long transitions and
retain the previous ordering if its transition cost is lower. This reduces
repeated jumps across holes without making the routing globally optimal.

## Dependencies

[pyembroidery](https://github.com/EmbroidePy/pyembroidery) 1.5.1 handles PES v6 and
extended DST serialization. The application owns the stitches and gives the
writer integer positions with encoding/resampling disabled. DST trims use the
writer's three-jump convention. PES reads may expose additional trim commands
from PEC jump encoding; sewn point coordinates remain identical.

[stitch_generator](https://github.com/bastanja/stitch_generator) was evaluated.
Its generic boundary satin calculation would still need this application's
crowding/underlay/travel/quantization logic. Direct NumPy sampling preserves our
actual paired rails and avoids an extra decorative-path abstraction and unused
noise dependency. It is therefore not required.

## Verification

Tests cover straight and curved physical density, inner-corner short stitches,
pull compensation, tapered caps, curve-preserving running stitches, clipped
tatami and residual fills with holes, underlay, maximum/minimum length checks,
separate regions without sewn bridges, hoop/budget limits and invalid settings.

Every example is generated as PES and DST, read back with pyembroidery, and its
entire sequence of sewn coordinates compared exactly with the JSON plan.
Existing SVG bytes are compared between original/both modes. Injected writer
failure leaves existing SVG/machine outputs intact. Web tests check both methods,
attachments, previews, invalid input and absence of native-tool calls. A browser
upload exercises the JavaScript comparison and downloads, beyond Flask tests.

Reproduce:

```bash
uv sync --frozen --extra dev --extra web
uv run pytest -q
uv run embroidery-rungs examples/satin-demo.svg --method both --auto-optimize -o output/comparison --json
uv run embroidery-rungs examples/direct-quality.svg --method both -o output/quality --json
pnpm install --frozen-lockfile
pnpm dev
```

`examples/direct-quality.svg` includes curved/ring satin, a thin running stroke,
wide fill with a hole and a taper. Machine round trips check digital validity;
the preview does not model thread tension, fabric deformation or embroidery speed.

## Remaining limits

This is a monochrome silhouette PoC, not universal full-color photo digitization.
Source colors/overlapping layers are flattened into a silhouette. Complex corners,
tiny tips, MAT branch boundaries and changes between fill/satin can still show
seams or need manual intervention. Short-stitch distribution and residual fills
are heuristics; region routing is not globally optimal. Geometric checks bound
faults they can detect, not physical stitching outcomes. The hoop limit is an
extent check, not a machine-specific hoop catalog or machine capability profile.

Native Ink/Stitch 3.3.0 has now been executed on all 28 comparison SVGs, using its
official portable macOS engine. Native zigzag underlay has a separate maximum
length: web export now configures both top/underlay limits and object trims.
Zero-length inner fan rails receive a paired-node repair inside the source
(maximum 0.02 mm nominal inner rail) for native SVG recognition. Direct fan
geometry remains unchanged. Native files are read back and actual length
violations are reported. See [quality evidence](QUALITY_REPORT.md). A Brother
sew-out has not been executed.
Verify PES/DST trim behavior and tune material-specific settings on
the target machine. Perfect fault-free embroidery from every arbitrary SVG/photo
cannot be established by file validation alone.
