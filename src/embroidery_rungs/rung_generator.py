"""Rung placement along the medial axis.

Pipeline per centerline path:

1. resample the skeleton polyline at uniform arc length,
2. lightly smooth it (kills pixel jaggies without distorting the shape),
3. compute tangents/normals by finite differences,
4. cast a sub-pixel ray each way to the shape boundary to form a rung,
5. space rungs adaptively (denser in curves) and drop any that would cross a
   neighbour, so rungs stay perpendicular and never fan out.

Bridges connect the nearest rungs of paths meeting at a junction (MST) so
Ink/Stitch reads the satin as continuous.
"""

import logging

import numpy as np
import networkx as nx
from scipy.ndimage import uniform_filter1d

from .geometry_utils import get_skeleton_paths, merge_aligned_paths, segments_intersect
from .debug_utils import save_debug_graph, save_rung_coverage_debug

logger = logging.getLogger(__name__)

_MIN_RUNG_LEN = 2.0      # px; ignore degenerate rungs
_MIN_PATH_LEN = 6.0      # px; ignore noise paths


def _resample(points, step):
    """Resample an (N, 2) polyline at a uniform arc-length ``step``.

    Returns ``(resampled, arc_lengths, total_length)``.
    """
    deltas = np.diff(points, axis=0)
    seg = np.hypot(deltas[:, 0], deltas[:, 1])
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(arc[-1])
    if total < 1e-6:
        return points[:1].astype(float), np.array([0.0]), 0.0
    n = max(2, int(total / step) + 1)
    targets = np.linspace(0.0, total, n)
    xs = np.interp(targets, arc, points[:, 0])
    ys = np.interp(targets, arc, points[:, 1])
    return np.column_stack([xs, ys]), targets, total


def _smooth(points, window):
    """Light moving-average smoothing that keeps the endpoints fixed."""
    if len(points) < 3 or window < 2:
        return points
    out = np.empty_like(points)
    out[:, 0] = uniform_filter1d(points[:, 0], size=window, mode="nearest")
    out[:, 1] = uniform_filter1d(points[:, 1], size=window, mode="nearest")
    out[0], out[-1] = points[0], points[-1]
    return out


_MIN_SPLIT_RUNGS = 10   # only split columns that are actually long
_MIN_SEGMENT_RUNGS = 4  # never create tiny fragments


def _split_at_sharp_curves(items, max_turn_deg=45.0, max_accum_deg=70.0):
    """Split a long column's rungs where the centerline bends too much.

    A satin column following a tight bend stitches unevenly (the inner rail gets
    denser). Splitting at sharp local turns — or once the curve has accumulated
    enough total turn — yields gentler sub-columns that stitch cleanly. Short
    columns and smooth/gentle shapes are left intact, and splits that would
    create tiny fragments are skipped (those degrade thin shapes). Sub-columns
    overlap by one rung so the satins meet without a gap.
    """
    n = len(items)
    if n < _MIN_SPLIT_RUNGS:
        return [items]
    centers = np.array([it["center"] for it in items], dtype=float)

    splits = []
    accum = 0.0
    last = 0
    for i in range(1, n - 1):
        v1 = centers[i] - centers[i - 1]
        v2 = centers[i + 1] - centers[i]
        n1, n2 = np.hypot(*v1), np.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        turn = np.degrees(np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)))
        accum += turn
        # Only split when both the piece left behind and what remains are big
        # enough to be real columns.
        if (turn >= max_turn_deg or accum >= max_accum_deg) \
                and i - last >= _MIN_SEGMENT_RUNGS and n - i >= _MIN_SEGMENT_RUNGS:
            splits.append(i)
            accum = 0.0
            last = i

    if not splits:
        return [items]
    segments, start = [], 0
    for s in splits:
        segments.append(items[start:s + 1])  # overlap by the split rung
        start = s
    segments.append(items[start:])
    return segments


def _smooth_rail(points):
    """Light smoothing of a rail polyline (kills ray-cast jaggedness)."""
    arr = np.asarray(points, dtype=float)
    if len(arr) < 5:
        return arr
    out = arr.copy()
    out[:, 0] = uniform_filter1d(arr[:, 0], size=5, mode="nearest")
    out[:, 1] = uniform_filter1d(arr[:, 1], size=5, mode="nearest")
    out[0], out[-1] = arr[0], arr[-1]   # keep the caps anchored
    return out


def _cast_to_boundary(mask, cx, cy, dx, dy, max_dist, step=0.5):
    """March from (cx, cy) along (dx, dy) until leaving the shape.

    Vectorized sub-pixel ray cast. Returns ``(x, y, distance)`` of the last
    point still inside; ``distance == max_dist`` means no boundary was hit.
    """
    h, w = mask.shape
    n = int(max_dist / step)
    if n < 1:
        return cx, cy, 0.0
    d = np.arange(1, n + 1) * step
    xs = cx + dx * d
    ys = cy + dy * d
    ix = np.round(xs).astype(int)
    iy = np.round(ys).astype(int)
    oob = (ix < 0) | (ix >= w) | (iy < 0) | (iy >= h)
    ix = np.clip(ix, 0, w - 1)
    iy = np.clip(iy, 0, h - 1)
    outside = oob | (mask[iy, ix] == 0)
    hit = np.argmax(outside)
    if not outside[hit]:
        return cx + dx * max_dist, cy + dy * max_dist, max_dist
    dist = d[hit] - step  # last point still inside
    return cx + dx * dist, cy + dy * dist, dist


