"""Deterministic visible-colour separation shared by bitmap tracing and digitizing."""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import (
    binary_dilation,
    binary_erosion,
    distance_transform_edt,
    find_objects,
    label,
)
from scipy.optimize import nnls
from scipy.spatial import cKDTree
from skimage.color import rgb2lab

from .background import bitmap_foreground as bitmap_foreground


def _interior_flat_accents(
    rgba: np.ndarray,
    packed: np.ndarray,
    visible: np.ndarray,
    paints: np.ndarray,
    candidates: list[np.uint32],
) -> np.ndarray:
    """Keep literal thin paint inside one body, not a blend of nearby bodies."""
    eligible = visible & (rgba[..., 3] == 255) & np.isin(packed, candidates)
    if not eligible.any():
        return np.empty(0, dtype=np.uint32)
    neighbourhood = np.ones((3, 3), dtype=bool)
    eligible &= binary_erosion(rgba[..., 3] == 255, structure=neighbourhood, iterations=2)
    if not eligible.any():
        return np.empty(0, dtype=np.uint32)
    neighbours = np.zeros(visible.shape, dtype=np.uint8)
    for paint in paints:
        neighbours += binary_dilation(
            visible & (packed == paint), structure=neighbourhood, iterations=2
        )
    # An RGB convex hull is not spatial evidence. A violet line within red paint
    # remains a valid source colour even if blue occurs elsewhere in the design.
    # A literal transition within two pixels of both paints remains an edge.
    return np.unique(packed[eligible & (neighbours <= 1)])


def separate_colors(rgba: np.ndarray, max_colors: int = 12) -> tuple[np.ndarray, list[str], bool]:
    """Return disjoint labels (0 = transparent) and an RGB thread palette.

    Frequent flat paints retain their exact RGB values. Photographs/gradients use
    a bounded median-cut palette; edge antialiasing is assigned to nearby paints
    in Lab space rather than creating extra thread colours.
    """
    visible = rgba[..., 3] >= 128
    pixels = rgba[..., :3][visible]
    if not len(pixels):
        raise ValueError("No visible colours found.")
    rgb = rgba[..., :3]
    packed = (
        (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]
    )
    interior = visible.copy()
    interior[[0, -1], :] = False
    interior[:, [0, -1]] = False
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        interior[1:-1, 1:-1] &= (
            packed[1:-1, 1:-1]
            == packed[1 + dr : packed.shape[0] - 1 + dr, 1 + dc : packed.shape[1] - 1 + dc]
        )
    visible_values, visible_counts = np.unique(packed[visible], return_counts=True)
    values, counts = np.unique(packed[interior], return_counts=True)
    # Thin repeated details may have no four-neighbour interior at all. Their
    # complete colour histogram still identifies flat paints without relying on
    # the raster's orientation or on an aliased stride through its pixels.
    exact = interior.sum() >= 0.5 * len(pixels) and 0 < len(values) <= max_colors
    if not exact and len(visible_values) <= max_colors:
        values, counts = visible_values, visible_counts
        exact = True
    elif exact and len(visible_values) <= max_colors:
        # A genuine thin accent can lack an interior. Edge colours blend nearby
        # paints; isolated accents or colours outside their RGB convex hull must
        # remain visible for the stitchability audit, even when very small.
        paints = np.column_stack([values >> 16, (values >> 8) & 255, values & 255])
        blends = np.vstack([paints.T, np.full(len(paints), 255)])
        adjacent = binary_dilation(visible & np.isin(packed, values))
        touching_values = np.unique(packed[visible & adjacent])
        accents = []
        ambiguous = []
        for value in np.setdiff1d(visible_values, values):
            color = np.array([value >> 16, (value >> 8) & 255, value & 255, 255])
            if value not in touching_values or nnls(blends, color)[1] > 2:
                accents.append(value)
            else:
                ambiguous.append(value)
        if ambiguous:
            accents.extend(_interior_flat_accents(rgba, packed, visible, values, ambiguous))
        if accents:
            values = np.union1d(values, accents)
            counts = visible_counts[np.searchsorted(visible_values, values)]
    reduced = False
    if exact:
        values = values[np.argsort(-counts, kind="stable")]
        palette = np.column_stack([values >> 16, (values >> 8) & 255, values & 255]).astype(
            np.uint8
        )
    else:
        order = np.argsort(-visible_counts, kind="stable")
        flat = visible_counts[order[:max_colors]].sum() / len(pixels) >= 0.97
        reduced = True
        if flat:
            paints = visible_values[order[:max_colors]]
            palette = np.column_stack([paints >> 16, (paints >> 8) & 255, paints & 255]).astype(
                np.uint8
            )
        else:
            # Equal quantiles of the sorted RGB histogram retain colour weights
            # in a bounded sample. A flip/rotation changes pixel order, never the
            # histogram or the median-cut result. Remainder allocation by RGB
            # tie order would bias photographs containing many unique colours.
            sample_count = min(100_000, len(pixels))
            ranks = (np.arange(sample_count) + 0.5) * len(pixels) / sample_count
            paints = visible_values[np.searchsorted(np.cumsum(visible_counts), ranks, side="right")]
            sample = np.column_stack([paints >> 16, (paints >> 8) & 255, paints & 255]).astype(
                np.uint8
            )
            quantized = Image.fromarray(sample.reshape(1, -1, 3)).quantize(colors=max_colors)
            palette, frequencies = np.unique(
                np.asarray(quantized.convert("RGB")).reshape(-1, 3), axis=0, return_counts=True
            )
            palette = palette[np.argsort(-frequencies, kind="stable")]
    labs = rgb2lab(palette[None, ...] / 255)[0]
    kept = []
    for i, lab in enumerate(labs):
        if exact or not kept or np.linalg.norm(labs[kept] - lab, axis=1).min() >= 6:
            kept.append(i)
    palette, labs = palette[kept], labs[kept]
    tree = cKDTree(labs)
    assigned = np.empty(len(pixels), dtype=np.uint8)
    for start in range(0, len(pixels), 100_000):
        end = min(start + 100_000, len(pixels))
        colors = rgb2lab(pixels[None, start:end, :] / 255)[0]
        assigned[start:end] = tree.query(colors)[1] + 1
    labels = np.zeros(visible.shape, dtype=np.uint8)
    labels[visible] = assigned
    # Stitch broad visible regions first and finish with smaller accents.
    areas = np.bincount(assigned, minlength=len(palette) + 1)[1:]
    used = np.flatnonzero(areas)
    used = used[np.argsort(-areas[used], kind="stable")]
    remap = np.zeros(len(palette) + 1, dtype=np.uint8)
    remap[used + 1] = np.arange(1, len(used) + 1)
    hex_colors = ["#" + "".join(f"{int(c):02x}" for c in palette[i]) for i in used]
    return remap[labels], hex_colors, reduced


