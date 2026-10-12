# Direct digitizing

`generate(input, output, params, *, method="inkstitch", stitch_params=None)`
remains the public entry point. Default library/CLI calls preserve the original
SVG workflow. `direct` and `both` add machine points without desktop dependencies.
Python 3.10 is the packaging minimum required by the native SVG renderer.

## Colors and source geometry

`colors.py` assigns disjoint visible pixels to ordered thread colors. Flat interior
paints retain exact RGB values, including similar colors and small accents.
Antialiased edges are assigned in Lab space. Photos/gradients use bounded
median-cut quantization from weighted quantiles of the complete RGB histogram.
Palette discovery is invariant under pixel order, flips and quarter turns;
thin isolated accents are retained without turning blended edges into threads. Palette discovery and nearest-color assignment are
bounded/chunked; the default maximum is 12, configurable from 1 to 32.

Automatic bitmap preparation preserves alpha, removes a uniform opaque perimeter
background, crops margins and traces separate even-odd color contours.
Manual threshold/inversion and explicit monochrome mode retain silhouette tracing.
SVG white paint is a real thread color, not an implicit transparent background.
Rendered visible colors respect SVG compositing: covered paint is not embroidered
again as a full hidden layer. Large visible regions sew first, small accents last.

`digitizer.py` renders the prepared SVG at approximately 305 DPI, bounded by
4 MP/4096 pixels. Each color has its own deterministic MAT and source mask.
Regions are planned in canonical local frames, then mapped back to the **shared
physical machine frame** for a single quantization. Local row/stagger origins
follow the region, so moving it does not change its sewing pattern.
The original Ink/Stitch rails are still generated separately with their historical
settings. Color-aware MAT work is necessary; it is not reused from a merged mask.

## One top strategy per region

`selection.py` chooses on complete connected source/color components:

- Satin uses useful paired rails with sufficient swept coverage and suitable
  width. Slender almost-convex columns can use clipped parallel cross sections,
  avoiding raster skeleton fans at straight ends.
- The widest cross-section must respect the satin width throughout the column,
  with compensation and rounding headroom below the machine length cap. A width
  percentile cannot conceal a broad cap. Manual split satin remains available.
- The quantized candidate must cover at least 99.9% structurally, leave no gap
  larger than 0.05 mm², contain no unsafe connectors or detected crowded satin
  penetrations, in the actual sewing direction. Routing preserves that accepted local phase;
  the final source-frame candidate is checked again after machine rounding.
- Fine running candidates are also checked for complete source coverage.
- Failed or unsuitable candidates become **whole-source tatami**, preserving
  boundaries and holes. There are no residual fill patches mixed into satin.

Tatami uses a region-local row grid, staggered needle positions, source-clipped
rows and contour finishing. Its automatic angle comes from analytical moments
of the filled area, subtracting holes, rounded to 15° bands. Near-isotropic
regions (principal moment ratio ≤1.2) retain the configured default. This replaces
a travel-cost search sensitive to row phase and design size. Manual angles remain
in the original design frame. Compensation is bounded
by region area/perimeter to avoid bloating thin branched shapes. It sweeps the
boundary along the chosen stitch direction, without adding perpendicular rows.
A 0.12 mm inset
finish is preferred; if it leaves a structural gap, a source-edge finish is used
with the same fill strategy. Original hole interiors remain excluded even when
the outer boundary receives compensation.

Compact submillimeter details can use a principal clipped running chord. When
necessary, its ends extend by at most 0.08 mm each to retain the minimum machine
stitch length. This bounded fidelity adjustment is recorded and warned about;
unrepresentable detail is not claimed to be perfectly reconstructed.
Unsewable connected components are explicitly omitted and warned about, with an
`omitted_regions` count and an `omitted` decision. A color with no sewn segment
is omitted with an explicit warning and zero coverage; it is retained in the
area-weighted quality audit. Generation fails only when no color remains sewable.
Isolated needle penetrations cannot become successful exports.

Manual `auto_select=False` retains the original rail-based split/fill controls
and optional broad residual fill. It reports its coverage without automatic
repair. `fill_gaps` controls that manual path only.

## Equivalent regions and symmetry

`regions.py` isolates four-connected components: corner contacts alone do not
join two sewing regions. Each component is normalized under translation,
quarter turns and reflections before contour simplification, MAT and stitch
placement. Identical raster silhouettes receive identical local computation.

