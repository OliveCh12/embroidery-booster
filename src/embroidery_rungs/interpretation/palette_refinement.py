"""Refine reduced bitmap thread colours without changing their cleaned masks."""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2lab

from ..colors import _rgb_histogram

_CHUNK_PIXELS = 100_000
_MIN_CORE_PIXELS = 9
_MIN_SHIFT_DELTA_E = 3.0
_MIN_PALETTE_SEPARATION = 8.0


def _weighted_percentile(values, counts, percentile):
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    cumulative = np.cumsum(counts[order], dtype=np.int64)
    rank = (int(cumulative[-1]) - 1) * percentile / 100
    low, high = int(np.floor(rank)), int(np.ceil(rank))
    first = ordered[np.searchsorted(cumulative, low, side="right")]
    last = ordered[np.searchsorted(cumulative, high, side="right")]
    return float(first + (last - first) * (rank - low))


def _colour_errors(values, counts, old_lab, candidate_lab):
    before, after = np.empty(len(values)), np.empty(len(values))
    for start in range(0, len(values), _CHUNK_PIXELS):
        stop = min(start + _CHUNK_PIXELS, len(values))
        labs = rgb2lab(values[None, start:stop, :] / 255)[0]
        before[start:stop] = np.linalg.norm(labs - old_lab, axis=1)
        after[start:stop] = np.linalg.norm(labs - candidate_lab, axis=1)
    pixels = int(counts.sum())
    return {
        name: {
            "mean_delta_e": float(np.dot(errors, counts) / pixels),
            "p95_delta_e": _weighted_percentile(errors, counts, 95),
            "squared_error": float(np.dot(errors * errors, counts)),
        }
        for name, errors in (("before", before), ("after", after))
    }


def _mode_core_pixels(rgba, labels, label_id, mode):
    height, width = labels.shape
    if min(height, width) < 3:
        return 0
    rows = max(1, _CHUNK_PIXELS // width)
    count = 0
    for start in range(1, height - 1, rows):
        stop = min(start + rows, height - 1)
        centre = rgba[start:stop, 1:-1]
        core = (labels[start:stop, 1:-1] == label_id) & (centre[..., 3] == 255)
        core &= np.all(centre[..., :3] == mode, axis=2)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = rgba[start + dy : stop + dy, 1 + dx : width - 1 + dx]
            core &= (neighbour[..., 3] == 255) & np.all(neighbour[..., :3] == mode, axis=2)
        count += int(core.sum())
    return count


def refine_bitmap_palette(rgba, labels, palette):
    """Try observed opaque modes on fixed labels after reduced-bitmap cleanup.

    The caller limits this optional step to cleanup-enabled palette fallbacks.
    Per-label source colour error must improve without moving a single boundary.
    """
    rgba, labels = np.asarray(rgba), np.asarray(labels)
    if rgba.ndim != 3 or rgba.shape[-1] != 4 or rgba.dtype != np.uint8:
        raise ValueError("Palette refinement requires uint8 RGBA pixels.")
    if labels.shape != rgba.shape[:2] or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("Palette refinement labels must match the RGBA grid.")
    result = list(palette)
    if labels.size and (labels.min() < 0 or labels.max() > len(result)):
        raise ValueError("Palette refinement labels must refer to the supplied palette.")
    report = {
        "policy": "source_mode_on_fixed_labels",
        "masks_unchanged": True,
        "refined_colors": 0,
        "count": 0,
        "changes": [],
        "candidates": [],
    }
    if not result:
        return result, report
    paints = np.array([[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in result])
    paint_labs = rgb2lab(paints[None, ...] / 255)[0]
    for index, old in enumerate(palette, 1):
        mask = (labels == index) & (rgba[..., 3] >= 128)
        if not mask.any():
            continue
        values, counts = _rgb_histogram(rgba[..., :3][mask])
        mode_index = int(counts.argmax())
        mode = values[mode_index]
        candidate = "#" + "".join(f"{int(c):02x}" for c in mode)
        record = {
            "label": index,
            "old": old,
            "proposed": candidate,
            "pixels": int(counts.sum()),
            "source_mode_pixels": int(counts[mode_index]),
            "source_mode_fraction": float(counts[mode_index] / counts.sum()),
            "accepted": False,
        }
        report["candidates"].append(record)
        candidate_lab = rgb2lab(mode[None, None, :] / 255)[0, 0]
        shift = float(np.linalg.norm(candidate_lab - paint_labs[index - 1]))
        record["shift_delta_e"] = shift
        if shift < _MIN_SHIFT_DELTA_E:
            record["reason"] = "small_colour_shift"
            continue
        cores = (
            _mode_core_pixels(rgba, labels, index, mode)
            if counts[mode_index] >= _MIN_CORE_PIXELS
            else 0
        )
        record.update(
            opaque_core_pixels=cores,
            opaque_core_fraction=cores / record["pixels"],
        )
        if cores < _MIN_CORE_PIXELS:
            record["reason"] = "insufficient_opaque_source_core"
            continue
        if np.linalg.norm(paint_labs - candidate_lab, axis=1).argmin() != index - 1:
            record["reason"] = "source_mode_matches_other_paint"
            continue
        errors = _colour_errors(values, counts, paint_labs[index - 1], candidate_lab)
        record.update(errors)
        before, after = errors["before"], errors["after"]
        if after["mean_delta_e"] > 0.8 * before["mean_delta_e"]:
            record["reason"] = "insufficient_mean_improvement"
        elif after["p95_delta_e"] > before["p95_delta_e"]:
            record["reason"] = "p95_colour_regression"
        elif after["squared_error"] > before["squared_error"]:
            record["reason"] = "squared_colour_error_regression"
        else:
            result[index - 1] = candidate
            record.update(accepted=True, reason="source_colour_error_improved")
    if any(record["accepted"] for record in report["candidates"]):
        proposed = np.array([[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in result])
        proposed_labs = rgb2lab(proposed[None, ...] / 255)[0]
        distances = np.linalg.norm(proposed_labs[:, None] - proposed_labs[None, ...], axis=2)
        np.fill_diagonal(distances, np.inf)
        if len(set(result)) != len(result) or distances.min() < _MIN_PALETTE_SEPARATION:
            result = list(palette)
            for record in report["candidates"]:
                if record["accepted"]:
                    record.update(accepted=False, reason="palette_separation_regression")
    report["refined_colors"] = sum(record["accepted"] for record in report["candidates"])
    report["count"] = report["refined_colors"]
    report["changes"] = [
        {"from": record["old"], "to": record["proposed"]}
        for record in report["candidates"]
        if record["accepted"]
    ]
    return result, report
