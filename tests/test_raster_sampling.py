"""Source geometry and literal accents must survive bounded bitmap reduction."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import label

from embroidery_rungs.colors import bitmap_colors, clean_color_regions
from embroidery_rungs.interpretation import sampling
from embroidery_rungs.interpretation.sampling import sample_bitmap


def _flat_logo(accent_side=24, *, stroke=False):
    rgba = np.zeros((240, 960, 4), dtype=np.uint8)
    rgba[..., :3] = (238, 32, 32)
    rgba[..., 3] = 255
    rgba[:, 720:, :3] = (32, 32, 238)
    rgba[100 : 100 + (120 if stroke else accent_side), 200 : 200 + accent_side, :3] = (
        135,
        32,
        135,
    )
    return rgba


def _old_thumbnail(rgba, physical_width_mm):
    height, width = rgba.shape[:2]
    side = min(2048, max(1, round(physical_width_mm * max(width, height) / width * 12)))
    image = Image.fromarray(rgba)
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    return np.asarray(image)


def _topology(mask):
    components = label(mask)[1]
    background, count = label(~mask, np.ones((3, 3), bool))
    exterior = (
        set(background[0]) | set(background[-1]) | set(background[:, 0]) | set(background[:, -1])
    )
    return components, count - len(exterior - {0})


def _interpreted_paints(rgba, physical_width_mm, max_colors):
    labels, colors, reduced = bitmap_colors(rgba, max_colors)
    labels = clean_color_regions(
        labels,
        colors,
        (rgba.shape[1] + 2) / physical_width_mm,
        {},
        rgba=rgba if reduced else None,
    )
    return {color for index, color in enumerate(colors, 1) if np.any(labels == index)}


def test_normal_flat_design_keeps_the_historical_lanczos_pixels():
    source = _flat_logo(accent_side=48)
    expected = _old_thumbnail(source, 20)
    result, report = sample_bitmap(source, 20, max_colors=3)
    assert np.array_equal(result, expected)
    assert report["passed"]
    assert not report["adapted"]
    assert len(report["attempts"]) == 1
    assert report["working_pixels"] == [240, 60]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("stroke", [False, True])
@pytest.mark.parametrize("width_mm", [20, 80])
def test_half_millimetre_blend_coloured_accent_survives_real_palette_and_cleanup(stroke, width_mm):
    source = _flat_logo(stroke=stroke)
    if width_mm == 80:
        source = np.repeat(np.repeat(source, 4, axis=0), 4, axis=1)
        source[np.all(source[..., :3] == (135, 32, 135), axis=2), :3] = (238, 32, 32)
        source[400 : 400 + (120 if stroke else 24), 800:824, :3] = (135, 32, 135)
    expected_colors = {"#ee2020", "#2020ee", "#872087"}
    assert _interpreted_paints(_old_thumbnail(source, width_mm), width_mm, 3) != expected_colors
    result, report = sample_bitmap(source, width_mm, max_colors=3)
    assert _interpreted_paints(result, width_mm, 3) == expected_colors
    assert report["adapted"]
    assert report["passed"]
    assert "#872087" in report["attempts"][0]["palette_at_risk"]
    assert report["source_palette"] == ["#2020ee", "#872087", "#ee2020"]
    violet = report["attempts"][0]["masks"]["#872087"]
    expected_pixels = (120 if stroke else 24) * 24
    assert violet["source_pixels"] == expected_pixels
    assert violet["source_area_mm2"] == pytest.approx(
        expected_pixels * (width_mm / (source.shape[1] + 2)) ** 2, abs=1e-6
    )


def test_categorical_fallback_keeps_a_rare_quarter_millimetre_accent_without_false_paints():
    source = _flat_logo(accent_side=12)
    result, report = sample_bitmap(source, 20, max_colors=3)
    assert report["passed"]
    assert report["resampling"] == "nearest"
    assert len(report["attempts"]) == 3
    assert _interpreted_paints(result, 20, 3) == {"#ee2020", "#2020ee", "#872087"}
    assert set(map(tuple, np.unique(result[..., :3].reshape(-1, 3), axis=0))) == {
        (238, 32, 32),
        (32, 32, 238),
        (135, 32, 135),
    }


@pytest.mark.parametrize("x", [100, 101, 102, 103])
def test_narrow_alpha_counter_is_preserved_independently_of_grid_phase(x):
    source = np.full((960, 960, 4), 255, dtype=np.uint8)
    source[..., :3] = 0
    source[100:148, x : x + 2, 3] = 0
    assert _topology(source[..., 3] >= 128) == (1, 1)
    assert _topology(_old_thumbnail(source, 20)[..., 3] >= 128) == (1, 0)
    result, report = sample_bitmap(source, 20, max_colors=1)
    assert report["passed"]
    assert report["adapted"]
    assert _topology(result[..., 3] >= 128) == (1, 1)
    assert report["attempts"][0]["masks"]["alpha"]["holes"]["lost"] == 1


def test_two_strokes_are_not_silently_fused():
    source = np.zeros((400, 960, 4), dtype=np.uint8)
    source[..., 0] = 125
    source[100:300, 20:470, 3] = 255
    source[100:300, 472:940, 3] = 255
    assert _topology(_old_thumbnail(source, 20)[..., 3] >= 128)[0] == 1
    result, report = sample_bitmap(source, 20, max_colors=1)
    assert report["passed"]
    assert report["adapted"]
    assert _topology(result[..., 3] >= 128)[0] == 2
    assert report["attempts"][0]["masks"]["alpha"]["components"]["merged"] == 1


def test_a_subthreshold_alpha_fragment_does_not_force_larger_working_grid(monkeypatch):
    source = np.zeros((200, 200, 4), dtype=np.uint8)
    source[15:75, 15:75, 3] = 255
    source[50:55, 75:95, 3] = 255
    working = np.zeros((40, 40, 4), dtype=np.uint8)
    working[3:15, 3:15, 3] = 255
    working[10, 18, 3] = 255
    width_mm = 40 / 12
    assert _topology(source[..., 3] >= 128) == (1, 0)
    assert _topology(working[..., 3] >= 128) == (2, 0)
    assert (width_mm / 42) ** 2 < 0.01
    calls = []

    def controlled_resampling(_source, side, method):
        calls.append((side, method))
        return working

    monkeypatch.setattr(sampling, "_sample", controlled_resampling)
    result, report = sample_bitmap(source, width_mm, max_colors=1)
    assert np.array_equal(result, working)
    assert calls == [(40, Image.Resampling.LANCZOS)]
    assert report["passed"]
    assert not report["adapted"]
    assert not report["topology_preserved"]
    assert report["attempts"][0]["masks"]["alpha"]["components"]["split"] == 0


def test_two_significant_fragments_of_a_source_body_still_fail_the_detail_check():
    source = np.zeros((40, 40), dtype=bool)
    source[3:15, 3:15] = True
    source[10:12, 15:19] = True
    working = np.zeros_like(source)
    working[3:15, 3:15] = True
    working[10:12, 18] = True
    pixel_mm = 0.08
    assert _topology(source) == (1, 0)
    assert _topology(working) == (2, 0)
    assert 2 * pixel_mm**2 >= 0.01
    report = sampling._audit_mask(source, working, pixel_mm, pixel_mm)
    assert report["issues"] > 0
    assert report["components"]["split"] == 1


def test_a_surviving_small_target_cell_is_not_mistaken_for_a_lost_source_detail():
    source = np.zeros((40, 40), dtype=bool)
    source[10:12, 10] = True
    working = np.zeros_like(source)
    working[10, 10] = True
    pixel_mm = 0.08
    assert 2 * pixel_mm**2 >= 0.01 > pixel_mm**2
    report = sampling._audit_mask(source, working, pixel_mm, pixel_mm)
    assert report["components"]["lost"] == 0
    assert report["components"]["split"] == 0


def test_a_significant_body_fragmented_entirely_into_dust_still_fails():
    source = np.zeros((40, 40), dtype=bool)
    source[10:12, 10:14] = True
    working = np.zeros_like(source)
    working[10, 10] = working[11, 13] = True
    pixel_mm = 0.08
    assert _topology(source) == (1, 0)
    assert _topology(working) == (2, 0)
    assert source.sum() * pixel_mm**2 >= 0.01 > pixel_mm**2
    report = sampling._audit_mask(source, working, pixel_mm, pixel_mm)
    assert report["issues"] > 0
    assert report["components"]["split"] == 1


def test_a_new_significant_counter_fails_when_the_source_has_none():
    source = np.ones((40, 40), dtype=bool)
    working = source.copy()
    working[10:14, 10:14] = False
    pixel_mm = 0.08
    assert _topology(source) == (1, 0)
    assert _topology(working) == (1, 1)
    assert 16 * pixel_mm**2 >= 0.01
    report = sampling._audit_mask(source, working, pixel_mm, pixel_mm)
    assert report["holes"]["source"] == 0
    assert report["holes"]["created"] == 1
    assert report["issues"] > 0


def test_insignificant_checkerboard_pixels_do_not_force_resolution_adaptation():
    row, column = np.indices((400, 400))
    source = np.full((400, 400, 4), 255, dtype=np.uint8)
    source[..., :3] = (((row + column) % 2) * 255)[..., None]
    result, report = sample_bitmap(source, 20, max_colors=2)
    assert report["passed"]
    assert not report["adapted"]
    assert not report["topology_preserved"]
    assert np.array_equal(result, _old_thumbnail(source, 20))
    assert report["attempts"][0]["masks"]["#000000"]["components"]["relevant_source"] == 0


def test_subthreshold_counter_loss_is_reported_without_needless_resolution_growth():
    source = np.full((960, 960, 4), 255, dtype=np.uint8)
    source[..., :3] = 0
    source[100:102, 100:102, 3] = 0
    result, report = sample_bitmap(source, 20, max_colors=1)
    assert report["passed"]
    assert not report["topology_preserved"]
    assert not report["adapted"]
    holes = report["attempts"][0]["masks"]["alpha"]["holes"]
    assert holes["source"] == 1
    assert holes["working"] == holes["relevant_source"] == 0
    assert np.array_equal(result, _old_thumbnail(source, 20))
    assert report["detail_scope"] == "graphic_preservation_not_sewability"


def test_budget_exhaustion_remains_visible_and_never_upscales():
    source = np.full((960, 960, 4), 255, dtype=np.uint8)
    source[..., :3] = 0
    source[100:148, 100, 3] = 0
    result, report = sample_bitmap(source, 20, max_colors=1)
    assert not report["passed"]
    assert report["unresolved_issues"] > 0
    assert len(report["attempts"]) <= 3
    assert max(result.shape[:2]) <= 2048
    assert max(attempt["working_pixels"][0] for attempt in report["attempts"]) <= 480
    assert report["attempts"][0]["masks"]["alpha"]["holes"]["relevant_source"] == 1


@pytest.mark.parametrize("transform", [np.fliplr, np.flipud, lambda a: np.rot90(a)])
def test_literal_accent_policy_is_consistent_after_flips_and_right_angle_rotation(transform):
    source = _flat_logo(accent_side=12)
    original, before = sample_bitmap(source, 20, max_colors=3)
    transformed = transform(source)
    rotated_width = 20 * (transformed.shape[1] + 2) / (source.shape[1] + 2)
    result, after = sample_bitmap(transformed, rotated_width, max_colors=3)
    assert before["passed"] == after["passed"] is True
    assert before["adapted"] == after["adapted"] is True
    assert before["resampling"] == after["resampling"] == "nearest"
    assert _interpreted_paints(result, rotated_width, 3) == _interpreted_paints(original, 20, 3)
    if transformed.shape == source.shape:
        assert np.array_equal(result, transform(original))
    else:
        # Historical width includes two padding cells, whereas thumbnail uses
        # the cropped aspect ratio. Rotation can change its rounded side by a
        # few pixels; preserve the same policy and paint topology regardless.
        assert abs(result.shape[0] - transform(original).shape[0]) <= 4
        assert abs(result.shape[1] - transform(original).shape[1]) <= 1
        for paint in ((238, 32, 32), (32, 32, 238), (135, 32, 135)):
            assert _topology(np.all(result[..., :3] == paint, axis=2)) == _topology(
                np.all(original[..., :3] == paint, axis=2)
            )


def test_existing_transparent_margin_and_hidden_rgb_are_not_interpreted_as_paint():
    source = np.zeros((1200, 1200, 4), dtype=np.uint8)
    source[..., :3] = (0, 255, 0)
    source[100:1100, 100:1100] = (120, 0, 0, 255)
    result, report = sample_bitmap(source, 80, max_colors=1)
    assert report["source_palette"] == ["#780000"]
    assert report["passed"]
    assert _topology(result[..., 3] >= 128) == (1, 0)
    assert report["reference"] == "source_alpha_and_literal_paints"


def test_no_resampling_preserves_literal_pixels_alpha_and_input_immutability():
    source = _flat_logo(accent_side=12)[:60, :120].copy()
    source[3, 5] = (12, 200, 30, 125)
    frozen = source.copy()
    result, report = sample_bitmap(source, 80, max_colors=1)
    assert np.array_equal(source, frozen)
    assert np.array_equal(result, frozen)
    assert report["resampling"] == "none"
    assert report["reference"] == "source_unchanged"
    assert report["attempts"] == []


def test_many_shades_use_alpha_only_without_photograph_palette_quantification(monkeypatch):
    generator = np.random.default_rng(5)
    source = generator.integers(0, 256, (1200, 1200, 4), dtype=np.uint8)
    source[..., 3] = 255

    def forbidden_palette_audit(*_args):
        pytest.fail("Many shades must not allocate per-paint maps or run a palette quantizer.")

    monkeypatch.setattr(sampling, "_paint_labels", forbidden_palette_audit)
    result, report = sample_bitmap(source, 80, max_colors=12)
    assert np.array_equal(result, _old_thumbnail(source, 80))
    assert report["reference"] == "source_alpha"
    assert report["literal_palette_colors"] is None
    assert list(report["attempts"][0]["masks"]) == ["alpha"]
    assert len(report["attempts"]) == 1


@pytest.mark.parametrize("width_mm", [np.float32(80), np.int64(80)])
@pytest.mark.parametrize("source_shape", [(500, 1000), (50, 100)])
def test_physical_frames_with_numpy_numbers_are_json_serialisable(width_mm, source_shape):
    height, width = source_shape
    source = np.zeros((height, width, 4), dtype=np.uint8)
    source[..., 3] = 255
    result, report = sample_bitmap(source, width_mm, max_colors=np.int64(2))
    working_height, working_width = result.shape[:2]
    payload = json.loads(json.dumps(report, allow_nan=False))
    assert payload["source_canvas_size_mm"] == pytest.approx([80, 80 * (height + 2) / (width + 2)])
    assert payload["source_pixel_size_mm"] == pytest.approx(80 / (width + 2))
    assert payload["working_canvas_size_mm"] == pytest.approx(
        [80, 80 * (working_height + 2) / (working_width + 2)]
    )
    assert payload["working_pixel_size_mm"] == pytest.approx(80 / (working_width + 2))


@pytest.mark.parametrize("physical_width", [0, -1, float("nan"), float("inf"), True])
def test_invalid_physical_width_is_rejected(physical_width):
    with pytest.raises(ValueError, match="positive finite"):
        sample_bitmap(np.ones((2, 2, 4), np.uint8), physical_width)


@pytest.mark.parametrize("max_colors", [0, 257, 1.5, True])
def test_invalid_palette_budget_is_rejected(max_colors):
    with pytest.raises(ValueError, match="palette limit"):
        sample_bitmap(np.ones((2, 2, 4), np.uint8), 20, max_colors=max_colors)


@pytest.mark.parametrize(
    "array", [np.empty((0, 2, 4), np.uint8), np.ones((2, 2, 3), np.uint8), np.ones((2, 2, 4))]
)
def test_invalid_rgba_is_rejected(array):
    with pytest.raises(ValueError, match="uint8 RGBA"):
        sample_bitmap(array, 20)


def test_oversized_source_is_rejected_before_image_work(monkeypatch):
    source = np.broadcast_to(np.array([1, 2, 3, 255], np.uint8), (4001, 4000, 4))
    monkeypatch.setattr(sampling, "_literal_palette", lambda *_: pytest.fail("Budget first."))
    with pytest.raises(ValueError, match="16 megapixels"):
        sample_bitmap(source, 20)