def bitmap_colors(
    rgba: np.ndarray, max_colors: int = 12, *, cleanup: bool = True, diagnostics: dict | None = None
):
    """Recover compressed flat paints without creating threads from edge blends.

    This is deliberately bitmap-only. Explicit SVG paints and exact raster
    palettes remain distinct; photographs retain the ordinary bounded palette.
    """
    visible = rgba[..., 3] >= 128
    pixels = rgba[..., :3][visible]
    if not len(pixels):
        raise ValueError("No visible colours found.")
    values, counts = np.unique(pixels, axis=0, return_counts=True)
    info = {
        "palette_source_colors": len(values),
        "flat_paints_recovered": False,
        "palette_consolidated_pixels": 0,
        "retained_accent_colors": 0,
        "dark_ink_edge_pixels": 0,
    }
    if diagnostics is not None:
        diagnostics.update(info)
    if not cleanup or len(values) <= max_colors:
        return separate_colors(rgba, max_colors)
    rgba, edge_pixels = _normalize_dark_ink_edges(rgba, visible, pixels, values, counts)
    if edge_pixels:
        pixels = rgba[..., :3][visible]
        values, counts = np.unique(pixels, axis=0, return_counts=True)
        if diagnostics is not None:
            diagnostics["dark_ink_edge_pixels"] = edge_pixels
        if len(values) <= max_colors:
            return separate_colors(rgba, max_colors)
    labs = rgb2lab(values[None, ...] / 255)[0]
    order = np.argsort(-counts, kind="stable")
    seeds = []
    for i in order:
        if counts[i] < 0.005 * len(pixels):
            break
        if not seeds or np.min(np.linalg.norm(labs[seeds] - labs[i], axis=1)) >= 8:
            seeds.append(i)
    if not seeds or len(seeds) > max_colors:
        return separate_colors(rgba, max_colors)
    packed = (
        (rgba[..., 0].astype(np.uint32) << 16)
        | (rgba[..., 1].astype(np.uint32) << 8)
        | rgba[..., 2]
    )
    interior = visible.copy()
    interior[[0, -1], :] = False
    interior[:, [0, -1]] = False
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        interior[1:-1, 1:-1] &= (
            packed[1:-1, 1:-1]
            == packed[1 + dr : packed.shape[0] - 1 + dr, 1 + dc : packed.shape[1] - 1 + dc]
        )
    core_values, core_counts = np.unique(packed[interior], return_counts=True)
    packed_values = (
        (values[:, 0].astype(np.uint32) << 16)
        | (values[:, 1].astype(np.uint32) << 8)
        | values[:, 2]
    )
    dominant_paints = len(seeds)
    for core in np.argsort(-core_counts, kind="stable"):
        if core_counts[core] < 9:
            break
        i = np.searchsorted(packed_values, core_values[core])
        if np.min(np.linalg.norm(labs[seeds] - labs[i], axis=1)) >= 8:
            seeds.append(i)
            if len(seeds) > max_colors:
                return separate_colors(rgba, max_colors)
    distance, nearest = cKDTree(labs[seeds]).query(labs)
    # Small flat paints can be below the global frequency threshold. Include
    # their observed cores before deciding whether this is a logo or a gradient.
    if counts[distance <= 10].sum() / len(pixels) < 0.85:
        return separate_colors(rgba, max_colors)
    paints = values[seeds]
    blends = np.vstack([paints.T, np.full(len(paints), 255)])
    accents = []
    for i in order[distance[order] > 14]:
        # Compression can drift off the RGB convex hull by several levels.
        # Truly different colours (even isolated single pixels) stay visible.
        if nnls(blends, np.r_[values[i], 255])[1] > 24:
            if not accents or np.min(np.linalg.norm(labs[accents] - labs[i], axis=1)) >= 6:
                accents.append(i)
                if len(seeds) + len(accents) > max_colors:
                    return separate_colors(rgba, max_colors)
    if accents:
        seeds.extend(accents)
        nearest = cKDTree(labs[seeds]).query(labs)[1]
    packed_pixels = (
        (pixels[:, 0].astype(np.uint32) << 16)
        | (pixels[:, 1].astype(np.uint32) << 8)
        | pixels[:, 2]
    )
    assigned = nearest[np.searchsorted(packed_values, packed_pixels)] + 1
    areas = np.bincount(assigned, minlength=len(seeds) + 1)[1:]
    used = np.flatnonzero(areas)
    used = used[np.argsort(-areas[used], kind="stable")]
    remap = np.zeros(len(seeds) + 1, dtype=np.uint8)
    remap[used + 1] = np.arange(1, len(used) + 1)
    labels = np.zeros(visible.shape, dtype=np.uint8)
    labels[visible] = remap[assigned]
    colors = ["#" + "".join(f"{int(c):02x}" for c in values[seeds[i]]) for i in used]
    if diagnostics is not None:
        # Compare spatial complexity with the ordinary palette only on the flat
        # recovery path; photos need no second expensive Lab quantization.
        baseline, baseline_colors, _ = separate_colors(rgba, max_colors)
        diagnostics.update(
            flat_paints_recovered=True,
            retained_accent_colors=len(seeds) - dominant_paints,
            palette_consolidated_pixels=int(
                counts[np.any(values != values[seeds][nearest], axis=1)].sum()
            ),
            palette_regions_before=sum(
                label(baseline == paint)[1] for paint in range(1, len(baseline_colors) + 1)
            ),
        )
    return labels, colors, True


