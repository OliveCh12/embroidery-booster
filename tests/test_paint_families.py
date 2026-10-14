"""Noisy source families must remain bounded estimates, never invented threads."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
import resvg_py
from PIL import Image
from scipy.ndimage import label

from embroidery_rungs.colors import bitmap_colors, clean_color_regions
from embroidery_rungs.inputs import _record_interpreted_palette
from embroidery_rungs.interpretation import paint_reference, sampling
from embroidery_rungs.interpretation.paint_reference import (
    discover_flat_paints,
    discover_paint_families,
    match_paint_families,
)


def _source():
    rgba = np.full((100, 200, 4), 255, dtype=np.uint8)
    rgba[..., :3] = (238, 32, 32)
    rgba[:, 150:, :3] = (32, 32, 238)
    rgba[40:60, 40:60, :3] = (135, 32, 135)
    rgba[45:50, 40:60, :3] = (136, 32, 135)
    rgba[50:55, 40:60, :3] = (135, 33, 135)
    # Same estimated paint at a remote blend edge has no independent core.
    rgba[:, 149, :3] = (135, 32, 135)
    rgba[:8, :8] = (0, 255, 0, 0)
    return rgba


def _jpeg_stroke(quality):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="240" '
        'viewBox="0 0 20 5"><rect width="20" height="5" fill="#ee2020"/>'
        '<rect x="15" width="5" height="5" fill="#2020ee"/>'
        '<path d="M6.1 1.25 L7.1 3.75" stroke="#872087" stroke-width="0.5" '
        'stroke-linecap="round"/></svg>'
    )
    png = resvg_py.svg_to_bytes(svg_string=svg, skip_system_fonts=True)
    output = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(output, "JPEG", quality=quality, subsampling=2)
    return np.asarray(Image.open(output).convert("RGBA"))


def _cleaned_palette(rgba):
    labels, colors, reduced = bitmap_colors(rgba, 6)
    labels = clean_color_regions(
        labels, colors, (rgba.shape[1] + 2) / 20, {}, rgba=rgba if reduced else None
    )
    return labels, colors


def test_families_join_nearby_observed_core_shades_without_a_distant_fringe():
    source = _source()
    original = source.copy()
    assert discover_flat_paints(source, 10, max_colors=3) is None
    reference = discover_paint_families(source, 10, max_colors=3)
    assert reference is not None
    assert reference.paints == (0x2020EE, 0x872087, 0xEE2020)
    mask = reference.paint_mask(0x872087)
    assert mask[40:60, 40:60].all()
    assert not mask[:, 149].any()
    assert mask.sum() == 400 and label(mask)[1] == 1
    assert np.array_equal(source, original)
    assert not reference.labels.flags.writeable
    report = reference.diagnostics()
    assert report["evidence"] == "opaque_exact_core_families"
    assert report["core_pixels"]["#872087"] == 18 * 18
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("alpha", [0, 127, 200, 254])
def test_family_anchors_require_opaque_source_cores(alpha):
    source = _source()
    source[..., 3] = alpha
    assert discover_paint_families(source, 10, max_colors=3) is None


def test_an_aggregate_of_tiny_core_islands_does_not_certify_a_family():
    source = _source()
    source[40:60, 40:60, :3] = (238, 32, 32)
    for y in (20, 40, 60):
        source[y : y + 4, 40:44, :3] = (135, 32, 135)
    # Twelve exact cores altogether, but only four within each component.
    assert discover_paint_families(source, 10, max_colors=3) is None


def test_a_wide_soft_fringe_cannot_borrow_the_anchor_of_a_distant_real_accent():
    source = _source()
    source[:, 148:151, :3] = np.array([(134, 32, 134), (135, 32, 135), (136, 32, 136)])
    reference = discover_paint_families(source, 10, max_colors=3)
    assert reference is not None
    violet = reference.paint_mask(0x872087)
    assert violet[40:60, 40:60].all()
    assert not violet[:, 148:151].any()
    assert label(violet)[1] == 1


def test_supported_core_component_also_requires_physical_area():
    source = _source()
    assert discover_paint_families(source, 0.5, max_colors=3) is None
    assert discover_paint_families(source, 10, max_colors=3) is not None


@pytest.mark.parametrize("start,stop", [(80, 120), (110, 120), (0, 255)])
def test_gray_plateau_gradients_are_not_certified_as_flat_paint_families(start, stop):
    source = np.full((100, 960, 4), 255, dtype=np.uint8)
    source[..., :3] = np.linspace(start, stop, 960).astype(np.uint8)[None, :, None]
    assert discover_paint_families(source, 20, max_colors=6) is None


def test_chained_close_shades_do_not_merge_transitively_into_a_family():
    source = _source()
    for index, value in enumerate((100, 104, 108, 112, 116)):
        source[10:30, index * 20 : (index + 1) * 20, :3] = value
    assert discover_paint_families(source, 10, max_colors=12) is None


@pytest.mark.parametrize("layout", ["flip", "rotate", "fortran", "channels"])
def test_family_masks_and_diagnostics_are_invariant_under_array_layout(layout):
    source = _source()
    before = discover_paint_families(source, 10, max_colors=3)
    transform = {"flip": np.fliplr, "rotate": np.rot90}.get(layout, lambda array: array)
    changed = transform(source)
    if layout == "fortran":
        changed = np.asfortranarray(changed)
    elif layout == "channels":
        changed = np.repeat(changed, 2, axis=-1)[..., ::2]
    width = 10 * (changed.shape[1] + 2) / (source.shape[1] + 2)
    after = discover_paint_families(changed, width, max_colors=3)
    assert before is not None and after is not None
    assert before.diagnostics() == after.diagnostics()
    for paint in before.paints:
        assert np.array_equal(transform(before.paint_mask(paint)), after.paint_mask(paint))


def test_matching_is_bounded_injective_and_abstains_from_ambiguous_shades():
    source = ["#2020ee", "#872087", "#ee2020"]
    working = ["#2220ee", "#882086", "#ed2022"]
    assert match_paint_families(source, working) == dict(zip(source, working, strict=True))
    assert match_paint_families(source, ["#882086", "#872087"]) == {}
    assert match_paint_families(["#000000"], ["#ffffff"]) == {}
    assert match_paint_families(["#808080", "#828282"], ["#818181"]) == {}
    assert match_paint_families([], working) == {}


def test_palette_diagnostics_match_estimated_family_shades_but_keep_literals_exact():
    source = ["#2020ee", "#872087", "#ee2020"]
    used = ["#2220ee", "#882086", "#ed2022"]
    masks = {color: {"components": {"relevant_source": 1}} for color in source}
    report = {
        "reference": "source_alpha_and_paint_families",
        "source_palette": source,
        "attempts": [{"masks": masks}],
    }
    _record_interpreted_palette(report, np.array([[1, 2, 3]]), used)
    assert report["missing_source_paints"] == []
    assert report["interpreted_palette_match"] == dict(zip(source, used, strict=True))
    _record_interpreted_palette(report, np.array([[1, 1, 3]]), used)
    assert report["missing_source_paints"] == ["#872087"]
    report["reference"] = "source_alpha_and_literal_paints"
    _record_interpreted_palette(report, np.array([[1, 2, 3]]), used)
    assert report["missing_source_paints"] == source


@pytest.mark.parametrize("quality", [75, 95])
def test_small_jpeg_stroke_survives_real_sampling_palette_and_cleanup(quality, monkeypatch):
    source = _jpeg_stroke(quality)
    with monkeypatch.context() as baseline:
        baseline.setattr(sampling, "discover_paint_families", lambda *_args, **_kwargs: None)
        old, _ = sampling.sample_bitmap(source, 20, max_colors=6)
    labels, colors = _cleaned_palette(old)
    assert len(np.unique(labels)) == 2
    working, report = sampling.sample_bitmap(source, 20, max_colors=6)
    labels, colors = _cleaned_palette(working)
    assert report["reference"] == "source_alpha_and_paint_families"
    assert report["passed"] and report["adapted"]
    assert report["working_pixels"] == [480, 120]
    assert report["literal_palette_colors"] is None
    family = match_paint_families(["#872087"], report["source_palette"])["#872087"]
    observed = report["attempts"][-1]["palette_match"][family]
    assert len(np.unique(labels)) == 3
    violet = labels == colors.index(observed) + 1
    assert label(violet)[1] == 1
    assert not violet[:, 240:].any()
    _record_interpreted_palette(report, labels, colors)
    assert report["missing_source_paints"] == []
    json.dumps(report, allow_nan=False)


def test_ambiguous_jpeg_recovery_keeps_exact_previous_bitmap_and_report(monkeypatch):
    source = _jpeg_stroke(35)
    with monkeypatch.context() as baseline:
        baseline.setattr(sampling, "discover_paint_families", lambda *_args, **_kwargs: None)
        old, old_report = sampling.sample_bitmap(source, 20, max_colors=6)
    result, report = sampling.sample_bitmap(source, 20, max_colors=6)
    assert np.array_equal(result, old)
    retry = report.pop("paint_family_retry")
    assert report == old_report
    assert not retry["adopted"] and retry["baseline_retained"]
    assert retry["unresolved_issues"] > 0
    assert retry["reason"] == "unconfirmed_working_palette_or_geometry"
    assert all("masks" not in attempt for attempt in retry["attempts"])


def test_rejected_family_proof_is_visible_even_when_historical_alpha_passes():
    source = np.full((100, 400, 4), 255, dtype=np.uint8)
    source[..., :3] = (238, 32, 32)
    source[:, :100, :3] = (237, 32, 32)
    source[:, 300:, :3] = (32, 32, 238)
    source[40:45, 150:155, :3] = (135, 32, 135)
    _, report = sampling.sample_bitmap(source, 8.04, max_colors=3)
    assert report["reference"] == "source_alpha"
    assert report["passed"] and report["unresolved_issues"] == 0
    retry = report["paint_family_retry"]
    assert retry["baseline_retained"] and retry["unresolved_issues"] > 0
    assert "#872087" in retry["source_palette"]
    json.dumps(report, allow_nan=False)


def test_successful_literal_and_exact_core_sampling_do_not_retry_families(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("A successful literal/exact-core result must remain unchanged.")

    monkeypatch.setattr(sampling, "discover_paint_families", forbidden)
    source = _source()
    sampling.sample_bitmap(source, 5, max_colors=6)
    source[40:60, 40:60, :3] = (135, 32, 135)
    source[39, 40:60, :3] = (160, 32, 112)
    sampling.sample_bitmap(source, 5, max_colors=6)
    sampling.sample_bitmap(_jpeg_stroke(95), 20, max_colors=6, recover_flat_paints=False)


def test_family_source_lab_work_is_chunked_instead_of_allocating_full_float_image(monkeypatch):
    source = np.repeat(_source(), 6, axis=0)
    original = paint_reference.rgb2lab
    calls = []

    def bounded(rgb):
        calls.append(rgb.shape)
        assert rgb.shape[0] * rgb.shape[1] <= 65_536
        return original(rgb)

    monkeypatch.setattr(paint_reference, "rgb2lab", bounded)
    assert discover_paint_families(source, 10, max_colors=3) is not None
    assert len(calls) > 2


def test_lab_query_is_pixel_bounded_on_extremely_wide_sources(monkeypatch):
    source = np.full((5, 30_000, 4), 255, dtype=np.uint8)
    source[..., :3] = (238, 32, 32)
    source[:, 1000:2000, :3] = (237, 32, 32)
    source[:, 22_500:, :3] = (32, 32, 238)
    original = paint_reference.rgb2lab
    calls = []

    def bounded(rgb):
        calls.append(rgb.shape)
        assert rgb.shape[0] * rgb.shape[1] <= 65_536
        return original(rgb)

    monkeypatch.setattr(paint_reference, "rgb2lab", bounded)
    assert discover_paint_families(source, 80, max_colors=2) is not None
    assert len(calls) > 2


@pytest.mark.parametrize("kind", ["gradient", "photo"])
def test_sixteen_megapixel_nonflat_sources_abstain_before_full_lab_work(kind, monkeypatch):
    if kind == "photo":
        source = np.random.default_rng(14).integers(0, 256, (4000, 4000, 4), dtype=np.uint8)
        source[..., 3] = 255
    else:
        source = np.full((4000, 4000, 4), 255, dtype=np.uint8)
        source[..., :3] = np.linspace(80, 120, 4000).astype(np.uint8)[None, :, None]
    original = paint_reference.rgb2lab

    def bounded(rgb):
        # Only a small seed catalogue is allowed before this source is rejected.
        assert rgb.shape[0] == 1 and rgb.shape[1] <= 2048
        return original(rgb)

    monkeypatch.setattr(paint_reference, "rgb2lab", bounded)
    assert discover_paint_families(source, 20, max_colors=6) is None
