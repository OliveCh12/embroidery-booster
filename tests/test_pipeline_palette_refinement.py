"""Reduced bitmap colours can improve without moving cleaned artwork geometry."""

import runpy
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from embroidery_rungs import GenerationParams, StitchParams, inputs
from embroidery_rungs.colors import separate_colors

FIXTURE = Path(__file__).resolve().parents[1] / "examples/quality/textured-five-paints.png"


def test_public_generator_matches_png_and_exposes_uncontaminated_reference():
    generator = runpy.run_path(str(FIXTURE.with_suffix(".py")))
    with Image.open(FIXTURE) as image:
        expected = np.asarray(image.convert("RGBA"))
    np.testing.assert_array_equal(generator["generate"](), expected)
    np.testing.assert_array_equal(generator["generate"](), expected)
    reference = generator["reference"]()
    assert reference.shape == expected.shape == (256, 256, 4)
    assert reference.dtype == np.uint8 and np.all(reference[..., 3] == 255)
    expected_paints = (
        (15, 46, 77),
        (126, 139, 95),
        (255, 255, 255),
        (243, 118, 34),
        (245, 228, 198),
    )
    start = 0
    for width, paint in zip((96, 64, 45, 31, 20), expected_paints, strict=True):
        assert np.all(reference[:, start : start + width, :3] == paint)
        start += width
    assert start == 256


def _trace(tmp_path, name, *, cleanup=True):
    destination = tmp_path / name
    report = {}
    inputs.raster_to_svg(
        FIXTURE,
        destination,
        width_mm=80,
        preserve_colors=True,
        max_colors=6,
        background_mode="keep",
        cleanup=cleanup,
        diagnostics=report,
    )
    return ET.parse(destination).getroot(), report


def _geometry(element):
    return (
        element.tag,
        {key: value for key, value in element.attrib.items() if key != "fill"},
        element.text,
        tuple(_geometry(child) for child in element),
    )


def _fills(root):
    return [element.get("fill") for element in root.iter() if element.get("fill")]


def _forbidden(*_args, **_kwargs):
    pytest.fail("Palette refinement must not run for this input policy.")


def test_real_textured_bitmap_refines_after_cleanup_with_identical_svg_geometry(
    tmp_path, monkeypatch
):
    original = FIXTURE.read_bytes()
    events, cleaned = [], []
    real_clean, real_refine = inputs.clean_color_regions, inputs.refine_bitmap_palette

    def clean(*args, **kwargs):
        result = real_clean(*args, **kwargs)
        events.append("cleanup")
        cleaned.append(result.copy())
        return result

    def refine(rgba, labels, palette):
        assert events == ["cleanup"]
        np.testing.assert_array_equal(labels, cleaned[0])
        events.append("refinement")
        return real_refine(rgba, labels, palette)

    with monkeypatch.context() as active:
        active.setattr(inputs, "clean_color_regions", clean)
        active.setattr(inputs, "refine_bitmap_palette", refine)
        actual, report = _trace(tmp_path, "refined.svg")
    assert events == ["cleanup", "refinement"]
    assert report["resampling"]["reference"] == "source_unchanged"
    refinement = report["cleanup"]["palette_refinement"]
    orange = next(c for c in refinement["candidates"] if c["proposed"] == "#f37622")
    assert orange["accepted"] and orange["shift_delta_e"] >= 3
    assert orange["opaque_core_pixels"] >= 9
    assert orange["after"]["mean_delta_e"] <= 0.8 * orange["before"]["mean_delta_e"]
    assert orange["after"]["p95_delta_e"] <= orange["before"]["p95_delta_e"]
    assert orange["after"]["squared_error"] <= orange["before"]["squared_error"]
    assert refinement["masks_unchanged"]

    def identity(_rgba, _labels, palette):
        return list(palette), {
            "count": 0,
            "changes": [],
            "candidates": [],
            "masks_unchanged": True,
        }

    monkeypatch.setattr(inputs, "refine_bitmap_palette", identity)
    baseline, old_report = _trace(tmp_path, "baseline.svg")
    assert _geometry(actual) == _geometry(baseline)
    changes = {change["from"]: change["to"] for change in refinement["changes"]}
    assert _fills(actual) == [changes.get(color, color) for color in _fills(baseline)]
    assert orange["old"] in _fills(baseline) and "#f37622" in _fills(actual)
    assert report["cleanup"]["regions_after"] == old_report["cleanup"]["regions_after"]
    assert report["tracing"]["final"]["passed"] and old_report["tracing"]["final"]["passed"]
    assert FIXTURE.read_bytes() == original


def test_cleanup_opt_out_skips_refinement_and_keeps_historical_palette(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "refine_bitmap_palette", _forbidden)
    root, report = _trace(tmp_path, "literal.svg", cleanup=False)
    with Image.open(FIXTURE) as source:
        _, historical, _ = separate_colors(np.asarray(source.convert("RGBA")), 6)
    assert not report["cleanup"]["enabled"]
    assert "palette_refinement" not in report["cleanup"]
    assert report["resampling"]["interpreted_palette"] == sorted(historical)
    assert set(_fills(root)) == set(historical)


def test_explicit_svg_preparation_never_refines_bitmap_paints(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "refine_bitmap_palette", _forbidden)
    source = tmp_path / "literal.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="40mm" '
        'viewBox="0 0 80 40"><path d="M0 0H40V40H0Z" fill="#f37622"/>'
        '<path d="M40 0H80V40H40Z" fill="#c0692f"/></svg>'
    )
    original = source.read_bytes()
    prepared, _, report = inputs.prepare_artwork(
        source,
        tmp_path,
        GenerationParams(background_mode="keep"),
        StitchParams(max_colors=6),
        preserve_colors=True,
    )
    assert prepared == source and source.read_bytes() == original
    assert report["cleanup"]["reason"] == "vector_artwork_preserved"
    assert "palette_refinement" not in report["cleanup"]


@pytest.mark.parametrize(
    "reference",
    [
        "source_alpha_and_literal_paints",
        "source_alpha_and_flat_paint_cores",
        "source_alpha_and_paint_families",
    ],
)
def test_confirmed_source_paint_references_skip_fallback_refinement(
    tmp_path, monkeypatch, reference
):
    real_sample = inputs.sample_bitmap

    def sampled(*args, **kwargs):
        rgba, report = real_sample(*args, **kwargs)
        _, palette, _ = separate_colors(rgba, 6)
        report.update(reference=reference, source_palette=palette)
        return rgba, report

    monkeypatch.setattr(inputs, "sample_bitmap", sampled)
    monkeypatch.setattr(inputs, "refine_bitmap_palette", _forbidden)
    _, report = _trace(tmp_path, "confirmed.svg")
    assert report["cleanup"]["enabled"] and report["cleanup"]["palette_reduced"]
    assert not report["cleanup"]["flat_paints_recovered"]
    assert report["resampling"]["reference"] == reference
    assert "palette_refinement" not in report["cleanup"]
