"""Palette-only source proof must preserve cleaned geometry and rare paint."""

import numpy as np
import pytest
from skimage.color import rgb2lab

from embroidery_rungs.interpretation.palette_refinement import (
    _weighted_percentile,
    refine_bitmap_palette,
)


def canvas(rgb=(243, 118, 34)):
    rgba = np.full((40, 60, 4), 255, np.uint8)
    rgba[..., :3] = rgb
    return rgba, np.ones(rgba.shape[:2], np.uint8)


def test_observed_orange_replaces_biased_representative_without_mutating_masks_or_source():
    rgba, labels = canvas()
    rgba[:, 30:, :3] = (15, 46, 77)
    labels[:, 30:] = 2
    rgba[15:18, 10:13, 3] = 0
    labels[15:18, 10:13] = 0
    original_rgba, original_labels = rgba.copy(), labels.copy()
    palette = ["#c0692f", "#0f2e4d"]
    rgba.flags.writeable = labels.flags.writeable = False
    actual, report = refine_bitmap_palette(rgba, labels, palette)
    assert actual == ["#f37622", "#0f2e4d"]
    assert palette == ["#c0692f", "#0f2e4d"]
    np.testing.assert_array_equal(rgba, original_rgba)
    np.testing.assert_array_equal(labels, original_labels)
    assert report["masks_unchanged"]
    assert report["count"] == 1
    assert report["changes"] == [{"from": "#c0692f", "to": "#f37622"}]
    candidate = report["candidates"][0]
    assert candidate["opaque_core_pixels"] >= 9
    assert candidate["source_mode_fraction"] == 1
    assert candidate["after"]["mean_delta_e"] == 0
    assert candidate["after"]["p95_delta_e"] == 0


@pytest.mark.parametrize("percentile", [0, 5, 50, 95, 100])
def test_histogram_percentile_is_exactly_the_expanded_pixel_percentile(percentile):
    values = np.array([3.0, 12.0, 5.0, 0.0])
    counts = np.array([2, 7, 3, 11])
    assert _weighted_percentile(values, counts, percentile) == pytest.approx(
        np.percentile(np.repeat(values, counts), percentile), abs=1e-12
    )


def test_small_white_shift_does_not_change_a_thread():
    rgba, labels = canvas((255, 255, 255))
    actual, report = refine_bitmap_palette(rgba, labels, ["#fffffe"])
    assert actual == ["#fffffe"]
    assert report["count"] == 0 and report["changes"] == []
    assert report["candidates"][0]["reason"] == "small_colour_shift"


def test_source_mode_without_an_opaque_local_core_is_not_a_paint_anchor():
    rgba, labels = canvas()
    rgba[..., 3] = 254
    actual, report = refine_bitmap_palette(rgba, labels, ["#c0692f"])
    assert actual == ["#c0692f"]
    assert report["candidates"][0]["opaque_core_pixels"] == 0
    assert report["candidates"][0]["reason"] == "insufficient_opaque_source_core"


def test_source_mode_belonging_to_another_thread_cannot_swap_paints():
    rgba, labels = canvas()
    actual, report = refine_bitmap_palette(rgba, labels, ["#c0692f", "#f37622"])
    assert actual == ["#c0692f", "#f37622"]
    assert report["candidates"][0]["reason"] == "source_mode_matches_other_paint"


def test_mean_improvement_cannot_hide_a_worse_source_error_tail():
    rgba, labels = canvas((126, 139, 95))
    rgba[-8:, :, :3] = (255, 255, 255)
    actual, report = refine_bitmap_palette(rgba, labels, ["#968c64"])
    assert actual == ["#968c64"]
    candidate = report["candidates"][0]
    assert candidate["after"]["mean_delta_e"] < 0.8 * candidate["before"]["mean_delta_e"]
    assert candidate["reason"] == "p95_colour_regression"


def test_two_proposals_that_approach_each_other_keep_the_entire_old_palette():
    rgba, labels = canvas((245, 117, 20))
    rgba[:, 30:, :3] = (245, 123, 20)
    labels[:, 30:] = 2
    palette = ["#f56414", "#f58c14"]
    actual, report = refine_bitmap_palette(rgba, labels, palette)
    assert actual == palette
    assert report["count"] == 0
    assert all(c["reason"] == "palette_separation_regression" for c in report["candidates"])


def test_exact_paints_and_a_one_pixel_black_accent_stay_exact():
    rgba, labels = canvas()
    rgba[20, 20, :3] = 0
    labels[20, 20] = 2
    actual, report = refine_bitmap_palette(rgba, labels, ["#f37622", "#000000"])
    assert actual == ["#f37622", "#000000"]
    assert report["count"] == 0


def test_smooth_gradient_has_no_flat_mode_core_and_keeps_its_palette():
    from embroidery_rungs.colors import separate_colors

    yy, xx = np.indices((90, 128))
    rgba = np.full((90, 128, 4), 255, np.uint8)
    rgba[..., :3] = np.stack((xx * 2, yy * 2, xx + yy), axis=-1)
    labels, palette, _ = separate_colors(rgba, 6)
    actual, report = refine_bitmap_palette(rgba, labels, palette)
    assert actual == palette
    assert report["count"] == 0


def test_per_label_error_statistics_match_all_actual_source_pixels():
    rgba, labels = canvas()
    rgba[10:15, :, :3] = (240, 119, 33)
    _, report = refine_bitmap_palette(rgba, labels, ["#c0692f"])
    candidate = report["candidates"][0]
    actual_labs = rgb2lab(rgba[None, ..., :3] / 255)[0].reshape(-1, 3)
    for field, color in (("before", [192, 105, 47]), ("after", [243, 118, 34])):
        paint_lab = rgb2lab(np.array(color)[None, None, :] / 255)[0, 0]
        errors = np.linalg.norm(actual_labs - paint_lab, axis=1)
        assert candidate[field]["mean_delta_e"] == pytest.approx(errors.mean())
        assert candidate[field]["p95_delta_e"] == pytest.approx(np.percentile(errors, 95))
        assert candidate[field]["squared_error"] == pytest.approx((errors**2).sum())
