import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("flask")
from embroidery_rungs import GenerationParams, generate
from embroidery_rungs.external import _run
from embroidery_rungs.inputs import convert_to_svg, raster_to_svg
from embroidery_rungs.web import services
from embroidery_rungs.web.app import create_app

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="140"><rect x="10" y="20" width="200" height="40"/></svg>'


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "OUTPUT_ROOT": str(tmp_path / "jobs"), "MAX_JOBS": 1})


def test_web_api_upload_download_and_preview(app):
    client = app.test_client()
    index = client.get("/")
    assert index.status_code == 200
    assert index.get_json()["frontend"] == "Next.js"
    response = client.post(
        "/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg"), "debug": "true"}
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] and result["stats"]["columns"] == 1
    assert result["stats"]["coverage"] >= 98
    assert result["warnings"] == []
    assert len(result["debug_images"]) == 5
    for url in result["files"].values():
        download = client.get(url)
        assert download.status_code == 200
        assert "attachment" in download.headers["Content-Disposition"]
    preview = client.get(result["preview"])
    assert preview.status_code == 200
    assert preview.data.startswith(b"\x89PNG")
    assert "nosniff" in preview.headers["X-Content-Type-Options"]
    assert client.get(result["artwork_preview"]).data.startswith(b"\x89PNG")
    assert client.get(result["artwork_svg"]).status_code == 200


def test_api_has_no_duplicate_frontend_and_profiles_share_library_settings(app):
    from embroidery_rungs import StitchParams

    client = app.test_client()
    assert client.get("/static/app.js").status_code == 404
    assert client.get("/static/styles.css").status_code == 404
    capabilities = client.get("/api/capabilities").get_json()
    assert capabilities["recommended_method"] == "direct"
    for fabric, weights in capabilities["material_presets"].items():
        for weight, values in weights.items():
            preset = StitchParams.for_fabric(fabric, thread_weight=int(weight))
            assert values["stitch_spacing"] == preset.satin_spacing_mm
            assert values["pull_compensation"] == preset.pull_compensation_mm


def test_inkstitch_path_uses_selected_hoop_when_fitting(app):
    source = b'<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="100mm" viewBox="0 0 200 100"><rect width="200" height="100"/></svg>'
    result = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(source), "large.svg"),
            "method": "inkstitch",
            "fit_to_hoop": "true",
            "hoop_width": "80",
            "hoop_height": "50",
        },
    )
    assert result.status_code == 200
    assert result.get_json()["artwork_size_mm"] == pytest.approx([78, 39], abs=0.001)


def test_web_bitmap_size_and_interpreted_artwork(app):
    image = Image.new("RGB", (500, 250), "white")
    from PIL import ImageDraw

    ImageDraw.Draw(image).rectangle((50, 50, 450, 200), fill="black")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    client = app.test_client()
    response = client.post(
        "/api/convert",
        data={
            "file": (stream, "image.png"),
            "method": "direct",
            "design_width": "65",
            "fit_to_hoop": "true",
        },
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["converted_from"] == "png"
    assert result["direct"]["stats"]["width_mm"] <= 65.5
    assert client.get(result["artwork_preview"]).data.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "extra", [{"spacing": "nope"}, {"density": "nan"}, {"dpi": "10"}, {"spacing": "0"}]
)
def test_bad_web_parameters_return_400(app, extra):
    data = {"file": (io.BytesIO(SVG), "logo.svg"), **extra}
    assert app.test_client().post("/api/convert", data=data).status_code == 400
    assert not Path(app.config["OUTPUT_ROOT"]).exists()


def test_invalid_upload_is_removed_and_restart_preserves_jobs(app):
    root = Path(app.config["OUTPUT_ROOT"])
    old = root / ("a" * 32)
    old.mkdir(parents=True)
    (old / "old.svg").write_text("saved result")
    create_app({"TESTING": True, "OUTPUT_ROOT": str(root)})
    assert (old / "old.svg").is_file()
    client = app.test_client()
    assert client.post("/api/convert").status_code == 400
    assert (
        client.post("/api/convert", data={"file": (io.BytesIO(b"bad"), "input.svg")}).status_code
        == 400
    )
    assert list(root.iterdir()) == [old]
    assert client.get("/api/file/not-a-job/old.svg").status_code == 400
    assert client.get(f"/api/file/{old.name}/../../pyproject.toml").status_code == 404