Near matches must retain hole topology, stay within two pixels in bounding
size/boundary distance, differ by at most 3% in area and 6% in their aligned
masks. A ±1 pixel alignment search resolves odd/even raster bounds. Detected
colored design symmetries (≤2% label disagreement) disambiguate intrinsic
orientation ties; the Union Jack uses its half-turn, without inventing mirror
symmetry. Quarter-turn matches are the supported discrete symmetry group;
arbitrary-angle rotational motifs are not yet explicitly grouped.

`consistency.py` assigns one policy to a cohort of equivalent regions: method,
local fill angle, spacing, bounded compensation, underlay profile and contour
finish. Every original outline is retained and audited separately in the shared
machine frame. If one counterpart fails the strict satin gate, the whole cohort
uses fill. It does not hide a faulty satin with patches or relax crowding limits.
Foundations use the conservative common profile; tiny regions avoid added bulk.
The final decision records `equivalence_group`, `equivalent_regions`,
`underlay_strategy` and `actual_top_metrics` alongside individual diagnostics.

Whole regions are ordered for travel, preserving their internal sewing direction
and foundation/top-layer order. Point coordinates/counts need not be exact clones
when the rasterized outlines differ or the machine grid has a different phase.
Resizing can legitimately change stitch type at physical safety/width limits;
matching counterparts still share a method at each size.

## Satin, routing and machine invariants

Satin is sampled by the larger local arc advance of its two rails. Penetrations
alternate at half the requested same-edge row pitch. Deterministic short-stitch
inset bands reduce stationary inner-corner crowding. Wide strands are split with
staggered phases; pull compensation is bounded by local width. Underlay is a
center walk plus coarse inset zigzag on sufficiently wide columns.
Stretch and textured fabrics also receive inset edge walks on columns at least
2.5 mm wide. Sparse zigzag pitch is 3 mm normally, 2.5 mm on stretch and 2 mm on
textured fabric.

`underlay.py` keeps fill foundations 0.3–0.5 mm inside the source according to
thread weight (0.2 mm fallback if the region vanishes). A contour anchors larger
pieces; sparse perpendicular rows support the surface at 3 mm pitch, or 2 mm on
stretch/textured fabrics. Regions below 4 mm² avoid this duplicate foundation.
These thresholds control edge visibility and bulk; they are conservative starting
values to calibrate through a sew-out, not a simulated fabric response.

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
After rounding/filtering, every run is checked again for safe geometry. The last
cap is retained when the preceding short step can be replaced safely; unsafe
chords split into needle-up moves. Runs with fewer than two penetrations vanish
before command emission, and their missing regions remain visible in diagnostics.

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
The machine dropdown uses server-owned profiles. `for_fabric(...,
machine="brother-skitch-pp1")` proposes six threads/7 mm satin and validates the
verified 100 × 100 mm area. Generic hoops and explicit recommendations are still
editable. No undocumented PP1 stitch-count limit is assumed; `max_stitches` is
the application resource budget. Stretch fabrics without cutaway and unstable
fabrics without underlay trigger advice before sewing.

## Evidence and limits

See [quality report](QUALITY_REPORT.md), [architecture](ARCHITECTURE.md) and
[before/after measurements](benchmarks/consistent-digitizing.json). Tests cover colored
SVG/PNG, transparency, overlaps, intentional holes, pale/similar paints, bounded
gradients, coherent strategies, curved/narrow tapered satin, quantized density,
machine limits, budget errors, API/CLI compatibility and PES/DST round trips.

Presets propose editable density, compensation and underlay for fabric/thread;
stabilizer choice is recorded, not mechanically simulated. Photo semantics,
thread tension, fabric deformation, thread spread and globally optimal routing
are not modeled. Tiny designs may require enlargement. A Brother sew-out remains
necessary to establish physical quality; valid files and near-complete geometric
coverage cannot prove perfect embroidery for every image.
Use [SEWOUT.md](SEWOUT.md) for the three-color test coupon, material controls and
Brother import/cutting workflow.

Reference: [Ink/Stitch satin parameters](https://inkstitch.org/docs/stitches/satin-column/)
and [pyembroidery serialization](https://github.com/EmbroidePy/pyembroidery/blob/main/README.md).
