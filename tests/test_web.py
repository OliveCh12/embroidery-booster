import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("flask")
from embroidery_rungs import GenerationParams, generate
from embroidery_rungs.inputs import convert_to_svg, raster_to_svg
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
    response = client.post("/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg")})
    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] and result["direct"]["stats"]["stitches"] > 100
    assert set(result["direct"]["files"]) == {"pes", "dst", "preview_svg", "plan_json"}
    assert result["direct"]["analysis"]
    assert result["direct"]["params"]["hoop_width_mm"] == 100
    for url in result["direct"]["files"].values():
        download = client.get(url)
        assert download.status_code == 200
        assert "attachment" in download.headers["Content-Disposition"]
    preview = client.get(result["direct"]["preview"])
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
    assert capabilities["engine"] == "direct"
    assert capabilities["automatic_variants"] is True
    assert set(capabilities["direct_formats"]) == {"pes", "dst"}
    assert "inkscape" not in capabilities and "inkstitch" not in capabilities
    for fabric, weights in capabilities["material_presets"].items():
        for weight, values in weights.items():
            preset = StitchParams.for_fabric(fabric, thread_weight=int(weight))
            assert values["stitch_spacing"] == preset.satin_spacing_mm
            assert values["pull_compensation"] == preset.pull_compensation_mm


def test_automatic_variant_previews_and_downloads_share_artwork(app):
    client = app.test_client()
    response = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(SVG), "logo.svg"), "compare_strategies": "true"},
    )
    assert response.status_code == 200
    result = response.get_json()
    variants = result["variants"]
    assert 1 <= len(variants) <= 5
    selected = next(v for v in variants if v["id"] == result["recommended_variant"])
    assert selected["direct"] == result["direct"]
    assert len({tuple(v["direct"]["threads"]) for v in variants}) == 1
    urls = {v["direct"]["files"]["plan_json"] for v in variants}
    assert len(urls) == len(variants)
    for variant in variants:
        direct = variant["direct"]
        plan = client.get(direct["files"]["plan_json"]).get_json()
        assert plan["analysis"]["comparison"]["strategy"] == variant["id"]
        assert direct["warnings"] == plan["warnings"]
        assert variant["reasons"]
        assert client.get(direct["files"]["pes"]).data.startswith(b"#PES0060")
        assert client.get(direct["files"]["dst"]).status_code == 200


def test_explicit_fill_ignores_automatic_comparison(app):
    result = (
        app.test_client()
        .post(
            "/api/convert",
            data={
                "file": (io.BytesIO(SVG), "logo.svg"),
                "compare_strategies": "true",
                "stitch_type": "fill",
            },
        )
        .get_json()
    )
    assert result["variants"] == []
    assert result["recommended_variant"] is None
    assert result["direct"]["params"]["stitch_type"] == "fill"


def test_selected_hoop_when_fitting(app):
    source = b'<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="100mm" viewBox="0 0 200 100"><rect width="200" height="100"/></svg>'
    result = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(source), "large.svg"),
            "machine": "generic",
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
    "extra",
    [
        {"stitch_spacing": "nope"},
        {"fill_spacing": "nan"},
        {"hoop_width": "5"},
        {"underlay": "maybe"},
        {"compare_strategies": "maybe"},
        {"density_percent": "79"},
        {"density_percent": "121"},
        {"density_percent": "100.5"},
        {"method": "both"},
        {"debug": "true"},
    ],
)
def test_bad_web_parameters_return_400(app, extra):
    data = {"file": (io.BytesIO(SVG), "logo.svg"), **extra}
    assert app.test_client().post("/api/convert", data=data).status_code == 400
    assert not Path(app.config["OUTPUT_ROOT"]).exists()


def test_web_density_is_applied_once_and_returned_with_effective_pitch(app):
    response = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SVG), "logo.svg"),
            "density_percent": "120",
            "fabric": "stable",
            "stitch_spacing": "0.6",
            "fill_spacing": "0.6",
        },
    )
    assert response.status_code == 200
    params = response.get_json()["direct"]["params"]
    assert params["density_percent"] == 120
    assert params["satin_spacing_mm"] == params["fill_spacing_mm"] == pytest.approx(0.333)


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
    assert result.direct.stats["stitches"] > 0
    assert "evenodd" in Path(destination).read_text()