def test_upload_limit_is_json(tmp_path):
    app = create_app({"TESTING": True, "OUTPUT_ROOT": str(tmp_path), "MAX_CONTENT_LENGTH": 100})
    response = app.test_client().post("/api/convert", data={"file": (io.BytesIO(SVG), "shape.svg")})
    assert response.status_code == 413
    assert response.get_json()["error"]


def test_busy_server_rejects_extra_job(app, monkeypatch):
    import importlib

    module = importlib.import_module("embroidery_rungs.web.app")
    entered, release = threading.Event(), threading.Event()
    original = module.generate

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "generate", delayed)

    def submit():
        return app.test_client().post("/api/convert", data={"file": (io.BytesIO(SVG), "shape.svg")})

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(submit)
        try:
            assert entered.wait(5)
            assert submit().status_code == 503
        finally:
            release.set()
        assert first.result().status_code == 200


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_opaque_raster_uses_luminance_and_preserves_holes(tmp_path, mode):
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image[10:90, 10:90] = 0
    image[30:70, 30:70] = 255
    source = tmp_path / "raster.png"
    Image.fromarray(image).convert(mode).save(source)
    destination = raster_to_svg(source, tmp_path / "raster.svg")
    result = generate(destination, tmp_path / "out", GenerationParams())
    assert result.columns_count > 0
    assert "evenodd" in Path(destination).read_text()


def test_transparent_raster_touching_edges(tmp_path):
    image = np.zeros((80, 100, 4), dtype=np.uint8)
    image[:40, :80, 3] = 255
    source = tmp_path / "alpha.png"
    Image.fromarray(image).save(source)
    svg = convert_to_svg(source, tmp_path)
    assert generate(svg, tmp_path / "out").columns_count > 0


