# Engineering audit and implementation evidence

Audited baseline: `2c5f643`. The review covered all package modules, CLI,
Flask app/services/UI, tests, examples, helper scripts, packaging, and notebook.
Implementation preserves `generate()`, `GenerationParams`, `GenerationResult`,
CLI processing options and the optional web upload/download workflow.

## Observed defects and changes

| Baseline finding | Consequence | Implemented change |
|---|---|---|
| `skeletonize(method='lee')` presented as MAT | Topological thinning is not a distance-ridge medial axis | Deterministic `medial_axis(..., return_distance=True, rng=0)` |
| Fixed 2,000-pixel hole removal and morphological closing | Erases intentional holes and merges nearby geometry | Preserve rendered mask topology; prune terminal MAT corner spurs relative to radius |
| 1,500-pixel minimum short side, up to 4,000 long side | Tiny designs become millions of pixels; requested DPI has little effect | Physical DPI with bounded 4 MP / 4096-side work; crop margins; minimum 256 long side for small documents |
| PIL draws every subpath as a filled polygon; curves sampled at 20 points | Compound-path holes, winding rules and detailed curves are wrong | Native resvg rendering of the actual XML, including fills/strokes/clips/transforms |
| Optional Inkscape writes shared `temp_raster.png` beside the input | Slow process launch, races, failure in read-only input directories | In-memory single render; core does not need desktop software |
| NetworkX node/edge objects for every skeleton pixel | Python object/graph overhead and duplicated neighbor edges | Vectorized neighbor tables and one traversal per edge |
| Small-cycle collapse, arbitrary endpoint connections within 100 px | Destroys real loops, stitches across empty space and separate components | Preserve all cycles; no artificial reconnection; watershed partitions shared junction regions |
| Loop traversal only begins at one node if the entire graph is degree two | Closed components vanish when another component has endpoints | Explicit pass for every remaining unvisited cycle edge |
| Two separate endpoint-extension algorithms | Repeated work, inconsistent ray semantics, points in background | Single batched first-exit ray cast against mask/branch ownership |
| Rail sampling and smoothing depend on guide spacing | Density changes geometry and quality | Physical rail sampling independent of guide settings |
| Global all-pairs rung rejection | Quadratic Python comparisons | Spatial hash, bounded ray batches, shared inner-corner nodes for quantization artifacts |
| Terminal tangent reversal and folded rails | Bow-tie sweeps / invalid satin geometry | Continuous rail identity; GEOS polygon validation; trim/subdivide invalid sweeps |
| Stubby regions fall back to running stitch based only on aspect ratio | Wide compact shapes lose most coverage | Principal-axis flow for compact MAT blobs; width-based running fallback |
| Optimizer reconstructs topology and ray casts six times, then again for final output | Large extra latency; catches errors silently; optimizes a DPI-dependent proxy | One rail computation; linear curvature/width-aware checkpoint selection |
| Coverage duplicated in pipeline, optimizer and debug | Metric inconsistency; sparse line coverage falls with resolution | Shared swept-quad/running-footprint diagnostic |
| ViewBox offset patched by translation after already-normalized parsing | Wrong alignment for shifted/scaled documents | Explicit source-user / CSS-viewport / raster transforms and tested inverse mapping |
| Rungs SVG has no viewBox/physical size; satin dimensions refitted ad hoc | Inconsistent scale across outputs | Explicit physical dimensions and a consistent normalized viewport |
| SVG text replacement at every `</svg>` | Malformed/nested SVG injection and namespace errors | XML tree composition with namespace-aware serialization |
| Two rails plus exactly two rungs, or extended rungs sharing corner nodes | Ambiguous Ink/Stitch rail recognition | Equal-node paired rails in satin SVG; explicit rungs in separate guide outputs |
| Import-time logging and macOS-only automatic viewer | Library side effects / fragile headless CLI | Logging configured by entry points; opt-in viewer; JSON stdout |
| Web deletes all output folders at startup | Data loss across restarts / multiple workers | App factory without startup deletion; isolated persistent job directories |
| Numeric parsing outside error handling; unbounded uploads/jobs | Invalid forms become 500s; resource exhaustion | Clear 400/413/503 responses, bounded inputs and processing slots |
| Root-wide request log handlers without filtering | Concurrent jobs receive each other's logs | Per-request thread filtering, removed in `finally` |
| Flask debug server on all interfaces | Unsafe defaults | Waitress on localhost; explicit host override |
| Web files not packaged; conflicting requirements; runtime JSX/CDNs | Installed wheel lacks UI; offline UI fails | Package UI/services; unified extras/lock; dependency-free HTML/CSS/JS |
| RGBA tracing always treats opaque alpha as silhouette; black pixels fail `< otsu` | Entire opaque image traced / empty black foreground | Alpha only if meaningful; `<=` luminance threshold; padded contours and even-odd holes |
| Regex removes nested stitch-plan groups; drawing sits outside viewBox | Broken or empty previews | XML removal and drawing-fitted preview viewport |
| Old notebook imports removed package/functions and nonexistent inputs | Notebook unusable | Minimal notebook calling the same public `generate()` API |

