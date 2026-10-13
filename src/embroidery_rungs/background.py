"""Perimeter-connected background extraction and bounded compositing refinement."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_erosion,
    binary_fill_holes,
    binary_propagation,
    distance_transform_edt,
    maximum_filter,
    minimum_filter,
)
from scipy.spatial import cKDTree

_CONNECTIVITY = np.ones((3, 3), dtype=bool)
_EDGE_RADIUS = 24


def _perimeter(shape: tuple[int, int]) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    result[[0, -1], :] = True
    result[:, [0, -1]] = True
    return result


def _coordinates(shape: tuple[int, int], selection: np.ndarray) -> np.ndarray:
    rows, columns = np.nonzero(selection)
    height, width = shape
    x = 2 * columns / max(1, width - 1) - 1
    y = 2 * rows / max(1, height - 1) - 1
    return np.column_stack((np.ones(len(x)), x, y))


def _fit_plane(rgb: np.ndarray, perimeter: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    design = _coordinates(perimeter.shape, perimeter)
    colors = rgb[perimeter].astype(float)
    weights = np.ones(len(colors))
    # Huber weighting permits a small border accent without allowing a second
    # large paint to masquerade as a spatially varying background.
    for _ in range(5):
        coefficients = np.linalg.lstsq(
            design * weights[:, None], colors * weights[:, None], rcond=None
        )[0]
        errors = np.linalg.norm(design @ coefficients - colors, axis=1)
        scale = max(1.0, float(np.median(errors)) * 1.4826)
        weights = np.minimum(1, 3 * scale / np.maximum(errors, 1e-6))
    return coefficients, errors


def _predict(
    coefficients: np.ndarray, shape: tuple[int, int], bounds: tuple[int, int, int, int]
) -> np.ndarray:
    top, bottom, left, right = bounds
    height, width = shape
    x = (2 * np.arange(left, right) / max(1, width - 1) - 1).astype(np.float32)
    y = (2 * np.arange(top, bottom) / max(1, height - 1) - 1).astype(np.float32)
    return np.clip(
        coefficients[0].astype(np.float32)
        + x[None, :, None] * coefficients[1].astype(np.float32)
        + y[:, None, None] * coefficients[2].astype(np.float32),
        0,
        255,
    )


def _residual(rgb: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    distances = np.empty((height, width), dtype=np.float32)
    # Bounded row chunks avoid multiple full RGB float images on a 16 MP input.
    for start in range(0, height, 256):
        stop = min(height, start + 256)
        delta = rgb[start:stop].astype(np.float32) - _predict(
            coefficients, (height, width), (start, stop, 0, width)
        )
        distances[start:stop] = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
    return distances


def _neighbor_gradient(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    gradient = np.zeros((height, width), dtype=np.float32)
    for start in range(0, height, 256):
        stop = min(height, start + 256)
        delta = np.diff(rgb[start:stop].astype(np.int16), axis=1).astype(np.float32)
        distances = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
        np.maximum(gradient[start:stop, 1:], distances, out=gradient[start:stop, 1:])
        np.maximum(gradient[start:stop, :-1], distances, out=gradient[start:stop, :-1])
        vertical_stop = min(height - 1, stop)
        delta = np.diff(rgb[start : vertical_stop + 1].astype(np.int16), axis=0).astype(np.float32)
        distances = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
        np.maximum(
            gradient[start + 1 : vertical_stop + 1],
            distances,
            out=gradient[start + 1 : vertical_stop + 1],
        )
        np.maximum(gradient[start:vertical_stop], distances, out=gradient[start:vertical_stop])
    return gradient


def _has_literal_palette(rgb: np.ndarray, visible: np.ndarray, limit: int = 8) -> bool:
    paints: set[int] = set()
    for start in range(0, len(rgb), 64):
        chunk = rgb[start : start + 64]
        packed = chunk[..., 0].astype(np.uint32) << 16
        packed |= chunk[..., 1].astype(np.uint32) << 8
        packed |= chunk[..., 2]
        colors = np.unique(packed[visible[start : start + 64]])
        if len(colors) > limit:
            return False
        paints.update(int(color) for color in colors)
        if len(paints) > limit:
            return False
    return True


def _tile_contrast(
    rgb: np.ndarray,
    outside: np.ndarray,
    coefficients: np.ndarray | None,
    bounds: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray | None]:
    top, bottom, left, right = bounds
    region = np.s_[top:bottom, left:right]
    colors = rgb[region]
    local_background = None
    if coefficients is None:
        # Transport observed colours through the boundary band, rather than
        # extrapolating a perimeter fit across a nonlinear background field.
        indices = distance_transform_edt(
            ~outside[region], return_distances=False, return_indices=True
        )
        local_background = colors[indices[0], indices[1]]
    background = (
        local_background.astype(np.float32)
        if local_background is not None
        else _predict(coefficients, outside.shape, bounds)
    )
    delta = colors.astype(np.float32) - background
    return np.sqrt(np.einsum("ijk,ijk->ij", delta, delta)), local_background


def _edge_tile(
    rgb: np.ndarray,
    outside: np.ndarray,
    coefficients: np.ndarray | None,
    tolerance: float,
    bounds: tuple[int, int, int, int],
    interior: tuple[int, int, int, int],
    recovered_rgba: np.ndarray | None = None,
    final_outside: np.ndarray | None = None,
    protected_interior: np.ndarray | None = None,
) -> np.ndarray:
    top, bottom, left, right = bounds
    height, width = outside.shape
    region = np.s_[top:bottom, left:right]
    exterior = outside[region]
    colors = rgb[region]
    contrast, local_background = _tile_contrast(rgb, outside, coefficients, bounds)
    local_maximum = maximum_filter(contrast, size=2 * _EDGE_RADIUS + 1)
    cores = (contrast >= 0.9 * local_maximum) & (contrast > max(8, 2 * tolerance))
    del local_maximum
    # Stable low-contrast paint supplies its own colour reference. Erosion only
    # selects sample cores; it never erodes the output silhouette.
    uniform = np.ones(exterior.shape, dtype=bool)
    for channel in range(3):
        plane = colors[..., channel]
        uniform &= maximum_filter(plane, size=5) == minimum_filter(plane, size=5)
    flat_cores = binary_erosion(~exterior, iterations=2) & uniform & (contrast > max(4, tolerance))
    cores |= flat_cores
    if protected_interior is None:
        barrier = binary_closing(contrast >= max(48, 4 * tolerance), structure=_CONNECTIVITY)
        protected = (
            binary_dilation(binary_fill_holes(barrier) & ~barrier, structure=_CONNECTIVITY)
            & ~exterior
        )
    else:
        protected = protected_interior[region].copy()
    pale_cores = flat_cores & (contrast < 48)
    pale_protected = np.zeros(exterior.shape, dtype=bool)
    if pale_cores.any():
        indices = distance_transform_edt(~pale_cores, return_distances=False, return_indices=True)
        pale_colors = colors[indices[0], indices[1]].astype(np.int16)
        del indices
        paint_delta = colors.astype(np.int16) - pale_colors
        matching_paint = (
            np.einsum("ijk,ijk->ij", paint_delta.astype(np.int32), paint_delta.astype(np.int32))
            <= max(12, tolerance * 2) ** 2
        )
        pale_protected = binary_propagation(pale_cores, mask=matching_paint & ~exterior)
        protected |= pale_protected
    weak = np.zeros(exterior.shape, dtype=bool)
    if not cores.any():
        return weak
    boundary = exterior if final_outside is None else final_outside[region]
    edge_distance = distance_transform_edt(~boundary)
    candidates = (edge_distance <= (_EDGE_RADIUS if final_outside is None else 3)) & ~boundary
    del edge_distance
    # Analyze only the tile's center. Its context covers both the nearest colour
    # reference and that reference's 24 px neighbourhood, avoiding tile seams.
    inner_top, inner_bottom, inner_left, inner_right = interior
    candidates[:inner_top] = False
    candidates[inner_bottom:] = False
    candidates[:, :inner_left] = False
    candidates[:, inner_right:] = False
    band_rows, band_columns = np.nonzero(candidates)
    indices = distance_transform_edt(~cores, return_distances=False, return_indices=True)
    reference_rows = indices[0, band_rows, band_columns]
    reference_columns = indices[1, band_rows, band_columns]
    del indices
    near = (reference_rows - band_rows) ** 2 + (
        reference_columns - band_columns
    ) ** 2 <= _EDGE_RADIUS**2
    band_rows, band_columns = band_rows[near], band_columns[near]
    reference = colors[reference_rows[near], reference_columns[near]].astype(np.float32)
    if local_background is not None:
        background = local_background[band_rows, band_columns].astype(np.float32)
    else:
        x = (2 * (band_columns + left) / max(1, width - 1) - 1).astype(np.float32)
        y = (2 * (band_rows + top) / max(1, height - 1) - 1).astype(np.float32)
        background = np.clip(
            coefficients[0].astype(np.float32)
            + x[:, None] * coefficients[1].astype(np.float32)
            + y[:, None] * coefficients[2].astype(np.float32),
            0,
            255,
        )
    direction = reference - background
    delta = colors[band_rows, band_columns].astype(np.float32) - background
    norm_squared = np.einsum("ij,ij->i", direction, direction)
    alpha = np.einsum("ij,ij->i", delta, direction) / np.maximum(norm_squared, 1)
    error = delta - alpha[:, None] * direction
    error_squared = np.einsum("ij,ij->i", error, error)
    # Alpha <50% belongs outside the embroidery silhouette. Small negative alpha
    # explains Lanczos/JPEG ringing; clamping it before projection retains a halo.
    uncertain = (
        (norm_squared > max(8, 2 * tolerance) ** 2)
        & (alpha >= -0.15)
        & (alpha < 0.5)
        & (error_squared <= max(12, tolerance * 2) ** 2)
        & ~cores[band_rows, band_columns]
        & ~protected[band_rows, band_columns]
    )
    weak[band_rows[uncertain], band_columns[uncertain]] = True
    if recovered_rgba is not None:
        # Palette reduction must see the foreground paint, rather than a retained
        # black/grey-background mixture that perceptually quantizes as white.
        # Only recover well-supported high-contrast edge blends; interior paint
        # and explicit low-contrast accents keep their source RGB values.
        reliable = (
            (norm_squared > 64**2)
            & (alpha >= 0.5)
            & (alpha <= 1)
            & (error_squared <= max(12, tolerance * 2) ** 2)
            & ~cores[band_rows, band_columns]
            & ~pale_protected[band_rows, band_columns]
            & (recovered_rgba[band_rows + top, band_columns + left, 3] >= 128)
        )
        recovered_rgba[band_rows[reliable] + top, band_columns[reliable] + left, :3] = np.rint(
            reference[reliable]
        ).astype(np.uint8)
    return weak


def _tile_jobs(
    band: np.ndarray,
) -> Iterator[tuple[tuple[int, int, int, int], tuple[int, int, int, int]]]:
    height, width = band.shape
    padding = 2 * _EDGE_RADIUS
    for top in range(0, height, 512):
        bottom = min(height, top + 512)
        for left in range(0, width, 512):
            right = min(width, left + 512)
            if not band[top:bottom, left:right].any():
                continue
            outer_top, outer_bottom = max(0, top - padding), min(height, bottom + padding)
            outer_left, outer_right = max(0, left - padding), min(width, right + padding)
            yield (
                (outer_top, outer_bottom, outer_left, outer_right),
                (top - outer_top, bottom - outer_top, left - outer_left, right - outer_left),
            )


def _refine_edge(
    rgb: np.ndarray,
    outside: np.ndarray,
    coefficients: np.ndarray | None,
    tolerance: float,
    recovered_rgba: np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    # Tiling bounds EDT and RGB float workspaces independently of source size.
    # Maximum-filter dilation cheaply skips every deep-interior tile.
    band = maximum_filter(outside, size=2 * _EDGE_RADIUS + 1, mode="constant", cval=0)
    band &= ~outside
    # Closing/fill-holes must see the whole contour: a ring cut by a tile border
    # is locally open. RGB contrast remains tiled, while topology uses bool masks.
    barrier = np.zeros(outside.shape, dtype=bool)
    for bounds, interior in _tile_jobs(band):
        contrast, _ = _tile_contrast(rgb, outside, coefficients, bounds)
        top, bottom = bounds[0] + interior[0], bounds[0] + interior[1]
        left, right = bounds[2] + interior[2], bounds[2] + interior[3]
        barrier[top:bottom, left:right] = contrast[
            interior[0] : interior[1], interior[2] : interior[3]
        ] >= max(48, 4 * tolerance)
    barrier = binary_closing(barrier, structure=_CONNECTIVITY)
    # A one-pixel border joins antialiased thin outlines containing both their
    # dark edge and enclosed white paint. Protecting the full barrier instead
    # also preserves grey exterior ringing as hundreds of false white regions.
    protected = (
        binary_dilation(binary_fill_holes(barrier) & ~barrier, structure=_CONNECTIVITY) & ~outside
    )
    del barrier
    weak = np.zeros(outside.shape, dtype=bool)
    for bounds, interior in _tile_jobs(band):
        tile = _edge_tile(
            rgb, outside, coefficients, tolerance, bounds, interior, protected_interior=protected
        )
        top, bottom = bounds[0] + interior[0], bounds[0] + interior[1]
        left, right = bounds[2] + interior[2], bounds[2] + interior[3]
        weak[top:bottom, left:right] = tile[interior[0] : interior[1], interior[2] : interior[3]]
    refined = binary_propagation(outside, structure=_CONNECTIVITY, mask=outside | weak)
    if recovered_rgba is not None:
        # Use the final silhouette for the 3 px recovery band, while retaining the
        # original exterior samples for B. The newly removed halo contains blends
        # and cannot serve as a clean background colour reference.
        recovery_band = maximum_filter(refined, size=7, mode="constant", cval=0) & ~refined
        for bounds, interior in _tile_jobs(recovery_band):
            _edge_tile(
                rgb,
                outside,
                coefficients,
                tolerance,
                bounds,
                interior,
                recovered_rgba,
                refined,
                protected,
            )
    return refined, int(np.count_nonzero(refined & ~outside))


def bitmap_foreground(
    rgba: np.ndarray,
    mode: str = "auto",
    diagnostics: dict | None = None,
    *,
    recover_edge_colors: bool = False,
) -> np.ndarray:
    """Remove exterior flat/smooth paint while preserving explicit alpha and counters.

    The method is geometric, not semantic: an ambiguous or textured border is
    retained in auto mode. Source RGB paint is preserved by default; optional
    recovery removes proven background contamination at retained edge pixels.
    """
    if mode not in ("auto", "keep", "remove"):
        raise ValueError("background mode must be 'auto', 'keep' or 'remove'.")
    result = rgba.copy()
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    info = {
        "mode": mode,
        "applied": False,
        "reason": "kept_by_request",
        "model": None,
        "model_fit": None,
        "gradient_step_rgb": None,
        "background_color": None,
        "border_confidence": 0.0,
        "border_error_rgb": None,
        "removed_fraction": 0.0,
        "interior_preserved_pixels": 0,
        "edge_refined_pixels": 0,
        "edge_recovered_pixels": 0,
    }
    if diagnostics is not None:
        diagnostics.update(info)
    if mode == "keep":
        return result
    perimeter = _perimeter(alpha.shape)
    border_alpha = alpha[perimeter]
    if np.any(border_alpha < 128) and (mode == "auto" or np.mean(border_alpha < 128) >= 0.85):
        info["reason"] = "existing_transparency"
        if diagnostics is not None:
            diagnostics.update(info)
        return result
    visible_perimeter = perimeter & (alpha >= 128)
    if not visible_perimeter.any():
        info["reason"] = "transparent_perimeter"
        if diagnostics is not None:
            diagnostics.update(info)
        return result
    border = rgb[visible_perimeter]
    paints, counts = np.unique(border, axis=0, return_counts=True)
    dominant = paints[np.argmax(counts)]
    border_distances = np.linalg.norm(border.astype(float) - dominant, axis=1)
    close = border_distances <= 18
    coefficients = np.zeros((3, 3))
    coefficients[0] = dominant
    plane, errors = _fit_plane(rgb, visible_perimeter)
    plane_error = float(np.percentile(errors, 99))
    compressed_border = False
    # Constant paint is exact when available. Otherwise a well-supported affine
    # field is preferable to a wide global tolerance that eats pale foreground.
    if np.percentile(border_distances, 99) <= 2:
        model = "constant"
        noise = float(np.percentile(border_distances, 99))
        confidence = float(close.mean())
    elif plane_error <= 4 and np.mean(errors <= 6) >= 0.98:
        coefficients = plane
        model = "affine"
        noise = plane_error
        confidence = float(np.mean(errors <= 6))
    elif (
        np.percentile(border_distances, 99) <= 32
        and np.ptp(dominant) <= 4
        and (dominant.max() <= 24 or dominant.min() >= 231)
        and np.percentile(np.ptp(border.astype(np.int16), axis=1), 99) <= 6
        and not _has_literal_palette(rgb, alpha >= 128)
    ):
        # Compressed monochrome canvases can contain slightly different padding
        # strips. Their tightly bounded neutral perimeter still describes one
        # background, unlike literal flag bands or a textured photograph border.
        model = "constant"
        noise = 0.0
        confidence = float(np.mean(border_distances <= 32))
        compressed_border = True
    elif np.mean(border_distances <= 2) >= 0.85:
        model = "constant"
        near = border_distances <= 2
        noise = float(np.percentile(border_distances[near], 99))
        confidence = float(near.mean())
    else:
        model = "smooth"
        gradient = _neighbor_gradient(rgb)
        boundary_gradient = gradient[visible_perimeter]
        gradient_noise = float(np.percentile(boundary_gradient, 99))
        gradient_limit = min(8.0, max(2.0, 2 * gradient_noise + 1))
        confidence = float(np.mean(boundary_gradient <= gradient_limit))
        # Step changes on the perimeter describe different artwork paints, not
        # a continuous background. Do not remove their union simply because each
        # individual side is locally flat.
        if gradient_noise > 4 or boundary_gradient.max() > 12 or confidence < 0.98:
            if mode == "auto":
                info.update(
                    reason="ambiguous_perimeter",
                    border_confidence=float(close.mean()),
                    border_error_rgb=plane_error,
                )
                if diagnostics is not None:
                    diagnostics.update(info)
                return result
            # Explicit removal can still target the dominant border paint when
            # no coherent smooth field exists; it does not flood all edge paints.
            model = "constant"
            noise = float(np.percentile(border_distances[close], 99))
            confidence = float(close.mean())
        else:
            matching = gradient <= gradient_limit
            matching |= alpha < 128
            outside = binary_propagation(
                perimeter & matching, structure=_CONNECTIVITY, mask=matching
            )
            # A smooth backdrop must occupy a useful exterior, rather than scattered
            # patches from photograph texture or small disconnected border colours.
            if outside.mean() < 0.25:
                info.update(
                    reason="ambiguous_perimeter",
                    border_confidence=confidence,
                    border_error_rgb=plane_error,
                )
                if diagnostics is not None:
                    diagnostics.update(info)
                return result
            noise = gradient_noise
            coefficients = None
    tolerance = min(12.0, max(2.0, 3 * noise + 2))
    if coefficients is not None:
        residual = _residual(rgb, coefficients)
        matching = residual <= tolerance
        if compressed_border:
            # Match only observed border shades. A sphere around the dominant
            # white could otherwise erase a distinct pale foreground core.
            tree = cKDTree(paints[np.linalg.norm(paints.astype(float) - dominant, axis=1) <= 32])
            for start in range(0, len(rgb), 64):
                chunk = rgb[start : start + 64]
                distances = tree.query(chunk.reshape(-1, 3))[0].reshape(chunk.shape[:2])
                matching[start : start + 64] = distances <= tolerance
        matching |= alpha < 128
        outside = binary_propagation(perimeter & matching, structure=_CONNECTIVITY, mask=matching)
        # A perimeter fit alone cannot establish the interior of a gradient.
        # When the affine field leaves a large low-gradient exterior unexplained,
        # use observed local background colours for refinement and propagation.
        if model == "affine":
            gradient = _neighbor_gradient(rgb)
            gradient_limit = min(
                8.0, max(2.0, 2 * float(np.percentile(gradient[visible_perimeter], 99)) + 1)
            )
            smooth_matching = (gradient <= gradient_limit) | (alpha < 128)
            smooth_outside = binary_propagation(
                perimeter & smooth_matching, structure=_CONNECTIVITY, mask=smooth_matching
            )
            if smooth_outside.mean() >= 0.25 and np.any(smooth_outside):
                validation = float(np.percentile(residual[smooth_outside], 95))
                if validation > max(12.0, tolerance * 2):
                    outside = smooth_outside
                    matching = smooth_matching
                    coefficients = None
                    model = "smooth"
        del residual
    if mode == "auto" and model != "constant" and np.all(outside | (alpha < 128)):
        info.update(
            reason="no_distinct_foreground",
            model="smooth_gradient",
            model_fit=model,
            border_confidence=confidence,
            border_error_rgb=round(plane_error, 4) if coefficients is not None else None,
        )
        if diagnostics is not None:
            diagnostics.update(info)
        return result
    # A small exact palette provides no evidence of blended edges. Inferring an
    # alpha against another paint can erase literal 1–4 px accents beside black.
    # Preserve those boundaries; compressed/antialiased inputs still use matting.
    refined_count = 0
    if not _has_literal_palette(rgb, alpha >= 128):
        outside, refined_count = _refine_edge(
            rgb,
            outside,
            coefficients,
            tolerance,
            result if recover_edge_colors else None,
        )
    recovered_count = 0
    if recover_edge_colors:
        for start in range(0, len(rgb), 64):
            recovered_count += np.count_nonzero(
                np.any(result[start : start + 64, :, :3] != rgb[start : start + 64], axis=-1)
            )
    removed = outside & (alpha >= 128)
    result[outside, 3] = 0
    info.update(
        applied=bool(removed.any()),
        reason=(
            "smooth_border_background" if model != "constant" else "border_connected_background"
        )
        if removed.any()
        else "no_border_connected_background",
        model="uniform" if model == "constant" else "smooth_gradient",
        model_fit="compressed_constant" if compressed_border else model,
        gradient_step_rgb=round(noise, 4) if coefficients is None else None,
        background_color=(
            "#" + "".join(f"{int(c):02x}" for c in dominant) if model == "constant" else None
        ),
        border_confidence=confidence,
        border_error_rgb=(
            round(float(np.percentile(border_distances if model == "constant" else errors, 95)), 4)
            if coefficients is not None
            else None
        ),
        removed_fraction=float(removed.mean()),
        interior_preserved_pixels=int((matching & ~outside & (alpha >= 128)).sum()),
        edge_refined_pixels=refined_count,
        edge_recovered_pixels=int(recovered_count),
    )
    if diagnostics is not None:
        diagnostics.update(info)
    return result
