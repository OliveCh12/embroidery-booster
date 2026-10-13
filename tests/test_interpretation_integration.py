import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
import pytest
import resvg_py
from PIL import Image

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.input_quality import complete_input_analysis
from embroidery_rungs.inputs import raster_to_svg
from embroidery_rungs.svg_manager import load_svg_paths


@pytest.mark.parametrize("preserve_colors", [False, True])
def test_raster_contract_reports_canvas_visible_size_and_source_crop(tmp_path, preserve_colors):
    rgba = np.zeros((40, 60, 4), dtype=np.uint8)
    rgba[8:20, 12:28, 3] = 255
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    assert raster_to_svg(
        source, target, width_mm=80, preserve_colors=preserve_colors, diagnostics=diagnostics
    ) == str(target)
    geometry = diagnostics["geometry"]
    assert geometry["source_crop_box_px"] == [12, 8, 28, 20]
    assert geometry["canvas_size_mm"] == pytest.approx([80, 80 * 14 / 18])
    assert geometry["visible_size_mm"] == pytest.approx([80 * 16 / 18, 80 * 12 / 18])
    assert geometry["pixel_size_mm"] == pytest.approx([80 / 18, 80 / 18])
    assert ET.parse(target).getroot().attrib["viewBox"] == "0 0 18 14"


def test_geometry_report_tracks_final_sizing_without_changing_source_crop(tmp_path):
    rgba = np.zeros((40, 60, 4), dtype=np.uint8)
    rgba[8:20, 12:28, 3] = 255
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    raster_to_svg(source, target, width_mm=80, preserve_colors=True, diagnostics=diagnostics)
    svg, _ = load_svg_paths(target)
    svg.width /= 2
    svg.height /= 2
    complete_input_analysis(svg, diagnostics)
    geometry = diagnostics["geometry"]
    assert geometry["canvas_size_mm"] == pytest.approx([40, 31.1111])
    assert geometry["visible_size_mm"] == pytest.approx([40 * 16 / 18, 40 * 12 / 18], abs=1e-4)
    assert geometry["source_crop_box_px"] == [12, 8, 28, 20]
    first = geometry.copy()
    complete_input_analysis(svg, diagnostics)
    assert geometry == first


@pytest.mark.parametrize("preserve_colors", [False, True])
def test_raster_trace_preserves_tiny_alpha_counter_before_machine_sampling(
    tmp_path, preserve_colors
):
    rgba = np.zeros((22, 22, 4), dtype=np.uint8)
    rgba[2:20, 2:20, 3] = 255
    rgba[11, 11, 3] = 0
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    raster_to_svg(
        source,
        target,
        width_mm=1.5,
        preserve_colors=preserve_colors,
        cleanup=False,
        diagnostics=diagnostics,
    )
    tracing = diagnostics["tracing"]
    assert diagnostics["quality"]["working_pixels"] == [18, 18]
    if not preserve_colors:
        assert tracing["fallback"]
        assert tracing["initial"]["paints"]["alpha"]["rendered"]["holes"] == 0
    assert tracing["final"]["changed_pixels"] == 0
    assert tracing["final"]["paints"]["alpha"]["rendered"]["holes"] == 1
    assert ET.parse(target).getroot().attrib["shape-rendering"] == "crispEdges"


def test_embedded_profile_is_normalized_in_the_shared_raster_entry_point(tmp_path):
    from PIL import ImageCms

    image = Image.new("RGB", (24, 24), "red")
    image.info["icc_profile"] = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    image.save(source)
    diagnostics = {}
    raster_to_svg(
        source, target, preserve_colors=True, background_mode="keep", diagnostics=diagnostics
    )
    assert diagnostics["normalization"]["icc_status"] == "converted"
    assert diagnostics["tracing"]["final"]["passed"]
    assert ET.parse(target).find("{http://www.w3.org/2000/svg}path").attrib["fill"] == "#ff0000"


