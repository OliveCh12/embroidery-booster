"""Palette acceleration must preserve ordering, ties and all downstream decisions."""

from __future__ import annotations

import numpy as np
import pytest

from embroidery_rungs import colors


def _row_histogram(pixels):
    return np.unique(pixels, axis=0, return_counts=True)


@pytest.mark.parametrize("kind", ["empty", "flat", "ties", "variable", "strided", "reversed"])
def test_packed_rgb_histogram_matches_the_original_row_histogram(kind):
    rng = np.random.default_rng(42)
    pixels = rng.integers(0, 256, (10_003, 3), dtype=np.uint8)
    if kind == "empty":
        pixels = pixels[:0]
    elif kind == "flat":
        pixels[:] = (255, 0, 128)
    elif kind == "ties":
        pixels = np.tile([[0, 255, 255], [1, 0, 0], [0, 255, 254]], (100, 1)).astype(np.uint8)
    elif kind == "strided":
        pixels = pixels[::3]
    elif kind == "reversed":
        pixels = pixels[::-1, ::-1]
    original = pixels.copy()
    actual = colors._rgb_histogram(pixels)
    expected = _row_histogram(pixels)
    for result, reference in zip(actual, expected, strict=True):
        assert result.dtype == reference.dtype
        assert np.array_equal(result, reference)
    assert np.array_equal(pixels, original)


@pytest.mark.parametrize("dtype", [np.uint16, np.int16, np.float32])
def test_other_dtypes_retain_the_previous_histogram_behavior(dtype):
    pixels = np.array([[256, 0, 1], [255, 0, 1], [256, 0, 1]], dtype=dtype)
    for actual, expected in zip(colors._rgb_histogram(pixels), _row_histogram(pixels), strict=True):
        assert actual.dtype == expected.dtype
        assert np.array_equal(actual, expected)


@pytest.mark.parametrize("cleanup", [False, True])
@pytest.mark.parametrize("kind", ["flat", "gradient", "noise", "dark_alpha", "accent"])
def test_bitmap_palette_and_diagnostics_are_exactly_preserved(monkeypatch, cleanup, kind):
    rng = np.random.default_rng(19)
    rgba = np.full((40, 80, 4), 255, dtype=np.uint8)
    rgba[..., :3] = (238, 32, 32)
    rgba[:, 60:, :3] = (32, 32, 238)
    if kind == "gradient":
        rgba[..., :3] = np.arange(80, dtype=np.uint8)[None, :, None] * 3
    elif kind == "noise":
        rgba[..., :3] = rng.integers(0, 256, rgba[..., :3].shape, dtype=np.uint8)
    elif kind == "dark_alpha":
        rgba[..., :3] = (16, 16, 16)
        rgba[:1, :, :3] = (80, 80, 80)
        rgba[:1, :, 3] = 180
        rgba[1:2, :, :3] = (70, 70, 70)
        rgba[1:2, :, 3] = 170
        rgba[2:3, :, :3] = (60, 60, 60)
        rgba[2:3, :, 3] = 160
    elif kind == "accent":
        rgba[10:18, 20:28, :3] = (135, 32, 135)
        rgba[12:18, 19, :3] = (188, 32, 84)
        rgba[:, 59, :3] = (100, 32, 170)
    rgba[30:35, 20:25, 3] = 0
    rgba[30:35, 20:25, :3] = (50, 255, 50)
    original = rgba.copy()
    actual_info = {}
    actual = colors.bitmap_colors(rgba, 6, cleanup=cleanup, diagnostics=actual_info)
    monkeypatch.setattr(colors, "_rgb_histogram", _row_histogram)
    expected_info = {}
    expected = colors.bitmap_colors(rgba, 6, cleanup=cleanup, diagnostics=expected_info)
    assert np.array_equal(actual[0], expected[0])
    assert actual[1:] == expected[1:]
    assert actual_info == expected_info
    assert np.array_equal(rgba, original)
