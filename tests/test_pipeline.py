import json
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs import GenerationParams, GenerationResult, StitchParams, generate
from embroidery_rungs.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_generate_produces_machine_outputs_by_default(svg_file, tmp_path):
    source = svg_file('<rect x="10" y="20" width="200" height="40"/>')
    original = source.read_bytes()
    result = generate(source, tmp_path / "result")
    assert isinstance(result, GenerationResult)
    assert result.input_path == str(source.resolve())
    assert Path(result.original_path).name == "shape_artwork.svg"
    assert Path(result.original_path).read_bytes() == original == source.read_bytes()
    direct = result.direct
    assert direct.stats["stitches"] > 0
    assert direct.stats["structural_coverage"] >= 0.999
    assert direct.stats["unsafe_connections"] == 0
    assert Path(direct.pes_path).read_bytes().startswith(b"#PES0060")
    assert Path(direct.preview_path).read_bytes().startswith(b"\x89PNG")
    assert Path(direct.dst_path).is_file()
    ET.parse(result.original_path)
    ET.parse(direct.svg_path)
    assert json.loads(Path(direct.plan_path).read_text())["commands"]
    assert result.timings["total"] > 0
    assert set(asdict(result)) == {
        "input_path",
        "original_path",
        "direct",
        "artwork_size_mm",
        "params",
        "warnings",
        "timings",
        "input_analysis",
        "variants",
        "recommended_variant",
        "skipped_variants",
    }
    assert {p.name for p in (tmp_path / "result").iterdir()} == {
        "shape_artwork.svg",
        "shape_direct.pes",
        "shape_direct.dst",
        "shape_direct.png",
        "shape_direct.svg",
        "shape_direct.json",
    }


def test_cli_compare_strategies_exports_structured_alternatives(svg_file, tmp_path, capsys):
    source = svg_file('<rect x="10" y="20" width="200" height="40"/>')
    assert (
        main([str(source), "-o", str(tmp_path / "variants"), "--compare-strategies", "--json"]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["variants"]
    selected = next(v for v in payload["variants"] if v["id"] == payload["recommended_variant"])
    assert payload["direct"]["pes_path"] == selected["direct"]["pes_path"]
    assert Path(payload["direct"]["pes_path"]).is_file()


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.svg")))
def test_all_repository_examples(name, tmp_path):
    result = generate(EXAMPLES / name, tmp_path, GenerationParams(fit_to_hoop=True))
    assert result.direct.stats["stitches"] > 0
    assert result.direct.stats["structural_coverage"] >= 0.999
    assert result.direct.stats["max_stitch_mm"] <= result.direct.params.max_stitch_mm
    assert result.direct.stats["short_stitches"] == 0


def test_physical_size_and_shifted_viewbox(svg_file, tmp_path):
    source = svg_file(
        '<rect x="10" y="20" width="200" height="100"/>',
        width="40mm",
        height="20mm",
        viewbox="10 20 200 100",
    )
    result = generate(source, tmp_path / "out", stitch_params=StitchParams(auto_adjust=False))
    assert result.artwork_size_mm == pytest.approx((40, 20))
    assert result.direct.stats["width_mm"] == pytest.approx(40, abs=0.5)
    assert result.direct.stats["height_mm"] == pytest.approx(20, abs=0.5)
    data = json.loads(Path(result.direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    stitches = commands[commands[:, 2] == pe.STITCH, :2] / 10 + data["origin_mm"]
    assert np.all(stitches >= -0.3)
    assert np.all(stitches <= np.array([40, 20]) + 0.3)


@pytest.mark.parametrize(
    "params",
    [
        GenerationParams(design_width_mm=0),
        GenerationParams(design_width_mm=float("nan")),
        GenerationParams(design_width_mm=float("inf")),
        GenerationParams(design_width_mm=True),
        GenerationParams(raster_threshold=-1),
        GenerationParams(raster_threshold=256),
        GenerationParams(raster_threshold=150.5),
        GenerationParams(raster_threshold=True),
        GenerationParams(fit_to_hoop=1),
        GenerationParams(raster_invert="true"),
    ],
)
def test_invalid_parameters_do_not_create_outputs(svg_file, tmp_path, params):
    source = svg_file('<rect width="100" height="20"/>')
    output = tmp_path / "invalid"
    with pytest.raises(ValueError):
        generate(source, output, params)
    assert not output.exists()


@pytest.mark.parametrize("method", ["inkstitch", "both", "unknown", None])
def test_removed_generation_methods_fail_before_outputs(svg_file, tmp_path, method):
    source = svg_file('<rect width="100" height="20"/>')
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="method must be 'direct'"):
        generate(source, output, method=method)
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
    output = tmp_path / "bad"
    with pytest.raises(ValueError):
        generate(source, output)
    assert not output.exists()


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate(tmp_path / "missing.svg", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_same_input_output_directory(svg_file, tmp_path):
    source = svg_file('<rect width="200" height="40"/>')
    original = source.read_bytes()
    result = generate(source, tmp_path)
    assert source.read_bytes() == original
    assert result.original_path != result.input_path


def test_cli_json_and_errors(svg_file, tmp_path, capsys):
    source = svg_file('<rect width="200" height="40"/>')
    assert main([str(source), "-o", str(tmp_path / "cli"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["input_path"] == str(source.resolve())
    assert data["direct"]["stats"]["stitches"] > 0
    assert Path(data["direct"]["pes_path"]).is_file()
    assert main([str(source), "--stitch-spacing", "nan"]) == 1
    assert "satin_spacing_mm" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--method", "--preview", "--dpi", "--auto-optimize"])
def test_cli_rejects_removed_external_workflow_flags(svg_file, flag):
    source = svg_file('<rect width="200" height="40"/>')
    with pytest.raises(SystemExit) as exc:
        main([str(source), flag])
    assert exc.value.code == 2


def test_failed_export_keeps_previous_outputs(svg_file, tmp_path, monkeypatch):
    import embroidery_rungs.pipeline as pipeline

    source = svg_file('<rect width="200" height="40"/>')
    output = tmp_path / "out"
    generate(source, output)
    saved = {path.name: path.read_bytes() for path in output.iterdir()}

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(pipeline, "export_direct", fail)
    with pytest.raises(OSError, match="disk failure"):
        generate(source, output)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == saved
    assert not list(output.glob(".embroidery-*"))
