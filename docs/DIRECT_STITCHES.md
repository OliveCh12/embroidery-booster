# Direct stitch generation

The automatic engine converts interpreted SVG geometry into physical paths,
then machine commands. No external digitizer calculates the stitches. The
library, CLI and web application all call `generate()` and the same direct
export. Internal rails are geometry candidates, not editable output artifacts.

## Physical interpretation and colours

SVGs render through resvg at 305 DPI, subject to a bounded raster budget. SVG
transforms, clipping and overlap determine the visible colour regions. The
palette preserves flat colours or quantizes gradients/photos through a stable
RGB histogram and Lab assignment; it does not recognize objects in a photo.
Colour areas are processed largest first, then their connected regions are
routed locally. Each colour is stitched once with explicit colour changes.

Inputs with more than 4096 visible connected regions fail before costly geometry
work. The error asks for simplification or colour reduction; no region is silently
dropped to meet this budget.

Bitmap tracing precedes this step. Explicit alpha takes priority; a sufficiently
uniform opaque perimeter background can be removed. The first GIF/TIFF frame is
used. Cropping and contour simplification have physical bounds. The interpreted
SVG is exported for inspection, since background removal and palette reduction
can change the intended artwork. [Input interpretation](INPUT_INTERPRETATION.md)
documents Auto/Keep/Remove, preservation of enclosed white paint, compressed-flat
palette recovery and the optional 0.10 mm² adjacent-speckle cleanup. Background
removal floods only from the border, rather than globally erasing a colour.

## Predictable region decisions

Foreground uses four-connectivity and hole topology uses the dual
eight-connected background. Each component is placed in a deterministic local
frame among quarter turns and reflections before medial-axis extraction and
stitch decisions. Broad compact regions are sent directly to tatami, avoiding
unnecessary skeleton work. Auto still evaluates elongated strokes with
area/diameter² ≥3 and diameter ≤2× the satin width recommendation. Explicit
Satin evaluates the rails regardless of region width.
Coordinates and stitch angles are transformed back before
shared machine quantization; global routing does not reverse an audited satin
path again.

Exact rigid equivalents share their policy. Conservative approximate cohorts
allow at most two raster pixels of boundary discrepancy, 3% area difference and
6% mask disagreement, with matching hole topology. Regions retain their own
outlines and actual coverage audits. Detected design symmetry provides an
alignment cue; it does not impose reflection symmetry on asymmetric artwork
such as the Union Jack, whose relevant symmetry is a half turn.

`StitchParams.stitch_type` selects `auto` (default), `satin`, `fill` or `running`.
The automatic top strategy is coherent per connected colour region:

- **Running:** fine details below the useful satin width, only when the actual
  sewn path retains structural coverage. The starting width threshold is
  `max(2 × min_stitch_mm, 0.75/0.6/0.45 mm for 30/40/60 wt)`.
- **Satin:** suitable columns whose rails cover the shape and remain within the
  physical float limit. The candidate must pass actual top-layer coverage,
  safe-connection and zero-crowding checks in its emitted direction.
- **Tatami:** broad, branched or otherwise unsuitable satin regions. Clipped
  rows cover the whole region while retaining counters and holes. A failing
  satin candidate is replaced as a region, never patched with another top type.

Equivalent counterparts receive a common safe choice, even if one individual
candidate fails after machine rounding. Automatic fill direction uses filled
area moments, including holes, rounded to 15° bands. Near-round shapes retain
the configured direction in their canonical frame. An explicit fill angle stays
in the global design frame and can override automatic angles.

If fill occupies at least 70% of a colour's substantive area (regions ≥4 mm²),
compact solid satin companions ≥4 mm² and area/width² <3 also receive fill.
Columns, curved lettering, counters and tiny regions keep their geometric
choice. Substantive fill cohorts share the colour's direction in their canonical
frames; small fill details retain their own geometry-derived direction.

Explicit **Satin** requires safe satin throughout and fails on inadequate
coverage, crowding or missing regions after column division. Explicit **Fill** uses
tatami on every sewable region without a medial-axis pass. Explicit **Running**
uses broad contours or fine centre lines and reports solid coverage honestly.
Material auto-adjustment and stitch-type selection are independent controls.

## Bounded material adjustments

`StitchParams.for_fabric()` proposes row pitches of 0.4 mm for custom/stable,
0.45 mm for stretch and 0.35 mm for textured fabrics. Thread-weight multipliers
are 1.25 / 1.0 / 0.75 for 30 / 40 / 60 wt. With `auto_adjust=True`,
`analysis.adjust_for_sewing()` bounds requests consistently across the design:

