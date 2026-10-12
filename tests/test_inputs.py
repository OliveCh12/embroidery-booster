import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
import pytest
from PIL import Image, ImageDraw
from shapely import intersects, linestrings
from shapely.geometry import box

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.cli import main
from embroidery_rungs.image_processor import render_preview
from embroidery_rungs.inputs import raster_to_svg
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths


def bitmap(path, *, transparent=False):
    image = Image.new(
        "RGBA" if transparent else "RGB", (240, 140), (255, 255, 255, 0) if transparent else "white"
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 200, 110), fill="black")
    draw.rectangle((95, 50, 145, 90), fill=(255, 255, 255, 0) if transparent else "white")
    image.save(path)
    return image


@pytest.mark.parametrize("transparent", [False, True])
def test_bitmap_library_traces_holes_in_physical_units_without_web(tmp_path, transparent):
    source = tmp_path / "logo.png"
    bitmap(source, transparent=transparent)
    original = source.read_bytes()
    result = generate(source, tmp_path / "output", method="direct")
    assert source.read_bytes() == original
    assert result.direct.stats["width_mm"] <= 80.5
    assert result.direct.stats["height_mm"] <= 41
    assert result.direct.stats["unsafe_connections"] == 0
    assert "evenodd" in Path(result.original_path).read_text()
    assert "Bitmap traced" in result.warnings[0]
    data = json.loads(Path(result.direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = (
        np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
    )
    assert not intersects(linestrings(segments), box(29, 12, 51, 29)).any()
    assert result.direct.stats["structural_coverage"] >= 0.999


@pytest.mark.parametrize("viewbox", ["", 'viewBox="10 20 240 120"'])
def test_explicit_size_scales_svg_and_does_not_overwrite_same_directory_input(tmp_path, viewbox):
    source = tmp_path / "logo.svg"
    source.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120" {viewbox}><rect x="20" y="30" width="200" height="40"/></svg>'
    )
    original = source.read_bytes()
    result = generate(source, tmp_path, GenerationParams(design_width_mm=60), method="both")
    assert source.read_bytes() == original
    assert Path(result.original_path).name == "logo_prepared.svg"
    document, _ = load_svg_paths(result.original_path)
    assert document.width / UNITS_PER_MM == pytest.approx(60)
    assert result.direct.stats["width_mm"] == pytest.approx(50, abs=0.6)


def test_auto_fit_preserves_aspect_and_reports_resizing(tmp_path):
    source = tmp_path / "large.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="100mm" viewBox="0 0 200 100"><rect x="0" y="0" width="200" height="100"/></svg>'
    )
    settings = StitchParams(hoop_width_mm=80, hoop_height_mm=50)
    with pytest.raises(ValueError, match="hoop"):
        generate(source, tmp_path / "original", method="direct", stitch_params=settings)
    result = generate(
        source,
        tmp_path / "fitted",
        GenerationParams(fit_to_hoop=True),
        method="direct",
        stitch_params=settings,
    )
    document, _ = load_svg_paths(result.original_path)
    assert document.width / document.height == pytest.approx(2)
    assert result.direct.stats["width_mm"] <= 80
    assert result.direct.stats["height_mm"] <= 50
    assert any("Artwork sized to 78.0" in warning for warning in result.warnings)


def test_raster_respects_exif_orientation(tmp_path):
    image = Image.new("RGB", (100, 60), "white")
    ImageDraw.Draw(image).rectangle((10, 15, 90, 45), fill="black")
    exif = Image.Exif()
    exif[274] = 6
    source = tmp_path / "camera.jpg"
    image.save(source, exif=exif)
    destination = raster_to_svg(source, tmp_path / "camera.svg")
    document, _ = load_svg_paths(destination)
    assert document.height > document.width * 2


def test_manual_threshold_and_inversion_are_repeatable(tmp_path):
    image = np.full((30, 40), 200, dtype=np.uint8)
    image[5:25, 8:32] = 60
    source = tmp_path / "grays.png"
    Image.fromarray(image).save(source)
    normal = tmp_path / "normal.svg"
    inverted = tmp_path / "inverse.svg"
    raster_to_svg(source, normal, threshold=100)
    raster_to_svg(source, inverted, threshold=100, invert=True)
    assert ET.parse(normal).getroot().find("{*}path").get("d") != ET.parse(inverted).getroot().find(
        "{*}path"
    ).get("d")


@pytest.mark.parametrize(
    "settings",
    [
        {"design_width_mm": float("nan")},
        {"design_width_mm": 0},
        {"raster_threshold": 256},
        {"raster_threshold": 12.5},
        {"fit_to_hoop": "true"},
    ],
)
def test_invalid_input_settings_fail_before_outputs(tmp_path, settings):
    output = tmp_path / "out"
    with pytest.raises(ValueError):
        generate(tmp_path / "missing.svg", output, GenerationParams(**settings))
    assert not output.exists()


def test_cli_generates_bitmap_pes_at_requested_size(tmp_path, capsys):
    source = tmp_path / "logo.png"
    bitmap(source)
    assert (
        main(
            [
                str(source),
                "--method",
                "direct",
                "--design-width",
                "45",
                "--fit-to-hoop",
                "--raster-threshold",
                "128",
                "--output-dir",
                str(tmp_path / "output"),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["direct"]["stats"]["width_mm"] <= 45.5
    assert Path(result["direct"]["pes_path"]).read_bytes().startswith(b"#PES")


def test_very_tall_preview_bounds_both_dimensions(tmp_path):
    source = tmp_path / "tall.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1mm" height="100mm" viewBox="0 0 1 100"><rect width="1" height="100"/></svg>'
    )
    import io

    with Image.open(io.BytesIO(render_preview(source, 1, 100))) as image:
        assert image.height == 1200
        assert 1 <= image.width <= 15


@pytest.mark.parametrize("width,height", [(1, 100), (100, 1)])
def test_extreme_svg_aspect_ratio_keeps_physical_geometry(tmp_path, width, height):
    source = tmp_path / "strip.svg"
    source.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}"/></svg>'
    )
    from svgelements import SVG

    from embroidery_rungs.image_processor import rasterize_svg
    from embroidery_rungs.pipeline import image_scale

    result = generate(source, tmp_path / "out")
    bounds = SVG.parse(result.satin_path).bbox()
    # Running stitches represent a centreline, whose SVG stroke is narrower than the source.
    axis = 1 if height > width else 0
    assert (bounds[axis + 2] - bounds[axis]) / UNITS_PER_MM == pytest.approx(100, abs=0.3)
    document, _ = load_svg_paths(source)
    mask, transform = rasterize_svg(document)
    physical_size = np.array(mask.shape[::-1]) - 6
    physical_size = physical_size / image_scale(transform) / UNITS_PER_MM
    assert physical_size == pytest.approx([width, height], abs=0.3)
