"""RGB reuse must preserve Lab decisions, ties, input order and transparency."""

import numpy as np
import pytest
from scipy.spatial import cKDTree
from skimage.color import rgb2lab

from embroidery_rungs import colors


def _pixel_reference(pixels, values, labs):
    tree = cKDTree(labs)
    dtype = np.uint8 if len(labs) < 256 else np.uint16
    assigned = np.empty(len(pixels), dtype=dtype)
    for start in range(0, len(pixels), 100_000):
        stop = min(start + 100_000, len(pixels))
        assigned[start:stop] = tree.query(rgb2lab(pixels[None, start:stop] / 255)[0])[1] + 1
    return assigned


@pytest.mark.parametrize("kind", ["flat", "jpeg", "gradient", "noise", "reversed"])
def test_palette_assignment_matches_pixel_reference(kind):
    rng = np.random.default_rng(2066)
    pixels = rng.integers(0, 256, (100_003, 3), dtype=np.uint8)
    if kind in ("flat", "jpeg", "reversed"):
        paints = rng.integers(0, 256, (9 if kind != "jpeg" else 2048, 3), dtype=np.uint8)
        pixels = paints[rng.integers(0, len(paints), len(pixels))]
    elif kind == "gradient":
        pixels = np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, axis=1)
        pixels = np.tile(pixels, (400, 1))
    if kind == "reversed":
        pixels = pixels[::-1, ::-1]
    packed = pixels.astype(np.uint32)
    values = np.unique((packed[:, 0] << 16) | (packed[:, 1] << 8) | packed[:, 2])
    palette = rng.integers(0, 256, (12, 3), dtype=np.uint8)
    labs = rgb2lab(palette[None, ...] / 255)[0]
    original = pixels.copy()
    assert np.array_equal(
        colors._nearest_palette_labels(pixels, values, labs), _pixel_reference(pixels, values, labs)
    )
    assert np.array_equal(pixels, original)


@pytest.mark.parametrize("max_colors", [1, 6, 12])
@pytest.mark.parametrize("cleanup", [False, True])
def test_palette_reuse_preserves_complete_bitmap_result_and_diagnostics(
    monkeypatch, max_colors, cleanup
):
    rng = np.random.default_rng(32)
    rgba = np.full((160, 240, 4), 255, dtype=np.uint8)
    paints = np.array([[15, 46, 77], [243, 118, 34], [126, 139, 95], [255, 255, 255]])
    rgba[..., :3] = paints[np.indices(rgba.shape[:2])[1] // 60]
    rgba[40:80, 50:150, :3] = np.clip(
        rgba[40:80, 50:150, :3].astype(int) + rng.integers(-4, 5, (40, 100, 3)), 0, 255
    )
    rgba[:4, :, 3] = 0
    info = {}
    actual = colors.bitmap_colors(rgba, max_colors, cleanup=cleanup, diagnostics=info)
    monkeypatch.setattr(colors, "_nearest_palette_labels", _pixel_reference)
    reference_info = {}
    expected = colors.bitmap_colors(rgba, max_colors, cleanup=cleanup, diagnostics=reference_info)
    assert np.array_equal(actual[0], expected[0])
    assert actual[1:] == expected[1:]
    assert info == reference_info


def test_all_256_literal_colors_remain_visible_and_transparent_zero_stays_reserved():
    rgba = np.zeros((17, 16, 4), dtype=np.uint8)
    rgba[:16, :, 0] = np.arange(256, dtype=np.uint8).reshape(16, 16)
    rgba[:16, :, 3] = 255
    labels, palette, reduced = colors.separate_colors(rgba, 256)
    assert not reduced
    assert len(palette) == 256
    assert labels.dtype == np.uint16
    assert set(np.unique(labels[:16])) == set(range(1, 257))
    assert not labels[16].any()
    restored = np.asarray([[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in palette])
    assert np.array_equal(restored[labels[:16] - 1], rgba[:16, :, :3])


def test_repeated_rgb_remapping_keeps_search_and_packing_bounded(monkeypatch):
    paints = np.array([[12, 34, 56], [210, 220, 230]], dtype=np.uint8)
    pixels = paints[np.arange(250_003) % 2]
    packed = paints.astype(np.uint32)
    values = (packed[:, 0] << 16) | (packed[:, 1] << 8) | packed[:, 2]
    labs = rgb2lab(paints[None, ...] / 255)[0]
    original = np.searchsorted
    batches = []

    def bounded(keys, query):
        batches.append(len(query))
        assert query.dtype == np.uint32
        assert len(query) <= 100_000
        return original(keys, query)

    monkeypatch.setattr(np, "searchsorted", bounded)
    actual = colors._nearest_palette_labels(pixels, values, labs)
    assert np.array_equal(actual, np.arange(len(pixels)) % 2 + 1)
    assert batches == [100_000, 100_000, 50_003]
