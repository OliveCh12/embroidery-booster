# Direct digitizing

`generate(input, output, params, *, method="inkstitch", stitch_params=None)`
remains the public entry point. Default library/CLI calls preserve the original
SVG workflow. `direct` and `both` add machine points without desktop dependencies.
Python 3.10 is the packaging minimum required by the native SVG renderer.

## Colors and source geometry

`colors.py` assigns disjoint visible pixels to ordered thread colors. Flat interior
paints retain exact RGB values, including similar colors and small accents.
Antialiased edges are assigned in Lab space. Photos/gradients use bounded
median-cut quantization. Palette discovery and nearest-color assignment are
bounded/chunked; the default maximum is 12, configurable from 1 to 32.

Automatic bitmap preparation preserves alpha, removes a uniform opaque perimeter
background, crops margins and traces separate even-odd color contours.
Manual threshold/inversion and explicit monochrome mode retain silhouette tracing.
SVG white paint is a real thread color, not an implicit transparent background.
Rendered visible colors respect SVG compositing: covered paint is not embroidered
again as a full hidden layer. Large visible regions sew first, small accents last.

`digitizer.py` renders the prepared SVG at approximately 305 DPI, bounded by
4 MP/4096 pixels. Each color has its own deterministic MAT and source mask.
Rails and connected components remain in a **shared physical frame and row grid**.
The original Ink/Stitch rails are still generated separately with their historical
settings. Color-aware MAT work is necessary; it is not reused from a merged mask.

## One top strategy per region

`selection.py` chooses on complete connected source/color components:

- Satin uses useful paired rails with sufficient swept coverage and suitable
  width. Slender almost-convex columns can use clipped parallel cross sections,
  avoiding raster skeleton fans at straight ends.
- The quantized candidate must cover at least 99.9% structurally, leave no gap
  larger than 0.05 mm², contain no unsafe connectors or detected crowded satin
  penetrations, and pass the same checks in **both sewing directions**.
- Fine running candidates are also checked for complete source coverage.
- Failed or unsuitable candidates become **whole-source tatami**, preserving
  boundaries and holes. There are no residual fill patches mixed into satin.

Tatami uses an absolute row grid, staggered needle positions, source-clipped rows,
automatically selected direction and contour finishing. Compensation is bounded
by region area/perimeter to avoid bloating thin branched shapes. A 0.12 mm inset
finish is preferred; if it leaves a structural gap, a source-edge finish is used
with the same fill strategy. Original hole interiors remain excluded even when
the outer boundary receives compensation.

Compact submillimeter details can use a principal clipped running chord. When
necessary, its ends extend by at most 0.08 mm each to retain the minimum machine
stitch length. This bounded fidelity adjustment is recorded and warned about;
unrepresentable detail is not claimed to be perfectly reconstructed.

Manual `auto_select=False` retains the original rail-based split/fill controls
and optional broad residual fill. It reports its coverage without automatic
repair. `fill_gaps` controls that manual path only.

## Satin, routing and machine invariants

Satin is sampled by the larger local arc advance of its two rails. Penetrations
alternate at half the requested same-edge row pitch. Deterministic short-stitch
inset bands reduce stationary inner-corner crowding. Wide strands are split with
staggered phases; pull compensation is bounded by local width. Underlay is a
center walk plus coarse inset zigzag on sufficiently wide columns.

`planner.py` orders regions and checks connectors against allowed geometry.
Outside/long travel uses locks, trims and bounded needle-up jumps. Very short
inter-region travel is also treated explicitly, so a nearby small detail cannot
silently lose its first stitch. In-region underlay travel may connect before a
covering top layer. The plan ends with a trim and one END command.

Each color plan uses the same machine origin. Merging preserves its command
ranges, retains terminal trims, inserts real `COLOR_CHANGE` commands and routes
between layers. Actual sewn bounds are centered using an **integer coordinate
shift**, avoiding a second quantization. Combined hoop and command budgets are
checked; sewn coordinates are integer tenths of a millimeter before export.
Existing minimum/maximum length and allowed-region checks remain mandatory.

`pyembroidery` serializes PES v6 and extended DST with stitch resampling disabled.
Thread lists follow color changes; both formats are read back in regression tests
and all sewn coordinates must match the JSON plan exactly. PES readers can expose
additional trims from PEC jumps; DST uses the writer's trim convention.

## Honest quality diagnostics

`quality.py` audits **only actual exported satin/fill/running blocks** for the
automatic engine. Underlay, locks and sewn travel cannot fill the quality mask.
JSON schema 2 records `coverage_basis="quantized_top_layer"`, per-color `layers`,
ordered `threads` and exact `top_layer_runs` command ranges. Empty top layers
report zero coverage. Manual diagnostics explicitly use `all_sewn_stitches`.

The reference footprint is 0.3 mm thread. Raw coverage, IoU and spill have no
structural tolerance. Structural coverage permits source pixels within 0.25 mm
of the footprint, distinguishing regular row spacing from substantial blanks.
Per-color checks prevent one thread from hiding a missing region of another.
Crowding checks inspect repeated local satin penetrations beyond adjacent points,
with a 0.05 mm rounding tolerance; intentional endpoint tie proximity is excluded.

The preview shows actual thread colors, gray underlay and dashed jumps. The web
UI exposes color preservation/palette limits, ordered swatches and top-layer
coverage. The comparison gallery retains a common all-sewn footprint for native
comparability and also displays the direct engine's separate top-layer audit.

## Evidence and limits

See [quality report](QUALITY_REPORT.md), [architecture](ARCHITECTURE.md) and
[before/after measurements](benchmarks/direct-top-layer.json). Tests cover colored
SVG/PNG, transparency, overlaps, intentional holes, pale/similar paints, bounded
gradients, coherent strategies, curved/narrow tapered satin, quantized density,
machine limits, budget errors, API/CLI compatibility and PES/DST round trips.

Presets propose editable density, compensation and underlay for fabric/thread;
stabilizer choice is recorded, not mechanically simulated. Photo semantics,
thread tension, fabric deformation, thread spread and globally optimal routing
are not modeled. Tiny designs may require enlargement. A Brother sew-out remains
necessary to establish physical quality; valid files and near-complete geometric
coverage cannot prove perfect embroidery for every image.

Reference: [Ink/Stitch satin parameters](https://inkstitch.org/docs/stitches/satin-column/)
and [pyembroidery serialization](https://github.com/EmbroidePy/pyembroidery/blob/main/README.md).
