"""Estimated paint references require local opaque source evidence."""

from __future__ import annotations

import json

import numpy as np
import pytest

from embroidery_rungs.interpretation.paint_reference import discover_flat_paints, region_counts


def _source():
    rgba = np.full((100, 200, 4), 255, dtype=np.uint8)
    rgba[..., :3] = (238, 32, 32)
    rgba[:, 150:, :3] = (32, 32, 238)
    rgba[40:60, 40:60, :3] = (135, 32, 135)
    # An antialiasing colour can share an entire edge yet have no local core.
    rgba[:, 149, :3] = (135, 32, 135)
    rgba[:8, :8, 3] = 0
    rgba[:8, :8, :3] = (0, 255, 0)
    return rgba


def test_reference_retains_an_interior_accent_but_not_a_distant_same_rgb_fringe():
    source = _source()
    reference = discover_flat_paints(source, 10, max_colors=3)
    assert reference is not None
    assert reference.paints == (0x2020EE, 0x872087, 0xEE2020)
    paint = reference.paint_mask(0x872087)
    assert paint[40:60, 40:60].all()
    assert not paint[:, 149].any()
    assert int(paint.sum()) == 400
    assert not reference.paint_mask(0x00FF00).any()
    diagnostics = json.loads(json.dumps(reference.diagnostics(), allow_nan=False))
    assert diagnostics["core_pixels"]["#872087"] == 18 * 18
    assert diagnostics["evidence"] == "opaque_four_neighbour_cores"


def test_a_core_is_not_recovered_from_partial_alpha_or_hidden_rgb():
    source = _source()
    source[..., 3] = 200
    assert discover_flat_paints(source, 10, max_colors=3) is None
    source[..., 3] = 0
    assert discover_flat_paints(source, 10, max_colors=3) is None


@pytest.mark.parametrize("side,expected", [(4, False), (5, True)])
def test_rare_paint_requires_nine_opaque_core_pixels(side, expected):
    source = np.full((100, 100, 4), 255, dtype=np.uint8)
    source[..., :3] = (238, 32, 32)
    source[40 : 40 + side, 40 : 40 + side, :3] = (135, 32, 135)
    reference = discover_flat_paints(source, 2.04, max_colors=3)
    assert reference is not None
    assert (0x872087 in reference.paints) == expected
    if expected:
        assert int(reference.paint_mask(0x872087).sum()) == side**2


def test_local_core_support_and_physical_area_are_required_per_component():
    source = _source()
    source[75:80, 40:45, :3] = (135, 32, 135)
    reference = discover_flat_paints(source, 2.04, max_colors=3)
    assert reference is not None
    paint = reference.paint_mask(0x872087)
    assert paint[40:60, 40:60].all()
    assert not paint[75:80, 40:45].any()


def test_many_coloured_flat_bands_exceeding_the_requested_palette_are_not_reinterpreted():
    source = np.full((100, 200, 4), 255, dtype=np.uint8)
    for index in range(10):
        source[:, index * 20 : (index + 1) * 20, :3] = (index * 20, 255 - index * 20, 20)
    assert discover_flat_paints(source, 20, max_colors=6) is None


def test_few_flat_cores_do_not_turn_a_mostly_variable_image_into_a_logo():
    generator = np.random.default_rng(12)
    source = generator.integers(0, 256, (300, 300, 4), dtype=np.uint8)
    source[..., 3] = 255
    source[:20, :20, :3] = (238, 32, 32)
    assert discover_flat_paints(source, 20, max_colors=6) is None


def test_smooth_gradients_without_plateaus_are_not_given_a_flat_palette():
    source = np.full((100, 256, 4), 255, dtype=np.uint8)
    source[..., :3] = np.arange(256, dtype=np.uint8)[None, :, None]
    assert discover_flat_paints(source, 20, max_colors=6) is None


@pytest.mark.parametrize("transform", [np.fliplr, np.flipud, np.rot90])
def test_core_evidence_and_supported_masks_are_invariant_under_flip_and_rotation(transform):
    source = _source()
    before = discover_flat_paints(source, 10, max_colors=3)
    changed = transform(source)
    width = 10 * (changed.shape[1] + 2) / (source.shape[1] + 2)
    after = discover_flat_paints(changed, width, max_colors=3)
    assert before is not None and after is not None
    assert before.diagnostics() == after.diagnostics()
    for paint in before.paints:
        assert np.array_equal(transform(before.paint_mask(paint)), after.paint_mask(paint))


