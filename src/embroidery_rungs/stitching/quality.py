"""Geometric diagnostics on actual quantized stitches, not a fabric simulation."""

from __future__ import annotations

import numpy as np
import pyembroidery as pe
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, label


def measure_stitches(commands, origin_mm, target, pixels_per_mm, offset_px, thread_mm=0.3):
    array = np.asarray(commands)
    codes = array[:, 2].astype(int) & pe.COMMAND_MASK
    sewn = (codes[:-1] == pe.STITCH) & (codes[1:] == pe.STITCH)
    points = array[:, :2] / 10 + origin_mm
    image = Image.new("1", (target.shape[1], target.shape[0]))
    draw = ImageDraw.Draw(image)
    xy = points * pixels_per_mm + offset_px
    for a, b in zip(xy[:-1][sewn], xy[1:][sewn], strict=True):
        draw.line([tuple(a), tuple(b)], fill=1, width=max(1, round(thread_mm * pixels_per_mm)))
    covered = np.asarray(image, dtype=bool)
    intersection = np.count_nonzero(covered & target)
    union = np.count_nonzero(covered | target)
    distances = distance_transform_edt(~covered)[target] / pixels_per_mm
    gaps = np.zeros_like(target)
    gaps[target] = distances > 0.25
    gap_labels, _ = label(gaps)
    gap_areas = np.bincount(gap_labels.ravel())[1:]
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = np.count_nonzero(target)
    return {
        "coverage": round(float(intersection / total), 4),
        "structural_coverage": round(float(np.mean(distances <= 0.25)), 4),
        "iou": round(float(intersection / union), 4),
        "spill_mm2": round(float(np.count_nonzero(covered & ~target) / pixels_per_mm**2), 2),
        "missing_mm2": round(float(np.count_nonzero(target & ~covered) / pixels_per_mm**2), 2),
        "uncovered_p95_mm": round(float(np.percentile(distances, 95)), 3),
        "uncovered_max_mm": round(float(distances.max(initial=0)), 3),
        "structural_missing_mm2": round(float(np.count_nonzero(gaps) / pixels_per_mm**2), 2),
        "largest_gap_mm2": round(float(gap_areas.max(initial=0) / pixels_per_mm**2), 2),
        "stitches": int(np.count_nonzero(codes == pe.STITCH)),
        "trims": int(np.count_nonzero(codes == pe.TRIM)),
        "jumps": int(np.count_nonzero(codes == pe.JUMP)),
        "jump_length_mm": round(float(lengths[codes[1:] == pe.JUMP].sum()), 1),
        "max_stitch_mm": round(float(lengths[sewn].max(initial=0)), 2),
        "short_stitches": int(np.count_nonzero(lengths[sewn] < 0.17)),
    }, image
