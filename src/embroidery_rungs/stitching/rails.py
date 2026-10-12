"""Extract continuous boundary rails from the medial axis for direct stitches."""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
from scipy.ndimage import find_objects, gaussian_filter1d, label, map_coordinates
from shapely.geometry import Polygon
from skimage.segmentation import watershed

from ..geometry_utils import get_skeleton_paths, segments_intersect

logger = logging.getLogger(__name__)


def _valid_rail_pieces(a, b, centers):
    """Trim folded caps and subdivide invalid sweeps before stitch planning."""
    pending = [(a, b, centers)]
    while pending:
        a, b, c = pending.pop()
        while len(a) > 2 and not Polygon([a[0], a[1], b[1], b[0]]).is_valid:
            a, b, c = a[1:], b[1:], c[1:]
        while len(a) > 2 and not Polygon([a[-2], a[-1], b[-1], b[-2]]).is_valid:
            a, b, c = a[:-1], b[:-1], c[:-1]
        polygon = Polygon(np.vstack([a, b[::-1]]))
        if polygon.is_valid and polygon.area > 0:
            yield a, b, c
        elif len(a) >= 4:
            mid = len(a) // 2
            pending.append((a[mid:], b[mid:], c[mid:]))
            pending.append((a[: mid + 1], b[: mid + 1], c[: mid + 1]))
        else:
            # A short folded region cannot define a satin. Preserve its flow
            # as a running stitch instead of exporting an invalid column.
            yield None, None, c


def _resample(points: np.ndarray, step: float) -> np.ndarray:
    keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-8]
    points = points[keep]
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    if arc[-1] < 1e-8:
        return points
    targets = np.linspace(0, arc[-1], max(3, int(np.ceil(arc[-1] / step)) + 1))
    return np.column_stack([np.interp(targets, arc, points[:, i]) for i in (0, 1)])


def cast_to_boundary(mask, centers, directions, limits, owners=None, owner=0):
    """Batched first-exit rays, including holes; bounded temporary memory."""
    result = centers.copy()
    hit_boundary = np.zeros(len(centers), dtype=bool)
    h, w = mask.shape
    for start in range(0, len(centers), 64):
        end = min(start + 64, len(centers))
        d = np.arange(0.5, float(np.max(limits[start:end])) + 0.5, 0.5)
        if not len(d):
            continue
        xy = centers[start:end, None, :] + directions[start:end, None, :] * d[None, :, None]
        ix, iy = np.floor(xy[..., 0] + 0.5).astype(int), np.floor(xy[..., 1] + 0.5).astype(int)
        outside = (ix < 0) | (ix >= w) | (iy < 0) | (iy >= h)
        outside |= ~mask[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)]
        if owners is not None:
            outside |= owners[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)] != owner
        outside &= d[None, :] <= limits[start:end, None]
        hit = outside.any(axis=1)
        lengths = np.maximum(0, d[outside.argmax(axis=1)] - 0.5)
        result[start:end] += directions[start:end] * lengths[:, None]
        hit_boundary[start:end] = hit
    return result, hit_boundary


