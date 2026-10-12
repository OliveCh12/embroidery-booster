"""Geometric diagnostics on actual quantized stitches, not a fabric simulation."""

from __future__ import annotations

import numpy as np
import pyembroidery as pe
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, label


def satin_crowding(plan, minimum_mm):
    """Count nearby repeated top penetrations in the local satin fan, excluding locks."""
    count = 0
    for block in plan.blocks:
        if block.kind != "satin":
            continue
        points = block.points[2:-2]
        crowded = np.zeros(len(points), dtype=bool)
        for lag in (2, 4, 6, 8):
            crowded[lag:] |= (
                np.linalg.norm(points[lag:] - points[:-lag], axis=1) < minimum_mm - 0.050001
            )
        count += int(crowded.sum())
    return count


def measure_plan(plan, target, pixels_per_mm, offset_px, thread_mm=0.3):
    """Audit only the quantized top layer, excluding underlay, locks and travel."""
    commands = []
    for block in plan.blocks:
        if block.kind not in ("satin", "fill", "running") or len(block.points) < 2:
            continue
        points = np.rint(block.points * 10).astype(int)
        commands.append([int(points[0, 0]), int(points[0, 1]), pe.JUMP])
        commands.extend([[int(x), int(y), pe.STITCH] for x, y in points])
    if not commands:
        commands = [[0, 0, pe.JUMP], [0, 0, pe.END]]
    return measure_stitches(commands, plan.origin_mm, target, pixels_per_mm, offset_px, thread_mm)


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
    distances = (
        distance_transform_edt(~covered)[target] / pixels_per_mm
        if covered.any()
        else np.full(np.count_nonzero(target), np.hypot(*target.shape) / pixels_per_mm)
    )
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