| Parameter | Automatic rule |
|---|---|
| Satin / fill row pitch | 0.7–1.5 × reference for custom; 0.8–1.25 × reference for other fabrics; never below 0.2 mm |
| Underlay | enabled for stretch and textured fabrics |
| Pull compensation per side | capped at 0.25 mm custom/stable, 0.35 mm stretch, 0.30 mm textured |
| Maximum satin width | bounded by the machine recommendation and the stitch length remaining after compensation plus 0.2 mm rounding headroom |

Ordinary preset values remain unchanged. Requested parameters, effective
parameters and each adjustment reason are exported separately. Setting
`auto_adjust=False` or CLI `--no-auto-adjust` preserves explicit values, while
validation and candidate safety checks remain active. These bounds are
conservative project policies, not measured properties of a particular fabric.
Stabilizer choice is recorded and supports useful warnings; it is not a
calibrated deformation model.

## Satin, tatami and foundations

Satin follows physical cross-sections with row pitch controlled on both rails;
curvature handling limits crowding of inner penetrations. Straight elongated
convex regions can use parallel cross-sections to avoid unstable medial-axis
fans. Pull compensation extends the two sides within bounded allowed geometry.
The automatic engine reserves compensation/rounding headroom before the maximum
stitch length. A wide sweep can become adjacent satin columns, retaining the
outer rails. Inner seams receive bounded overlap and, on nearly straight rails,
a small deterministic stagger to avoid a straight perforation line. Each column
reserves compensation and rounding headroom, and the complete top layer is
audited for coverage, unsafe connections and crowding. Auto restricts division
to elongated geometry up to twice the width recommendation; forced Satin can
attempt wider sweeps but never bypasses these audits or silently switches to fill.
Decisions report `split_satin_columns` and `safe_satin_width_mm` (rail width,
before compensation); the measured maximum machine stitch remains a separate
limit. Internal seams can affect sheen and need a physical sew-out.

Tatami rows clip to the region and its holes, stagger penetrations and use
bounded segment lengths. Edge finishing uses a small inset when its machine-grid
coverage is sufficient; otherwise the region uses rows reaching the boundary.
Compensation follows row direction and is reduced for fine or narrow shapes.

Satin underlay uses a centre walk, plus sparse zigzag on widths of at least 3 mm.
Stretch/textured columns add edge support when the lower width quartile is at
least 2.5 mm. Tatami foundations use sparse cross rows, with edge support on
sufficiently large inset interiors. Their inset is 0.5 / 0.4 / 0.3 mm for
30 / 40 / 60 wt, and cross spacing is 2 mm for stretch/textured or 3 mm otherwise.
Regions below 4 mm² do not receive fill foundations. If a cohort member cannot
emit actual supporting stitches after rounding, foundation is disabled for the
whole cohort and metadata reflects this. More penetrations are not assumed to
improve tiny details.

## Machine plan and output

### Automatic alternatives

`generate(..., compare_strategies=True)` compares a bounded set using the same
interpreted image, physical scale, palette and textile settings. **Balanced**
retains the ordinary regional/coherent-colour policy. **Satin preferred** can
evaluate additional rail sweeps and retain suitable satin companions instead
of unifying them with a filled body; it never bypasses machine-grid audits and
falls back to tatami for incomplete or crowded columns. **Uniform fill** uses
tatami with the requested global fill angle on all sewable surfaces.
**All satin** requires complete satin coverage and reports failures separately.
**Running outlines** sew contours rather than solid surfaces and cannot win the
surface recommendation. Exact duplicates retain all equivalent strategy names.

When medial-axis rails fail, strict satin and satin-preferred Auto can evaluate
up to six deterministic directional decompositions, each bounded to 64 paired
rail columns per region. Sweep topology events separate branches and preserve
holes. Large compact regions remain tatami in ordinary Auto; forcing satin does
not remove width, crowding or coverage checks. The fallback audit uses the final
artwork frame and 0.1 mm machine grid. Inner fans and narrow caps shorten or
skip penetrations only when the resulting top stitches retain audited coverage.