def _make_rung(mask, cx, cy, nx, ny, max_search):
    """Build a rung centred at (cx, cy) along normal (nx, ny), or None."""
    p1x, p1y, d1 = _cast_to_boundary(mask, cx, cy, nx, ny, max_search)
    p2x, p2y, d2 = _cast_to_boundary(mask, cx, cy, -nx, -ny, max_search)
    # Both rays maxed out -> we are not inside a band, reject.
    if d1 >= max_search and d2 >= max_search:
        return None
    if np.hypot(p1x - p2x, p1y - p2y) < _MIN_RUNG_LEN:
        return None
    return (float(p1x), float(p1y)), (float(p2x), float(p2y))


def _crosses_recent(rung, recent):
    p1, p2 = rung
    for prev in recent:
        if segments_intersect(prev[0], prev[1], p1, p2):
            return True
    return False


def _remove_crossings(items):
    """Drop any rung that strictly crosses an already-accepted one.

    Guarantees no two rungs in the result cross — including across different
    paths, which is where junction/spiral X-artifacts come from. Cheap thanks to
    a bounding-box pre-check before the exact segment test.
    """
    accepted = []
    boxes = []  # (xmin, ymin, xmax, ymax) per accepted rung
    for it in items:
        (ax, ay), (bx, by) = it["rung"]
        box = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        crosses = False
        for (cx0, cy0, cx1, cy1), other in zip(boxes, accepted):
            if box[2] < cx0 or box[0] > cx1 or box[3] < cy0 or box[1] > cy1:
                continue  # disjoint bounding boxes
            if segments_intersect(other["rung"][0], other["rung"][1],
                                  it["rung"][0], it["rung"][1]):
                crosses = True
                break
        if not crosses:
            accepted.append(it)
            boxes.append(box)
    return accepted


def _rungs_for_path(points_rc, distance_map, binary_img, spacing_px):
    """Generate ordered rungs (and their centres) for one centerline path."""
    # points_rc is (row, col) = (y, x); work in (x, y).
    pts = np.column_stack([points_rc[:, 1], points_rc[:, 0]]).astype(float)

    step = max(2.0, spacing_px / 10.0)
    rs, arc, total = _resample(pts, step)
    if total < _MIN_PATH_LEN:
        return []

    window = max(2, int(round(spacing_px / step / 2)))
    sm = _smooth(rs, window)

    # Tangents and normals by central differences on the smoothed centerline.
    tang = np.gradient(sm, axis=0)
    tn = np.hypot(tang[:, 0], tang[:, 1])
    tn[tn < 1e-9] = 1.0
    tang /= tn[:, None]
    normals = np.column_stack([-tang[:, 1], tang[:, 0]])

    # Curvature magnitude (1 / turn radius), in 1/px.
    dtang = np.gradient(tang, axis=0)
    curv = np.hypot(dtang[:, 0], dtang[:, 1]) / step

    h, w = binary_img.shape
    placed = []
    recent = []
    s = 0.0
    # Always include the two ends so the satin is capped.
    forced_end = False
    while True:
        i = min(int(np.searchsorted(arc, s)), len(sm) - 1)
        cx, cy = sm[i]
        iy = int(np.clip(cy, 0, h - 1))
        ix = int(np.clip(cx, 0, w - 1))
        local_w = float(distance_map[iy, ix])
        max_search = max(local_w * 2.2, 12.0)

        rung = _make_rung(binary_img, cx, cy, normals[i, 0], normals[i, 1], max_search)
        if rung is not None and not _crosses_recent(rung, recent[-2:]):
            placed.append({"rung": rung, "center": (float(cx), float(cy)),
                           "half_width": local_w})
            recent.append(rung)

        # Adaptive advance: denser in curves, but never closer than the local
        # half-width (that is what makes perpendicular rungs cross / fan out).
        radius = 1.0 / max(curv[i], 1e-6)
        factor = float(np.clip(radius / (spacing_px * 2.0), 0.45, 1.5))
        next_step = max(spacing_px * factor, local_w * 0.9, 3.0)
        s += next_step

        if s >= total:
            if forced_end:
                break
            s = total          # place one final rung exactly at the end
            forced_end = True

    return placed