Direct `networkx` dependency and legacy graph repair/search code were removed.
Scikit-image can still install NetworkX as its own transitive dependency.
Shapely/GEOS validates actual sweep geometry; it is a deliberate correctness
addition rather than a second orchestration layer.

## Behavior changes worth knowing

- Automatic mode is local guide refinement under the requested maximum gap,
  rather than global spacing/density candidate search. Returned parameters remain
  the user's values; local spacing becomes finer at bends and width changes.
- The satin SVG uses Ink/Stitch's paired-node format. Rail nodes control stitch
  direction; guide spacing does not set zigzag density.
- Artificial bridges are removed (`bridges_count` remains in the API and is zero).
- The CLI opens a viewer only with `--preview`; `--no-preview` remains accepted.
- Python minimum is now 3.10 for the native renderer / current scientific stack.
- `coverage` is a swept-area diagnostic, with a physical 0.3 mm footprint for
  running paths. Original line-dilation percentages are not comparable.
- Input text/images must be converted to vector paths; external SVG assets,
  scripts and XML entities are rejected. Bitmap tracing is now shared by the library, CLI and web interfaces. Filled backgrounds are part of the silhouette and should be removed
  from the source when they are not intended to be embroidered.

## Verification

The regression suite verifies topology, actual geometry and serialized outputs:
MAT determinism and radius values; intentional holes; separate and closed
components; strict guide crossings; high swept coverage with bounded spill;
valid paired rails on every example; physical sizing/shifted viewBoxes at three
DPIs; input errors; CLI JSON; staged-write failure preservation; packaged web
uploads/downloads/preview; concurrency limits; bitmap alpha/luminance/holes;
missing external tools/timeouts and off-page stitch-plan fitting.

The built wheel was installed in a separate temporary virtual environment and
run from outside the checkout. CLI generation and web API convert/preview/download
routes succeeded. The interface now lives exclusively in Next.js; legacy Flask
launchers, static HTML and compatibility re-exports were removed. During the initial
audit native binaries were absent. The later dual-pipeline
validation executed official Ink/Stitch 3.3.0 on all 28 comparison SVGs; see
[the current quality report](QUALITY_REPORT.md). Native Inkscape and physical
sew-out remain untested. Tool failure handling is also covered with controlled
subprocess results. CI is configured for Python 3.10, 3.12 and 3.13; local execution used
Python 3.12.13 on macOS arm64.

## Benchmark

Measurements use the same host, Python and dependency environment, no Inkscape,
150 requested DPI, debug/auto mode disabled, one warm-up and the median of three
runs. Both timings include loading, rendering, geometry, routing, coverage and
all four output writes. The original checkout was restored read-only from
`git archive 2c5f643` into a temporary directory for the baseline.

| Input | Baseline seconds | New seconds | Speedup |
|---|---:|---:|---:|
| adidas | 1.7540 | 0.7613 | 2.3× |
| arabian | 0.7296 | 0.0432 | 16.9× |
| flower | 1.5354 | 0.8548 | 1.8× |
| gros_babe | 1.1725 | 0.7626 | 1.5× |
| margot | 0.8007 | 0.0572 | 14.0× |
| nike | 4.1272 | 0.4599 | 9.0× |
| shapes | 0.9056 | 0.2095 | 4.3× |

Sum of per-file medians: **11.0250 → 3.1495 seconds (3.5×)**. The different
raster budget is an intentional algorithm change, not an equal-pixel microbenchmark.
Correctness assertions separately check resolution-independent physical sizing
and output geometry. For example, `margot.svg` now correctly uses running paths
at its original physical size; its lack of satin columns is not a failure.

Raw data: [baseline](benchmarks/benchmark-baseline.json), [initial refactor](benchmarks/benchmark.json).
Reproduce current results with:

```bash
uv run python scripts/benchmark.py --repeats 3 --json output/benchmark.json
uv run python scripts/benchmark.py examples/nike.svg --auto-optimize --repeats 3
```

Runtime varies by hardware and SVG complexity. Watershed is computed only for
multiple branches; ray batches and raster work are bounded; routing uses a
bounded 2-opt neighborhood. No hard wall-clock assertion makes tests depend on
hardware speed.

## Practical limits

This is a usable, packaged PoC for **editing and finishing**, not a universal
fully automatic digitizer. MAT is sensitive to tiny source details. At sharp
junctions, taper transitions or very wide regions, a digitizer may need to
adjust/split columns or choose fill stitches. Running paths intentionally do not
fill the entire source area. Review warnings, then validate with Ink/Stitch's
Troubleshoot/Simulator and a sew-out. No global optimum, universal zero overlap,
or machine/fabric-specific quality guarantee is claimed.