def test_discovery_does_not_modify_the_original_rgba():
    source = _source()
    original = source.copy()
    reference = discover_flat_paints(source, 10, max_colors=3)
    assert reference is not None
    for paint in reference.paints:
        reference.paint_mask(paint)
    assert np.array_equal(source, original)


def _scalar_core_evidence(rgba, max_colors):
    counts = {}
    visible = sum(int(pixel[3]) >= 128 for row in rgba for pixel in row)
    for y in range(1, len(rgba) - 1):
        for x in range(1, rgba.shape[1] - 1):
            centre = tuple(int(value) for value in rgba[y, x])
            if centre[3] != 255:
                continue
            if all(
                tuple(int(value) for value in rgba[ny, nx]) == centre
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
            ):
                paint = (centre[0] << 16) | (centre[1] << 8) | centre[2]
                counts[paint] = counts.get(paint, 0) + 1
    if len(counts) > max_colors or not visible or sum(counts.values()) / visible < 0.5:
        return None
    paints = {paint: count for paint, count in counts.items() if count >= 9}
    return paints or None


@pytest.mark.parametrize("layout", ["normal", "flip", "rotate", "fortran", "channels"])
def test_word_core_detection_matches_scalar_rgba_evidence_across_layouts_and_alpha(layout):
    source = _source()
    source[20, 20, 3] = 254
    source[22, 22, 3] = 127
    if layout == "flip":
        source = np.fliplr(source)
    elif layout == "rotate":
        source = np.rot90(source)
    elif layout == "fortran":
        source = np.asfortranarray(source)
    elif layout == "channels":
        source = np.repeat(source, 2, axis=-1)[..., ::2]
    before = source.copy()
    expected = _scalar_core_evidence(source, 3)
    reference = discover_flat_paints(source, 10, max_colors=3)
    assert reference is not None and expected is not None
    assert dict(zip(reference.paints, reference.core_counts, strict=True)) == expected
    assert np.array_equal(source, before)


def test_word_core_detection_keeps_evidence_at_tile_boundaries():
    source = np.full((257, 263, 4), 255, dtype=np.uint8)
    source[..., :3] = (238, 32, 32)
    source[245:255, 100:130, :3] = (135, 32, 135)
    reference = discover_flat_paints(source, 10, max_colors=3)
    expected = _scalar_core_evidence(source, 3)
    assert reference is not None and expected is not None
    assert dict(zip(reference.paints, reference.core_counts, strict=True)) == expected


@pytest.mark.parametrize("count", [0, 1, 12, 1000, 65537])
@pytest.mark.parametrize("masked", [False, True])
@pytest.mark.parametrize("dtype", [np.int32, np.uint32, np.uint64])
def test_region_histogram_matches_scalar_counts_for_dense_sparse_masks_and_strides(
    count, masked, dtype
):
    if count < 65537:
        values = np.arange(320, dtype=np.uint64) % (count + 1)
    else:
        values = np.resize(np.array([0, 7, 65537, 65536], dtype=np.uint64), 320)
    groups = values.astype(dtype).reshape(16, 20).T
    mask = (np.arange(320).reshape(16, 20) % 3 == 0).T if masked else None
    expected = np.zeros(count + 1, dtype=np.uint32)
    for y in range(groups.shape[0]):
        for x in range(groups.shape[1]):
            if mask is None or mask[y, x]:
                expected[int(groups[y, x])] += 1
    if count == 1:
        # Preserve the original single-component shortcut's unused zero bin.
        expected[0] = 0
    actual = region_counts(groups, count, mask=mask)
    assert actual.dtype == np.uint32
    assert np.array_equal(actual, expected)


def test_dense_histogram_allocations_are_bounded_per_tile(monkeypatch):
    groups = (np.arange(140_000, dtype=np.int32) % 13).reshape(350, 400)
    expected = np.array([np.count_nonzero(groups == index) for index in range(13)], np.uint32)
    calls = []
    original = np.bincount

    def bounded(values, *, minlength):
        calls.append((len(values), minlength))
        assert len(values) <= 65_536
        assert minlength <= 65_537
        return original(values, minlength=minlength)

    monkeypatch.setattr(np, "bincount", bounded)
    assert np.array_equal(region_counts(groups, 12), expected)
    assert len(calls) == 3


def test_sparse_high_label_ids_keep_the_bounded_unique_path(monkeypatch):
    groups = np.array([[0, 7, 100_000], [100_000, 7, 0]], dtype=np.uint32)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Sparse high IDs must not allocate a large histogram per tile.")

    monkeypatch.setattr(np, "bincount", forbidden)
    counts = region_counts(groups, 100_000)
    assert counts[0] == counts[7] == counts[100_000] == 2
    assert np.count_nonzero(counts) == 3