def test_transparent_raster_touching_edges(tmp_path):
    image = np.zeros((80, 100, 4), dtype=np.uint8)
    image[:40, :80, 3] = 255
    source = tmp_path / "alpha.png"
    Image.fromarray(image).save(source)
    svg = convert_to_svg(source, tmp_path)
    assert generate(svg, tmp_path / "out").direct.stats["stitches"] > 0


def test_blank_image_is_clear(tmp_path):
    source = tmp_path / "blank.png"
    Image.new("RGB", (20, 20), "white").save(source)
    with pytest.raises(ValueError, match="uniform"):
        raster_to_svg(source, tmp_path / "blank.svg")


def test_web_plan_matches_machine_units_and_selected_hoop(app):
    import pyembroidery as pe

    client = app.test_client()
    response = client.post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SVG), "logo.svg"),
            "machine": "brother-skitch-pp1",
            "design_width": "60",
        },
    )
    assert response.status_code == 200
    direct = response.get_json()["direct"]
    plan = client.get(direct["files"]["plan_json"]).get_json()
    assert plan["schema_version"] == 3
    assert plan["units"] == "0.1mm"
    assert plan["hoop"]["width_mm"] == plan["hoop"]["height_mm"] == 100
    assert plan["hoop"]["bounds_mm"] == [-50, -50, 50, 50]
    assert plan["command_codes"]["stitch"] == pe.STITCH
    assert plan["command_codes"]["color_change"] == pe.COLOR_CHANGE
    assert all(abs(x) <= 500 and abs(y) <= 500 for x, y, _ in plan["commands"])
    assert direct["requested_params"]["machine"] == "brother-skitch-pp1"
    assert direct["params"] == plan["params"]
    assert direct["adjustments"] == plan["adjustments"]


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
            "auto_adjust": "false",
        },
    )
    assert response.status_code == 200
    direct = response.get_json()["direct"]
    assert direct["params"]["fabric"] == "stretch"
    assert direct["params"]["satin_spacing_mm"] == 0.5
    assert direct["params"]["pull_compensation_mm"] == 0.25
    assert direct["params"]["stabilizer"] == "cutaway"
    assert direct["decisions"]


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


def test_unsafe_svg_returns_clear_error_and_leaves_no_job(app):
    source = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    response = app.test_client().post(
        "/api/convert", data={"file": (io.BytesIO(source), "bad.svg")}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]
    assert not list(Path(app.config["OUTPUT_ROOT"]).glob("*"))


def test_automatic_adjustments_are_reported(app):
    response = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SVG), "logo.svg"),
            "fabric": "stretch",
            "stitch_spacing": "0.2",
            "underlay": "false",
        },
    )
    assert response.status_code == 200
    direct = response.get_json()["direct"]
    assert direct["requested_params"]["satin_spacing_mm"] == 0.2
    assert direct["params"]["satin_spacing_mm"] >= 0.36
    assert direct["params"]["underlay"]
    assert {a["parameter"] for a in direct["adjustments"]} >= {"satin_spacing_mm", "underlay"}


@pytest.mark.parametrize(
    "error,status", [(RuntimeError("Unsewable geometry"), 422), (OSError("internal"), 500)]
)
def test_failed_job_releases_capacity_and_removes_files(app, monkeypatch, error, status):
    import importlib

    module = importlib.import_module("embroidery_rungs.web.app")
    original = module.generate

    def failed(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, "generate", failed)
    client = app.test_client()
    assert (
        client.post("/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg")}).status_code
        == status
    )
    assert not list(Path(app.config["OUTPUT_ROOT"]).glob("*"))
    monkeypatch.setattr(module, "generate", original)
    assert (
        client.post("/api/convert", data={"file": (io.BytesIO(SVG), "logo.svg")}).status_code == 200
    )