def _fallback_axes(mask, paths, distance):
    """A disk's MAT is a point: choose its principal diameter for digitizing."""
    components, n = label(mask, structure=np.ones((3, 3)))
    bounds = find_objects(components, max_label=n)
    represented = defaultdict(list)
    for path in paths:
        r, c = np.rint(path["points"][len(path["points"]) // 2]).astype(int)
        represented[int(components[r, c])].append(path)
    for component in range(1, n + 1):
        existing = represented[component]
        if existing:
            length = sum(
                np.linalg.norm(np.diff(p["points"], axis=0), axis=1).sum() for p in existing
            )
            radius = max(
                float(distance[tuple(np.rint(p["points"]).astype(int).T)].max()) for p in existing
            )
            if length >= 4 * radius:
                continue
            # Round blobs have unstable radial MAT branches. A diameter gives
            # coherent parallel stitches instead of a fan around the center.
            paths = [p for p in paths if all(p is not item for item in existing)]
        region = bounds[component - 1]
        rc = np.argwhere(components[region] == component)
        rc += (region[0].start, region[1].start)
        if len(rc) < 2:
            continue
        center = rc.mean(axis=0)
        centered = rc - center
        _, vectors = np.linalg.eigh(centered.T @ centered)
        direction = vectors[:, -1]
        # Snap to an interior pixel, even for a crescent whose centroid is outside.
        center = rc[np.argmin(np.sum((rc - center) ** 2, axis=1))].astype(float)
        paths.append(
            {
                "points": np.array([center - direction * 0.5, center + direction * 0.5]),
                "start_node": -2 * component,
                "end_node": -2 * component - 1,
            }
        )
    return paths


def _crossing_filter(rails):
    """Spatial hash instead of comparing every rung to all previous rungs."""
    all_widths = [np.linalg.norm(b - a, axis=1) for a, b, _ in rails]
    cell = max(4.0, float(np.median(np.concatenate(all_widths)))) if all_widths else 4.0
    cells, accepted = defaultdict(list), []
    output = []
    for a, b, centers in rails:
        valid = []
        for i, (p, q) in enumerate(zip(a, b, strict=True)):
            low, high = np.minimum(p, q), np.maximum(p, q)
            lo, hi = np.floor(low / cell).astype(int), np.floor(high / cell).astype(int)
            keys = [(x, y) for x in range(lo[0], hi[0] + 1) for y in range(lo[1], hi[1] + 1)]
            nearby = {j for key in keys for j in cells[key]}
            crosses = False
            for j in nearby:
                u, v = accepted[j]
                if not segments_intersect(p, q, u, v):
                    continue
                matrix = np.column_stack([q - p, u - v])
                hit = p + (q - p) * np.linalg.solve(matrix, u - p)[0]
                ends = [p, q]
                previous = [u, v]
                current_end = min(ends, key=lambda x: np.linalg.norm(x - hit))
                previous_end = min(previous, key=lambda x: np.linalg.norm(x - hit))
                if (
                    max(np.linalg.norm(current_end - hit), np.linalg.norm(previous_end - hit))
                    <= 1.0
                ):
                    # Raster quantization at an inner corner: share a rail node
                    # instead of deleting a whole fan of otherwise valid rungs.
                    current_end[:] = hit
                    previous_end[:] = hit
                else:
                    crosses = True
                    break
            if crosses:
                continue
            valid.append(i)
            j = len(accepted)
            accepted.append((p, q))
            for key in keys:
                cells[key].append(j)
        output.append((a, b, centers, np.array(valid, dtype=int)))
    return output


def generate_columns(
    skeleton,
    distance_map,
    binary_img,
    *,
    min_satin_width_px=0.0,
    pixels_per_mm=6.0,
):
    """Return satin rails and running paths without producing SVG guide geometry.

    Branches remain separate columns at junctions. No artificial bridges are
    stitched across empty space.
    """
    paths = get_skeleton_paths(skeleton, distance=distance_map)
    paths = _fallback_axes(binary_img, paths, distance_map)
    owners = None
    if len(paths) > 1:
        seeds = np.zeros(binary_img.shape, dtype=np.int32)
        for owner, path in enumerate(paths, 1):
            rc = np.rint(path["points"]).astype(int)
            empty = seeds[tuple(rc.T)] == 0
            seeds[tuple(rc[empty].T)] = owner
        owners = watershed(-distance_map, seeds, mask=binary_img)
    endpoints = defaultdict(int)
    for path in paths:
        endpoints[path["start_node"]] += 1
        endpoints[path["end_node"]] += 1
    rails = []
    step = max(1.0, min(4.0, pixels_per_mm * 0.25))
    for owner, path in enumerate(paths, 1):
        centers = _resample(path["points"][:, ::-1], step)
        if len(centers) < 3:
            continue
        closed = np.linalg.norm(centers[0] - centers[-1]) < 0.5
        original = centers.copy()
        centers = gaussian_filter1d(
            centers[:-1] if closed else centers,
            sigma=max(0.9, pixels_per_mm * 0.45 / step),
            axis=0,
            mode="wrap" if closed else "nearest",
        )
        if closed:
            centers = np.vstack([centers, centers[0]])
        if not closed:
            centers[0], centers[-1] = original[0], original[-1]
        inside = map_coordinates(binary_img.astype(np.uint8), centers[:, ::-1].T, order=0) > 0
        if owners is not None:
            inside &= map_coordinates(owners, centers[:, ::-1].T, order=0) == owner
        centers[~inside] = original[~inside]
        if not closed:
            for side, key in ((0, "start_node"), (-1, "end_node")):
                if endpoints[path[key]] != 1:
                    continue
                direction = centers[side] - centers[2 if side == 0 else -3]
                direction /= max(np.linalg.norm(direction), 1e-9)
                radius = map_coordinates(distance_map, centers[side, ::-1, None], order=1)[0]
                target, hit = cast_to_boundary(
                    binary_img,
                    centers[side : side + 1] if side == 0 else centers[-1:],
                    direction[None, :],
                    np.array([max(4.0, radius * 4)]),
                    owners,
                    owner,
                )
                if hit[0]:
                    centers[side] = target[0]
            centers = _resample(centers, step)
        if closed:
            tangent = (np.roll(centers[:-1], -1, axis=0) - np.roll(centers[:-1], 1, axis=0)) / 2
            tangent = np.vstack([tangent, tangent[0]])
        else:
            tangent = np.gradient(centers, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
        normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
        # A terminal tangent can flip at a cap after extension/resampling.
        # Keep rail identity continuous instead of creating a bow-tie quad.
        signs = np.cumprod(np.r_[1, np.where(np.sum(normal[1:] * normal[:-1], axis=1) < 0, -1, 1)])
        normal *= signs[:, None]
        radius = map_coordinates(distance_map, centers[:, ::-1].T, order=1)
        limits = np.full(
            len(radius), min(np.hypot(*binary_img.shape), max(8.0, float(radius.max()) * 4))
        )
        a, ha = cast_to_boundary(binary_img, centers, normal, limits, owners, owner)
        b, hb = cast_to_boundary(binary_img, centers, -normal, limits, owners, owner)
        good = ha & hb & (np.linalg.norm(b - a, axis=1) >= 1.0)
        if owners is not None:
            good &= map_coordinates(owners, centers[:, ::-1].T, order=0) == owner
        # Keep invalid gaps visible to segmentation rather than connecting over them.
        a[~good] = b[~good] = centers[~good]
        rails.append((a, b, centers))
    elements = []
    for a, b, centers, valid in _crossing_filter(rails):
        widths = np.linalg.norm(b - a, axis=1)
        satin = widths >= min_satin_width_px
        # Changes of stitch type and rejected cross-sections are column boundaries.
        valid = valid[widths[valid] >= 1.0]
        if len(valid) < 2:
            continue
        cuts = (
            np.flatnonzero(
                (satin[valid[1:]] != satin[valid[:-1]])
                | (
                    np.linalg.norm(np.diff(centers[valid], axis=0), axis=1)
                    > np.maximum(6 * pixels_per_mm, widths[valid[:-1]])
                )
            )
            + 1
        )
        for indices in np.split(valid, cuts):
            if len(indices) < 2:
                continue
            if not satin[indices[0]]:
                elements.append(
                    {
                        "type": "running",
                        "points": centers[indices].tolist(),
                        "rail_a": a[indices].tolist(),
                        "rail_b": b[indices].tolist(),
                    }
                )
                continue
            # Split tight bends; overlap one cross-section to avoid a visible gap.
            angles = np.unwrap(np.arctan2(*np.gradient(centers[indices], axis=0)[:, ::-1].T))
            splits = []
            low = high = angles[0]
            for k in range(2, len(indices) - 2):
                low, high = min(low, angles[k]), max(high, angles[k])
                if high - low >= np.radians(80):
                    splits.append(k)
                    low = high = angles[k]
            for left, right in zip([0] + splits, splits + [len(indices) - 1], strict=True):
                ix = indices[left : right + 1]
                for ra, rb, c in _valid_rail_pieces(a[ix], b[ix], centers[ix]):
                    if ra is None:
                        elements.append({"type": "running", "points": c.tolist()})
                        continue
                    if len(ra) == 2:
                        ra, rb, c = [np.vstack([x[0], x.mean(axis=0), x[1]]) for x in (ra, rb, c)]
                    elements.append(
                        {
                            "type": "satin",
                            "rail_a": ra.tolist(),
                            "rail_b": rb.tolist(),
                        }
                    )
    logger.info("Extracted %d satin/running rail elements", len(elements))
    return elements