def _build_bridges(merged_paths, skeleton_paths, path_rungs_map, G, spacing_px):
    """Connect nearest rungs of paths meeting at each junction via an MST."""
    junctions = [n for n, deg in G.degree() if deg > 2]
    if not junctions:
        return []

    j_map = {j: set() for j in junctions}
    for p_idx, p in enumerate(merged_paths):
        for node in (p.get("start_node"), p.get("end_node")):
            if node in j_map:
                j_map[node].add(p_idx)
        for orig_idx in p.get("original_indices", []):
            op = skeleton_paths[orig_idx]
            for node in (op["start_node"], op["end_node"]):
                if node in j_map:
                    j_map[node].add(p_idx)

    bridges = []
    for j, connected in j_map.items():
        if len(connected) < 2:
            continue
        jy, jx = G.nodes[j]["pos"]  # (row, col)
        # Closest rung of each path to the junction.
        endpoints = []
        for p_idx in connected:
            rungs = path_rungs_map.get(p_idx)
            if not rungs:
                continue
            best = min(rungs, key=lambda r: (r["center"][0] - jx) ** 2 + (r["center"][1] - jy) ** 2)
            endpoints.append(best["center"])
        if len(endpoints) < 2:
            continue

        gb = nx.Graph()
        for i in range(len(endpoints)):
            for k in range(i + 1, len(endpoints)):
                d = float(np.hypot(endpoints[i][0] - endpoints[k][0],
                                   endpoints[i][1] - endpoints[k][1]))
                if d < spacing_px * 10:
                    gb.add_edge(i, k, weight=d)
        if gb.number_of_edges():
            for u, v in nx.minimum_spanning_tree(gb).edges():
                bridges.append((endpoints[u], endpoints[v]))

    # Deduplicate.
    seen, unique = set(), []
    for p1, p2 in bridges:
        key = tuple(sorted(((round(p1[0], 1), round(p1[1], 1)),
                            (round(p2[0], 1), round(p2[1], 1)))))
        if key not in seen:
            seen.add(key)
            unique.append((p1, p2))
    return unique


def generate_rungs(skeleton, distance_map, spacing_px, binary_img,
                   min_satin_width_px=0.0, debug_dir=None):
    """Generate embroidery elements (satin columns + running stitches).

    Each centerline path becomes one or more elements. A piece wide enough for a
    satin (median width >= ``min_satin_width_px``) is emitted as a satin column;
    a thinner piece is emitted as a running stitch down its centerline. This
    adapts the stitch type to the local shape so fine strokes stay crisp.
    """
    logger.info(f"Generating rungs (spacing {spacing_px:.1f}px)...")

    skeleton_paths, G = get_skeleton_paths(skeleton, binary_img=binary_img, min_len_px=10)
    if debug_dir:
        save_debug_graph(debug_dir, G, binary_img.shape)
    if not skeleton_paths:
        logger.warning("No valid skeleton paths found.")
        return [], [], []

    merged_paths = merge_aligned_paths(skeleton_paths, G, spacing_px)
    logger.info(f"Merged {len(skeleton_paths)} segments into {len(merged_paths)} continuous paths.")

    all_items = []
    for p_idx, path in enumerate(merged_paths):
        for item in _rungs_for_path(path["points"], distance_map, binary_img, spacing_px):
            item["p_idx"] = p_idx
            all_items.append(item)

    accepted = _remove_crossings(all_items)
    rungs = [item["rung"] for item in accepted]

    path_rungs_map = {}
    for item in accepted:
        path_rungs_map.setdefault(item["p_idx"], []).append(item)

    # Build embroidery elements. Each path (after splitting tight curves) becomes
    # a satin column where it is wide enough, or a running stitch where it is too
    # thin for a clean satin.
    elements = []
    for items in path_rungs_map.values():
        if len(items) < 2:
            continue
        for sub in _split_at_sharp_curves(items):
            width = 2.0 * float(np.median([it["half_width"] for it in sub]))
            centers = _smooth_rail([it["center"] for it in sub])
            length = float(np.hypot(*np.diff(centers, axis=0).T).sum())
            # Running stitch when too thin for a clean satin, or too stubby to be
            # a real column (a satin must be clearly longer than it is wide).
            if width < min_satin_width_px or length < 1.5 * width:
                elements.append({
                    "type": "running",
                    "points": [(float(x), float(y)) for x, y in centers],
                })
            else:
                rail_a = _smooth_rail([it["rung"][0] for it in sub])
                rail_b = _smooth_rail([it["rung"][1] for it in sub])
                a = [(float(x), float(y)) for x, y in rail_a]
                b = [(float(x), float(y)) for x, y in rail_b]
                elements.append({
                    "type": "satin",
                    "rail_a": a,
                    "rail_b": b,
                    "rungs": [(a[i], b[i]) for i in range(len(a))],
                })

    bridges = _build_bridges(merged_paths, skeleton_paths, path_rungs_map, G, spacing_px)

    n_satin = sum(1 for e in elements if e["type"] == "satin")
    n_run = len(elements) - n_satin
    logger.info(f"Generated {len(rungs)} rungs -> {n_satin} satin columns, "
                f"{n_run} running stitches, {len(bridges)} bridges.")
    if debug_dir:
        save_rung_coverage_debug(debug_dir, binary_img, rungs, skeleton_paths)

    return rungs, bridges, elements