def _normalize_dark_ink_edges(rgba, visible, pixels, values, counts):
    """Recover a nearly black bitmap's alpha fringe without flattening gray paint.

    A black mark exported against a gray matte can carry gray RGB values in its
    partially transparent outline. Those one-pixel fragments are not additional
    thread paints. Exact palettes, opaque gray outlines, colored accents, and
    interior shading provide contrary evidence and are preserved.
    """
    intensity = pixels.max(axis=1)
    if (
        np.mean(intensity <= 35) < 0.97
        or np.any(np.ptp(pixels, axis=1) > 8)
        or np.diff(np.percentile(intensity, (5, 95)))[0] > 12
    ):
        return rgba, 0
    fringe = visible & (rgba[..., :3].max(axis=2) > 35)
    if not fringe.any() or np.any(rgba[..., 3][fringe] == 255):
        return rgba, 0
    # The alpha boundary, rather than a color-only threshold, distinguishes
    # compositing contamination from a genuine gray detail inside the artwork.
    edge_distance = distance_transform_edt(np.pad(visible, 1))[1:-1, 1:-1]
    if np.any(edge_distance[fringe] > 3):
        return rgba, 0
    core = values.max(axis=1) <= 35
    paint = values[np.flatnonzero(core)[counts[core].argmax()]]
    result = rgba.copy()
    result[fringe, :3] = paint
    return result, int(fringe.sum())