Prepared visible labels and canonical geometry are reused, with lazy medial
axes cached per region. Stitches, underlay and their quality measurements are
rebuilt independently. Exact command/palette duplicates produce one export.
A fully qualified all-satin plan also fulfills the strict-satin comparison
without repeating its geometry and machine audit.
An unsuccessful alternative does not discard a successful primary plan.
Explicit Satin/Fill/Running requests do not trigger variants.
Above 256 visible colour regions, comparison retains just balanced and reports
the uncomputed policies. This deterministic operational budget bounds repeated
candidate/cohort/colour audits; it is not a machine limit or a sewing threshold.
The original 4096-region input budget and explicit modes are unchanged.

Recommendations compare actual safety and coverage diagnostics first; a safe
satin gain is an aesthetic preference only among qualified alternatives.
They do not optimize thread count into a supposed beauty metric or increase
density to mask deficient geometry. The balanced plan wins equivalent choices.
An explicit `density_percent` (80–120, web default 100) divides the material's reference row pitch
by the requested percentage. It is idempotent across shared preparation and
digitizing; thread weight and fabric retain their physical spacing bounds.
Without this request (`None`), existing library/CLI spacing is preserved within
material bounds. Explicit 100 resets to the material reference, including after
a manual spacing change. Manual spacing takes precedence when automatic adjustment is disabled. Density
modifies the top layer, not the number of foundations. This follows the principle
of [satin density relative to a preset](https://docs.wilcom.com/embroiderystudio/27/en/OnlineHelp/Digitizing/stitches/stitches-8.htm)
and [joint fabric, underlay and compensation settings](https://docs.wilcom.com/embroiderystudio/28/en/OnlineHelp/Digitizing/properties/properties-9.htm).
Common image ambiguities and all remaining omissions remain visible in the
diagnostics. Physical stitch appearance still requires material-specific sewing
validation, as commercial
[auto-digitizing documentation also explains](https://help.wilcom.com/portal/en/kb/wilcom-international/embroidery-web-api/faqs/articles/autodigitizing-concept).

Paths return to one physical artwork frame before their coordinates round to
integer **0.1 mm** positions. All colours share the same origin. Final commands
are centred in the hoop; compensated and rounded bounds are checked against
its dimensions. Explicit needle-up jumps, trims, locks, colour changes and END
commands are encoded by pyembroidery into PES v6 and extended DST without writer
resampling. Empty or unsewable designs fail clearly.

Locks are verified after their own machine rounding. On a fine stepped edge,
a short already-audited segment can replace an unsafe rounded anchor; an anchor
is never added outside the region to secure a thread. Geometric candidate errors
can trigger a cohort fallback or an explicitly diagnosed omission, while budget,
hoop and invalid-input errors remain fatal.

Tiny compact details may receive at most 0.08 mm extension per endpoint to keep
a legal sewn segment. The adjustment is reported. Details or entire colours
that remain unsewable are marked omitted and remain part of the coverage audit.

JSON **schema 3** contains `units`, `coordinate_frame`, `origin_mm`, exact
`commands`, command codes, hoop and machine limits, first stitch, playback
metadata, threads, settings, decisions and typed command ranges. `top_layer_runs`
separate satin/fill/running from underlay and travel. Playback follows the
commands; its duration counts needle cycles only. The Skitch profile uses
[Brother's 400 SPM and 100 × 100 mm specifications](https://www.brother-usa.com/p/sewing-embroidery/PP1).
The generic profile's 400 SPM is an explicit simulation assumption.

Travel and locks have their own command ranges. `analysis.stitch_breakdown`
counts top, underlay, sewn travel, lock and initial-entry penetrations exactly
once; the context node at each run's start is not another stitch. Underlay uses
the active thread colour and diameter in playback. Optional connections are
amber and locks violet; preview toggles do not alter machine commands. Static
SVG/PNG previews read the machine commands directly, including sewn support,
travel and locks in the active spool colour. Needle-up jumps are not drawn there.

## Quality evidence and limitations

`quality.py` audits the actual quantized top-layer runs. Underlay, locks and
stitched travel cannot conceal missing top stitches. The reference thread is
0.3 mm wide and structural tolerance is 0.25 mm. Candidate coverage of at least
99.9%, largest missing component at most 0.05 mm², and zero satin crowding gate
automatic satin. Final missing regions, unsafe connections and insufficient
coverage produce diagnostics and a review status.

These are geometric checks. They do not model tension, bobbin thread, needle,
acceleration, puckering or thread spread on fabric. Near-complete structural
coverage is not a promise of opaque sewn coverage. Verify the
[current measurements](QUALITY_REPORT.md) and use the [sew-out protocol](SEWOUT.md)
to calibrate a real material before production.
