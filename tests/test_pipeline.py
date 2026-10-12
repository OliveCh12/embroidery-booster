import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from svgelements import SVG
from svgelements import Path as SVGPath

from embroidery_rungs import GenerationParams, GenerationResult, generate
from embroidery_rungs.cli import main
from embroidery_rungs.svg_manager import INKSTITCH_NS, SVG_NS

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_generate_produces_valid_outputs(svg_file, tmp_path):
    source = svg_file('<rect x="10" y="20" width="200" height="40"/>')
    result = generate(source, tmp_path / "result", GenerationParams(debug=True, auto_optimize=True))
    assert isinstance(result, GenerationResult)
    assert result.columns_count == 1
    assert result.rungs_count >= 3
    assert result.coverage >= 0.98
    for path in (result.original_path, result.rungs_path, result.ready_path, result.satin_path):
        assert Path(path).is_file()
        ET.parse(path)
    assert Path(result.original_path).read_bytes() == source.read_bytes()
    assert {p.name for p in Path(result.debug_dir).glob("*.png")} == {
        "debug_01_original.png",
        "debug_03_distance.png",
        "debug_04_skeleton.png",
        "debug_05_overlay.png",
        "debug_07_coverage.png",
    }
    root = ET.parse(result.satin_path).getroot()
    satin = root.find(f".//{{{SVG_NS}}}path")
    assert satin.get(f"{{{INKSTITCH_NS}}}satin_column") == "true"
    assert result.timings["total"] > 0


@pytest.mark.parametrize("name", [p.name for p in EXAMPLES.glob("*.svg")])
def test_all_repository_examples(name, tmp_path):
    result = generate(EXAMPLES / name, tmp_path)
    assert result.columns_count + result.running_count > 0
    assert 0 < result.coverage <= 1
    ET.parse(result.satin_path)


@pytest.mark.parametrize("dpi", [75, 150, 300])
def test_physical_size_and_shifted_viewbox(svg_file, tmp_path, dpi):
    source = svg_file(
        '<rect x="10" y="20" width="200" height="100"/>',
        width="40mm",
        height="20mm",
        viewbox="10 20 200 100",
    )
    result = generate(source, tmp_path / str(dpi), GenerationParams(dpi=dpi))
    satin = SVG.parse(result.satin_path)
    bbox = satin.bbox()
    assert (bbox[2] - bbox[0]) * 25.4 / 96 == pytest.approx(40, abs=0.4)
    assert (bbox[3] - bbox[1]) * 25.4 / 96 == pytest.approx(20, abs=0.4)
    combined = ET.parse(result.ready_path).getroot()
    group = combined.find(f'{{{SVG_NS}}}g[@id="generated_rungs"]')
    paths = [SVGPath(p.get("d")) for p in group.iter(f"{{{SVG_NS}}}path")]
    assert paths
    for path in paths:
        x0, y0, x1, y1 = path.bbox()
        assert 8 < x0 < x1 + 0.01 < 212
        assert 18 < y0 < y1 + 0.01 < 122


@pytest.mark.parametrize(
    "params",
    [
        GenerationParams(spacing=0),
        GenerationParams(density=-1),
        GenerationParams(spacing=float("nan")),
        GenerationParams(density=float("inf")),
        GenerationParams(dpi=0),
        GenerationParams(dpi=150.5),
        GenerationParams(spacing=0.001),
    ],
)
def test_invalid_parameters_do_not_create_outputs(svg_file, tmp_path, params):
    source = svg_file('<rect width="100" height="20"/>')
    output = tmp_path / "invalid"
    with pytest.raises(ValueError):
        generate(source, output, params)
    assert not output.exists()


@pytest.mark.parametrize(
    "xml",
    [
        "not XML",
        "<svg/>",
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text>Test</text></svg>',
        '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><use href="file:///etc/passwd"/></svg>',
    ],
)
def test_bad_inputs_are_clear_errors(tmp_path, xml):
    source = tmp_path / "bad.svg"
    source.write_text(xml)
    with pytest.raises(ValueError):
        generate(source, tmp_path / "bad")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate(tmp_path / "missing.svg", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_same_input_output_directory(svg_file, tmp_path):
    source = svg_file('<rect width="200" height="40"/>')
    original = source.read_bytes()
    generate(source, tmp_path)
    assert source.read_bytes() == original


def test_point_rail_fans_export_as_two_nondegenerate_inkstitch_rails(svg_file, tmp_path):
    from svgelements import Matrix

    from embroidery_rungs.svg_manager import load_svg_paths, save_satin_svg

    source = svg_file('<path d="M10 10L0 0L0 20Z"/>')
    document, _ = load_svg_paths(source)
    output = tmp_path / "fan.svg"
    element = {"type": "satin", "rail_a": [[10, 10]] * 3, "rail_b": [[0, 0], [0, 10], [0, 20]]}
    save_satin_svg(output, [element], Matrix(), document)
    path = SVGPath(ET.parse(output).getroot().find(f".//{{{SVG_NS}}}path").get("d"))
    rails = [SVGPath(subpath) for subpath in path.as_subpaths()]
    assert len(rails) == 2
    assert len(rails[0]) == len(rails[1]) == 3
    assert 0 < rails[0].length() <= 0.02 * 96 / 25.4 + 0.0001
    assert rails[1].length() > 1


def test_cli_json_and_errors(svg_file, tmp_path, capsys):
    source = svg_file('<rect width="200" height="40"/>')
    assert main([str(source), "-o", str(tmp_path / "cli"), "--json", "--no-preview"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["columns_count"] == 1
    assert main([str(source), "--spacing", "nan"]) == 1
    assert "positive finite" in capsys.readouterr().err


@pytest.mark.parametrize("name", [p.name for p in EXAMPLES.glob("*.svg")])
def test_exported_satin_rails_are_valid_and_paired(name, tmp_path):
    from shapely.geometry import LineString, Polygon

    result = generate(EXAMPLES / name, tmp_path)
    root = ET.parse(result.satin_path).getroot()
    for element in root.iter(f"{{{SVG_NS}}}path"):
        if element.get(f"{{{INKSTITCH_NS}}}satin_column") != "true":
            continue
        parts = list(SVGPath(element.get("d")).as_subpaths())
        assert len(parts) == 2, "Unambiguous paired-node satin must have exactly two rails"
        a, b = [[(s.end.x, s.end.y) for s in part] for part in parts]
        assert len(a) == len(b) >= 3
        assert LineString(a).is_simple and LineString(b).is_simple
        assert Polygon(a + list(reversed(b))).is_valid


def test_failed_export_keeps_previous_outputs(svg_file, tmp_path, monkeypatch):
    import embroidery_rungs.pipeline as pipeline

    source = svg_file('<rect width="200" height="40"/>')
    output = tmp_path / "out"
    first = generate(source, output)
    saved = Path(first.satin_path).read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(pipeline, "save_satin_svg", fail)
    with pytest.raises(OSError, match="disk failure"):
        generate(source, output)
    assert Path(first.satin_path).read_bytes() == saved
    assert not list(output.glob(".rungs-*"))