def clean_color_regions(
    labels: np.ndarray,
    colors: list[str],
    pixels_per_mm: float,
    diagnostics: dict,
    *,
    rgba: np.ndarray | None = None,
) -> np.ndarray:
    """Merge sub-resolution colour speckles into a nearby, similar stable paint.

    No alpha is deleted, no transparent counter filled, and isolated accents
    survive. The 0.10 mm² / 0.5 mm limits bound changes in the sewing frame.
    """
    regions = np.zeros(labels.shape, dtype=np.int32)
    count = 0
    for paint in range(1, len(colors) + 1):
        components, n = label(labels == paint)
        occupied = components > 0
        regions[occupied] = components[occupied] + count
        count += n
    result = labels.copy()
    areas = np.bincount(regions.ravel())
    rgb = np.array([[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in colors])
    labs = rgb2lab(rgb[None, ...] / 255)[0]
    limit = 0.10 * pixels_per_mm**2
    diagnostics.update(
        changed_pixels=0,
        removed_pixels=0,
        regions_before=count,
        regions_after=count,
        changed_area_mm2=0.0,
        edge_blend_pixels=0,
        reason="no_safe_speckles",
    )
    distances = np.linalg.norm(labs[:, None] - labs[None, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    if not np.any(distances <= 18) and rgba is None:
        return result
    # Build slice objects only for recoverable speckles touching a stable paint.
    # A dense checkerboard can contain millions of unrecoverable components.
    stable = (regions > 0) & (areas[regions] > limit)
    candidates = np.unique(regions[binary_dilation(stable) & ~stable])
    candidates = candidates[(candidates > 0) & (areas[candidates] <= limit)]
    if not len(candidates):
        return result
    compact = np.zeros(count + 1, dtype=np.int32)
    compact[candidates] = np.arange(1, len(candidates) + 1)
    boxes = find_objects(compact[regions])
    changed = 0
    blended = 0
    for candidate, region in enumerate(candidates):
        box = boxes[candidate]
        if max(axis.stop - axis.start for axis in box) / pixels_per_mm > 0.5:
            continue
        patch = tuple(
            slice(max(0, axis.start - 2), min(size, axis.stop + 2))
            for axis, size in zip(box, labels.shape, strict=True)
        )
        mask = regions[patch] == region
        border = binary_dilation(mask, iterations=2) & ~mask
        neighbours = regions[patch][border]
        stable = neighbours[(neighbours > 0) & (areas[neighbours] > limit)]
        if not len(stable):
            continue
        candidates = np.unique(labels[patch][border & np.isin(regions[patch], stable)])
        paint = labels[box][regions[box] == region][0]
        distances = np.linalg.norm(labs[candidates - 1] - labs[paint - 1], axis=1)
        chosen = np.argmin(distances)
        if distances[chosen] > 18:
            if rgba is None or len(candidates) < 2:
                continue
            source = rgba[box][regions[box] == region, :3].astype(float)
            source_labs = rgb2lab(source[None, ...] / 255)[0]
            errors = np.full(len(source), np.inf)
            for index, first in enumerate(candidates):
                for second in candidates[index + 1 :]:
                    base = rgb[first - 1]
                    direction = rgb[second - 1] - base
                    fraction = np.clip(
                        (source - base) @ direction / max(float(direction @ direction), 1),
                        0,
                        1,
                    )
                    delta = source - base - fraction[:, None] * direction
                    errors = np.minimum(errors, np.linalg.norm(delta, axis=1))
            if np.percentile(errors, 90) > 24:
                continue
            chosen = np.argmin(
                np.linalg.norm(labs[candidates - 1] - source_labs.mean(axis=0), axis=1)
            )
            blended += int(areas[region])
        if candidates[chosen] == paint:
            continue
        result[box][regions[box] == region] = candidates[chosen]
        changed += int(areas[region])
    diagnostics.update(
        changed_pixels=changed,
        removed_pixels=0,
        regions_before=count,
        regions_after=(
            sum(label(result == paint)[1] for paint in range(1, len(colors) + 1))
            if changed
            else count
        ),
        changed_area_mm2=changed / pixels_per_mm**2,
        edge_blend_pixels=blended,
        reason="small_adjacent_colour_speckles" if changed else "no_safe_speckles",
    )
    return result