def test_blank_image_and_missing_tools_are_clear(tmp_path, monkeypatch):
    source = tmp_path / "blank.png"
    Image.new("RGB", (20, 20), "white").save(source)
    with pytest.raises(ValueError, match="uniform"):
        raster_to_svg(source, tmp_path / "blank.svg")
    monkeypatch.setattr(services, "_tool", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        services.export_embroidery("input.svg", tmp_path / "out.zip")


def test_external_tool_timeout_is_clear(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        "embroidery_rungs.external.subprocess.run",
        Mock(side_effect=subprocess.TimeoutExpired("inkstitch", 1)),
    )
    with pytest.raises(RuntimeError, match="timed out"):
        _run(["inkstitch"], timeout=1)


def test_stitch_preview_fits_off_page_drawing(tmp_path, monkeypatch):
    import subprocess

    plan = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
    <g id="embroidery"><path d="M0 0L50 50" stroke="blue"/></g>
    <g id="stitch_plan"><path d="M200 10L250 50L200 50Z" fill="red"/></g></svg>"""
    monkeypatch.setattr(services, "_tool", lambda _: "inkstitch")
    monkeypatch.setattr(
        services, "_run", lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=plan)
    )
    preview = tmp_path / "preview.png"
    source = tmp_path / "input.svg"
    source.write_bytes(SVG)
    services.render_stitch_preview(source, preview)
    with Image.open(preview) as image:
        assert np.asarray(image.getchannel("A")).max() > 0
        assert image.width == 1400
    xml = preview.with_suffix(".svg").read_text()
    assert 'id="embroidery"' not in xml
    assert "stitch_plan" in xml


@pytest.mark.parametrize("method", ["both", "direct"])
def test_direct_web_exports_without_native_tools(app, monkeypatch, method):
    monkeypatch.setattr(
        services, "export_embroidery", Mock(side_effect=AssertionError("native tool used"))
    )
    client = app.test_client()
    result = client.post(
        "/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg"), "method": method}
    ).get_json()
    assert result["success"] and result["method"] == method
    assert result["direct"]["stats"]["stitches"] > 100
    assert len(result["files"]) == 3
    for url in result["direct"]["files"].values():
        response = client.get(url)
        assert response.status_code == 200
        assert "attachment" in response.headers["Content-Disposition"]
    assert client.get(result["direct"]["preview"]).data.startswith(b"\x89PNG")
    assert client.get("/api/capabilities").get_json()["direct"]


@pytest.mark.parametrize(
    "extra",
    [
        {"method": "nope"},
        {"method": "direct", "stitch_spacing": "nan"},
        {"method": "both", "hoop_width": "5"},
    ],
)
def test_bad_direct_web_settings_return_400(app, extra):
    response = app.test_client().post(
        "/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg"), **extra}
    )
    assert response.status_code == 400
    assert not Path(app.config["OUTPUT_ROOT"]).exists()


def test_direct_only_never_invokes_requested_native_export(app, monkeypatch):
    monkeypatch.setattr(
        services, "export_embroidery", Mock(side_effect=AssertionError("native tool used"))
    )
    response = app.test_client().post(
        "/api/convert",
        data={"file": (io.BytesIO(SVG), "logo.svg"), "method": "direct", "export": "true"},
    )
    assert response.status_code == 200


def test_web_material_selection_and_manual_override(app):
    response = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SVG), "fabric.svg"),
            "method": "direct",
            "fabric": "stretch",
            "thread_weight": "60",
            "stabilizer": "cutaway",
            "stitch_spacing": "0.5",
        },
    )
    assert response.status_code == 200
    direct = response.get_json()["direct"]
    assert direct["params"]["fabric"] == "stretch"
    assert direct["params"]["spacing_mm"] == 0.5
    assert direct["params"]["pull_compensation_mm"] == 0.25
    assert direct["params"]["stabilizer"] == "cutaway"
    assert direct["decisions"]


def test_native_settings_bound_underlay_and_preserve_source(tmp_path):
    from xml.etree import ElementTree as ET

    from embroidery_rungs import StitchParams
    from embroidery_rungs.svg_manager import INKSTITCH_NS

    source = tmp_path / "source.svg"
    source.write_bytes(SVG)
    result = generate(source, tmp_path / "out")
    original = Path(result.satin_path).read_bytes()
    params = StitchParams.for_fabric("stretch", max_stitch_mm=6)
    configured = services.configure_native_svg(result.satin_path, tmp_path / "native.svg", params)
    satin = next(e for e in ET.parse(configured).iter() if e.get(f"{{{INKSTITCH_NS}}}satin_column"))
    assert float(satin.get(f"{{{INKSTITCH_NS}}}zigzag_underlay_max_stitch_length_mm")) <= 2.5
    assert float(satin.get(f"{{{INKSTITCH_NS}}}max_stitch_length_mm")) < 6
    assert satin.get(f"{{{INKSTITCH_NS}}}trim_after") == "true"
    assert Path(result.satin_path).read_bytes() == original


def test_quality_data_is_optional_and_served_with_safe_paths(app, tmp_path):
    directory = tmp_path / "quality"
    app.config["QUALITY_REPORT_DIR"] = directory
    client = app.test_client()
    assert not client.get("/api/capabilities").get_json()["quality_report"]
    assert client.get("/quality/").status_code == 404
    directory.mkdir()
    (directory / "comparison.json").write_text('{"results": []}')
    assert client.get("/api/capabilities").get_json()["quality_report"]
    assert client.get("/quality/comparison.json").get_json() == {"results": []}
    assert client.get("/quality/").status_code == 404
    assert client.get("/quality/../outside.txt").status_code == 404


def test_native_export_stats_inspects_encoded_points(tmp_path):
    import zipfile

    import pyembroidery as pe

    pattern = pe.EmbPattern()
    pattern.add_thread("#176d9c")
    pattern.add_stitch_absolute(pe.STITCH, 0, 0)
    pattern.add_stitch_absolute(pe.STITCH, 150, 0)
    pattern.add_command(pe.END)
    pes = tmp_path / "long.pes"
    pe.write_pes(pattern, str(pes), {"encode": False})
    archive = tmp_path / "native.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(pes, "long.pes")
    stats = services.native_export_stats(archive)
    assert stats["max_stitch_mm"] == 15
    assert stats["stitches"] == 2


def test_comparison_preview_keeps_source_viewport(tmp_path, monkeypatch):
    import subprocess
    from xml.etree import ElementTree as ET

    source = tmp_path / "source.svg"
    source.write_bytes(SVG)
    plan = b'<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70"><g id="__inkstitch_stitch_plan__"><path d="M10 20L60 20" stroke="blue"/></g></svg>'
    commands = []
    monkeypatch.setattr(services, "_tool", lambda _: "inkstitch")

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=plan)

    monkeypatch.setattr(services, "_run", run)
    services.render_stitch_preview(source, tmp_path / "preview.png", align_source=True)
    assert "--move-to-side=False" in commands[0]
    root = ET.parse(tmp_path / "preview.svg").getroot()
    assert root.get("viewBox") == "0 0 80 70"
    assert root.get("width") == "80mm"