@pytest.mark.parametrize("accent_height", [0.5, 2.5])
def test_half_millimetre_literal_accent_reaches_machine_plan(tmp_path, accent_height):
    pixels_per_mm = 48
    image = Image.new("RGBA", (20 * pixels_per_mm, 5 * pixels_per_mm), "#ee2020")
    image.paste("#2020ee", (15 * pixels_per_mm, 0, 20 * pixels_per_mm, 5 * pixels_per_mm))
    x0, y0 = 320, 60
    image.paste("#872087", (x0, y0, x0 + 24, y0 + round(accent_height * pixels_per_mm)))
    source = tmp_path / "accent.png"
    image.save(source)
    result = generate(
        source,
        tmp_path / "result",
        GenerationParams(design_width_mm=20, background_mode="keep"),
        stitch_params=StitchParams.for_fabric("stable", machine="brother-skitch-pp1"),
    )
    assert "#872087" in result.direct.threads
    assert result.direct.stats["omitted_colors"] == 0
    assert result.direct.stats["unsafe_connections"] == 0
    decisions = [decision for decision in result.direct.decisions if decision["color"] == "#872087"]
    assert decisions
    assert all(decision["method"] != "omitted" for decision in decisions)


@pytest.fixture
def antialiased_accent_png():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 5">'
        '<rect width="20" height="5" fill="#ee2020"/>'
        '<rect x="15" width="5" height="5" fill="#2020ee"/>'
        '<circle cx="6.6667" cy="2.5" r="0.25" fill="#872087"/></svg>'
    )
    return resvg_py.svg_to_bytes(svg_string=svg, width=960, height=240, skip_system_fonts=True)


def test_antialiased_colour_accent_reaches_pes_without_remote_penetrations(
    tmp_path, antialiased_accent_png
):
    source = tmp_path / "antialiased.png"
    source.write_bytes(antialiased_accent_png)
    result = generate(
        source,
        tmp_path / "machine",
        GenerationParams(design_width_mm=20, background_mode="keep"),
        stitch_params=StitchParams.for_fabric("stable", machine="brother-skitch-pp1"),
    )
    assert set(result.direct.threads) == {"#ee2020", "#2020ee", "#872087"}
    assert result.direct.stats["omitted_colors"] == 0
    assert result.direct.stats["unsafe_connections"] == 0
    plan = json.loads(Path(result.direct.plan_path).read_text())
    commands = np.asarray(plan["commands"])
    codes = commands[:, 2].astype(int) & pe.COMMAND_MASK
    passes = np.cumsum(codes == pe.COLOR_CHANGE)
    violet = result.direct.threads.index("#872087")
    points = commands[(codes == pe.STITCH) & (passes == violet), :2]
    assert len(points)
    physical = points / 10 + plan["origin_mm"]
    assert np.linalg.norm(physical - [6.6667, 2.5], axis=1).max() < 1
    for path in (result.direct.pes_path, result.direct.dst_path):
        exported = pe.read(path)
        assert [
            thread.hex_color().lower() for thread in exported.threadlist
        ] == result.direct.threads
        assert np.isfinite(np.asarray(exported.stitches)[:, :2]).all()


def test_preflight_core_diagnostics_match_machine_generation(tmp_path, antialiased_accent_png):
    pytest.importorskip("flask")
    from embroidery_rungs.web.app import create_app

    app = create_app({"TESTING": True, "OUTPUT_ROOT": tmp_path / "jobs"})
    settings = {
        "design_width": "20",
        "background_mode": "keep",
        "fabric": "stable",
        "machine": "brother-skitch-pp1",
        "max_colors": "6",
    }
    client = app.test_client()
    preflight = client.post(
        "/api/analyze",
        data={**settings, "file": (io.BytesIO(antialiased_accent_png), "accent.png")},
    )
    assert preflight.status_code == 200
    assert not (tmp_path / "jobs").exists()
    generated = client.post(
        "/api/convert",
        data={**settings, "file": (io.BytesIO(antialiased_accent_png), "accent.png")},
    )
    assert generated.status_code == 200, generated.get_json()
    assert preflight.get_json()["input_analysis"] == generated.get_json()["input_analysis"]
    report = generated.get_json()["input_analysis"]["resampling"]
    assert report["reference"] == "source_alpha_and_flat_paint_cores"
    assert report["missing_source_paints"] == []
