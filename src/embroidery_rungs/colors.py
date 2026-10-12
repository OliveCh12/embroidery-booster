"""Deterministic visible-colour separation shared by bitmap tracing and digitizing."""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
from scipy.optimize import nnls
from scipy.spatial import cKDTree
from skimage.color import rgb2lab


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
        for value in np.setdiff1d(visible_values, values):
            color = np.array([value >> 16, (value >> 8) & 255, value & 255, 255])
            if value not in touching_values or nnls(blends, color)[1] > 2:
                accents.append(value)
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


def bitmap_foreground(rgba: np.ndarray) -> np.ndarray:
    """Remove a uniform opaque perimeter background; explicit alpha takes priority."""
    rgba = rgba.copy()
    if np.any(rgba[..., 3] < 255):
        return rgba
    rgb = rgba[..., :3]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    colors, counts = np.unique(border, axis=0, return_counts=True)
    background = colors[np.argmax(counts)]
    distances = np.linalg.norm(border.astype(float) - background, axis=1)
    close_border = distances <= 18
    if close_border.mean() >= 0.85:
        tolerance = max(1.0, float(np.percentile(distances[close_border], 99)))
        flat = rgba.reshape(-1, 4)
        for start in range(0, len(flat), 100_000):
            chunk = flat[start : start + 100_000]
            delta = chunk[:, :3].astype(np.int32) - background
            chunk[np.einsum("ij,ij->i", delta, delta) <= tolerance**2, 3] = 0
    return rgba
