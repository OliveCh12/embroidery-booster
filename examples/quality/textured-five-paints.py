"""Generate the original 256×256 five-paint texture fixture with NumPy and Pillow."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

SIDE = 256
WIDTHS = (38, 25, 18, 12, 8)
PAINTS = ((15, 46, 77), (126, 139, 95), (255, 255, 255), (243, 118, 34), (245, 228, 198))


def _bounds() -> np.ndarray:
    return np.rint(np.cumsum(WIDTHS) / sum(WIDTHS) * SIDE).astype(int)


def reference() -> np.ndarray:
    """Return the five pure opaque paint bands before texture and shadows."""
    regions = np.searchsorted(_bounds(), np.arange(SIDE), side="right")
    rgba = np.full((SIDE, SIDE, 4), 255, np.uint8)
    rgba[..., :3] = np.asarray(PAINTS, dtype=np.uint8)[regions]
    return rgba


def generate() -> np.ndarray:
    """Return opaque RGBA paint bands with repeatable 3×3 texture and shadows."""
    side, tile = SIDE, 3
    paints = np.asarray(PAINTS, dtype=np.uint8)
    rng = np.random.default_rng(2406)
    yy, xx = np.indices((side, side))
    bounds = _bounds()
    base = reference()[..., :3].astype(float)
    grid = (side + tile - 1) // tile
    offsets = rng.normal(0, 3, (grid, grid, 3))
    offsets[rng.random((grid, grid)) < 0.16] = 0
    rgb = base + offsets[yy // tile, xx // tile]
    selector = rng.random((grid, grid))
    other = paints[rng.integers(0, len(paints), (grid, grid))]
    amount = rng.uniform(0.05, 0.90, (grid, grid))[yy // tile, xx // tile, None]
    blend = base * (1 - amount) + other[yy // tile, xx // tile] * amount
    textured = selector[yy // tile, xx // tile] < 0.15
    rgb[textured] = blend[textured]
    rgba = np.full((side, side, 4), 255, np.uint8)
    rgba[..., :3] = np.rint(np.clip(rgb, 0, 255)).astype(np.uint8)
    for index in range(37):
        y = 7 + (index * 41) % (side - 14)
        x = 5 + (index * 67) % (bounds[0] - 10)
        rgba[y, x, :3] = (15, 39, 49) if index < 25 else (37, 35, 46)
    return rgba


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=Path(__file__).with_suffix(".png"))
    destination = parser.parse_args().output
    Image.fromarray(generate()).save(destination)
    print(destination)
