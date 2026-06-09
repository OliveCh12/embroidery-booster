"""Automatic parameter search for rung generation.

Given an already-computed skeleton/distance map, try a handful of candidate
(spacing, density) configurations and pick the one with no intersections, a
rung count within range, and the best coverage.
"""

import logging

import numpy as np
from skimage.draw import line
from skimage.morphology import dilation, disk

from .rung_generator import generate_rungs

logger = logging.getLogger(__name__)

# Candidate configurations, ordered roughly from default to sparse/dense.
_CANDIDATES = [
    (3.0, 1.0),   # default
    (4.0, 1.0),   # more spaced
    (5.0, 1.0),
    (6.0, 1.0),   # very spaced
    (3.0, 0.8),   # denser
    (4.0, 0.8),   # dense and spaced
]


_WORLD_UNITS_PER_MM = 96.0 / 25.4


def _spacing_to_px(spacing_mm, density, scale):
    return (spacing_mm / density) * _WORLD_UNITS_PER_MM * scale


def _coverage_ratio(binary_img, rungs):
    coverage = np.zeros_like(binary_img, dtype=np.uint8)
    h, w = coverage.shape
    for (p1_x, p1_y), (p2_x, p2_y) in rungs:
        rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
        valid = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        coverage[rr[valid], cc[valid]] = 255
    coverage_dilated = dilation(coverage, disk(2))
    total = np.sum(binary_img > 0)
    if total == 0:
        return 0.0
    covered = np.sum((binary_img > 0) & (coverage_dilated > 0))
    return covered / total


def optimize_rung_parameters(skeleton, distance, binary_img, scale):
    """Find optimal (spacing, density) using the precomputed skeleton.

    Returns ``(spacing_mm, density, rungs_count, bridges_count, coverage)`` or
    ``None`` if no configuration produced any rungs.
    """
    logger.info("🔍 Searching for optimal parameters...")

    def test_config(spacing_mm, density):
        spacing_px = _spacing_to_px(spacing_mm, density, scale)
        try:
            rungs, bridges = generate_rungs(
                skeleton, distance, spacing_px, binary_img, debug_dir=None)
            return len(rungs), len(bridges), rungs
        except Exception as e:
            logger.debug(f"Config spacing={spacing_mm}mm density={density} failed: {e}")
            return 0, 999, []

    scored = []  # (spacing, density, rungs_count, bridges_count, coverage)
    for spacing_mm, density in _CANDIDATES:
        rungs_count, bridges_count, rungs = test_config(spacing_mm, density)
        if rungs_count == 0:
            continue
        coverage = _coverage_ratio(binary_img, rungs)
        scored.append((spacing_mm, density, rungs_count, bridges_count, coverage))
        logger.info(f"  spacing {spacing_mm}mm, density {density}: {rungs_count} rungs, "
                    f"{bridges_count} bridges, {coverage:.1%} coverage")

    if not scored:
        logger.error("❌ No viable configuration found")
        return None

    # Prefer no bridges, then higher coverage, then fewer rungs (efficiency).
    best = max(scored, key=lambda c: (c[3] == 0, c[4], -c[2]))
    logger.info(f"✅ Optimal config: spacing={best[0]}mm, density={best[1]} "
                f"({best[2]} rungs, {best[3]} bridges, {best[4]:.1%} coverage)")
    return best
