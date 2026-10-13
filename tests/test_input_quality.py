"""Source sampling advice and preflight contracts at the real embroidery size."""

import importlib
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.image_processor import render_preview
from embroidery_rungs.input_quality import complete_input_analysis, raster_quality
from embroidery_rungs.inputs import prepare_artwork, raster_to_svg
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="24mm" height="12mm" viewBox="0 0 80 40"><rect x="5" y="5" width="70" height="30" fill="#174f80"/></svg>'


def _png_bytes(image, **settings):
    stream = io.BytesIO()
    image.save(stream, format="PNG", **settings)
    return stream.getvalue()


def _logo(size=(320, 240)):
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).rectangle((80, 80, 239, 159), fill="#174f80")
    return image


def _prepare(source, destination, *, params=None, stitch_params=None):
    destination.mkdir()
    settings = stitch_params or StitchParams()
    artwork, _, analysis = prepare_artwork(
        source,
        destination,
        params or GenerationParams(),
        settings,
        preserve_colors=settings.preserve_colors,
    )
    document, _ = load_svg_paths(artwork)
    complete_input_analysis(document, analysis, source_is_vector=source.suffix.lower() == ".svg")
    return document, analysis


@pytest.fixture
def app(tmp_path):
    pytest.importorskip("flask")
    from embroidery_rungs.web.app import create_app

    return create_app({"TESTING": True, "OUTPUT_ROOT": str(tmp_path / "jobs"), "MAX_JOBS": 1})


@pytest.mark.parametrize(
    "width_mm,status,issue",
    [(80, "poor", "very_low_resolution"), (40, "caution", "low_resolution"), (20, "good", None)],
)
def test_sampling_advice_changes_with_embroidery_size_without_changing_source(
    width_mm, status, issue
):
    quality = raster_quality(
        source_pixels=(320, 240),
        artwork_pixels=(160, 80),
        working_pixels=(160, 80),
        physical_size_mm=(width_mm, width_mm / 2),
        source_format="PNG",
        cleanup={"palette_reduced": False, "palette_colors": 1, "regions_after": 1},
    )
    assert quality["status"] == status
    assert quality["pixels_per_mm"] == 160 / width_mm
    assert quality["effective_dpi"] == pytest.approx(160 / width_mm * 25.4)
    assert quality["recommended_pixels"] == [width_mm * 12, width_mm * 6]
    assert quality["artwork_pixels"] == [160, 80]
    if issue is None:
        assert not quality["issues"]
    else:
        assert issue in quality["issues"]


def test_source_artwork_pixels_are_measured_before_thumbnail(tmp_path):
    image = Image.new("RGB", (1400, 1200), "white")
    ImageDraw.Draw(image).rectangle((200, 300, 1199, 899), fill="#174f80")
    source = tmp_path / "large.png"
    image.save(source)
    _, analysis = _prepare(
        source, tmp_path / "prepared", params=GenerationParams(design_width_mm=20)
    )
    quality = analysis["quality"]
    assert quality["source_pixels"] == [1400, 1200]
    assert quality["artwork_pixels"] == [1000, 600]
    assert quality["working_pixels"] == [240, 144]
    assert quality["pixels_per_mm"] > 40
    assert quality["status"] == "good"


def test_svg_unit_roundoff_cannot_add_a_recommended_pixel_or_flip_sampling_threshold(tmp_path):
    source = tmp_path / "sized.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="40mm"><rect width="100" height="100"/></svg>'
    )
    document, _ = load_svg_paths(source)
    analysis = {
        "cleanup": {},
        "quality": raster_quality(
            source_pixels=(480, 240),
            artwork_pixels=(480, 240),
            working_pixels=(480, 240),
            physical_size_mm=(80, 40),
            source_format="PNG",
            cleanup={},
        ),
    }
    complete_input_analysis(document, analysis)
    assert analysis["quality"]["physical_size_mm"] == [80, 40]
    assert analysis["quality"]["recommended_pixels"] == [960, 480]
    assert analysis["quality"]["pixels_per_mm"] == 6
    assert analysis["quality"]["status"] == "good"


def test_unused_gradient_definitions_do_not_misclassify_flat_vector_artwork(tmp_path):
    source = tmp_path / "unused-gradient.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="20mm"><defs><linearGradient id="unused"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="50" height="50" fill="black"/></svg>'
    )
    _, analysis = _prepare(source, tmp_path / "prepared")
    assert analysis["quality"]["status"] == "good"
    assert analysis["quality"]["issues"] == []


def test_dpi_metadata_cannot_inflate_a_low_resolution_source(tmp_path):
    qualities = []
    image = _logo()
    for dpi in (72, 1200):
        source = tmp_path / f"logo-{dpi}.png"
        image.save(source, dpi=(dpi, dpi))
        _, analysis = _prepare(
            source,
            tmp_path / f"prepared-{dpi}",
            params=GenerationParams(design_width_mm=80),
        )
        qualities.append(analysis["quality"])
    assert qualities[0] == qualities[1]
    assert qualities[0]["status"] == "poor"
    assert qualities[0]["effective_dpi"] < 60


def test_source_and_artwork_dimensions_follow_exif_orientation(tmp_path):
    image = Image.new("RGB", (240, 160), "white")
    ImageDraw.Draw(image).rectangle((40, 60, 119, 99), fill="#174f80")
    exif = Image.Exif()
    exif[274] = 6
    source = tmp_path / "rotated.png"
    image.save(source, exif=exif)
    document, analysis = _prepare(source, tmp_path / "prepared")
    assert analysis["quality"]["source_pixels"] == [160, 240]
    assert analysis["quality"]["artwork_pixels"] == [40, 80]
    assert document.height > document.width


@pytest.mark.parametrize("width_mm,fit", [(20, False), (80, False), (200, True)])
def test_raster_quality_uses_final_document_size_including_hoop_fit(tmp_path, width_mm, fit):
    source = tmp_path / "logo.png"
    _logo().save(source)
    document, analysis = _prepare(
        source,
        tmp_path / "prepared",
        params=GenerationParams(design_width_mm=width_mm, fit_to_hoop=fit),
        stitch_params=StitchParams(hoop_width_mm=50, hoop_height_mm=40),
    )
    quality = analysis["quality"]
    final_size = [document.width / UNITS_PER_MM, document.height / UNITS_PER_MM]
    assert quality["physical_size_mm"] == pytest.approx(final_size)
    assert quality["pixels_per_mm"] == pytest.approx(
        min(pixels / millimeters for pixels, millimeters in zip([160, 80], final_size, strict=True))
    )
    assert quality["status"] == (
        "good" if width_mm == 20 else "poor" if width_mm == 80 else "caution"
    )
    if fit:
        assert final_size[0] == pytest.approx(48)
        assert final_size[1] <= 38


def test_monochrome_quality_preserves_transparent_counters_and_source_bytes(tmp_path):
    image = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 139, 139), fill="black")
    draw.rectangle((60, 60, 99, 99), fill=(0, 0, 0, 0))
    source = tmp_path / "counter.png"
    image.save(source)
    original = source.read_bytes()
    diagnostics = {}
    destination = raster_to_svg(
        source, tmp_path / "counter.svg", width_mm=40, diagnostics=diagnostics
    )
    document, _ = load_svg_paths(destination)
    preview = Image.open(
        io.BytesIO(render_preview(destination, 40, 40, max_dimension=160))
    ).convert("RGBA")
    assert source.read_bytes() == original
    assert preview.getpixel((80, 80))[3] == 0
    assert preview.getpixel((35, 35))[3] == 255
    assert diagnostics["quality"]["kind"] == "monochrome"
    assert diagnostics["quality"]["artwork_pixels"] == [120, 120]
    complete_input_analysis(document, diagnostics)
    assert diagnostics["quality"]["physical_size_mm"] == pytest.approx([40, 40])


def test_vector_quality_has_no_fictitious_pixel_resolution_after_resizing(tmp_path):
    source = tmp_path / "drawing.svg"
    source.write_bytes(SVG)
    document, analysis = _prepare(
        source, tmp_path / "prepared", params=GenerationParams(design_width_mm=60)
    )
    quality = analysis["quality"]
    assert quality["source_type"] == "vector"
    assert quality["status"] == "good"
    assert quality["physical_size_mm"] == pytest.approx([60, 30])
    assert quality["source_pixels"] is quality["pixels_per_mm"] is quality["effective_dpi"] is None
    assert not quality["issues"]
    assert document.width / UNITS_PER_MM == pytest.approx(60)


def test_svg_gradients_are_reported_as_many_shades_without_rasterizing_vector_source(tmp_path):
    source = tmp_path / "gradient.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 80 40">'
        '<defs><linearGradient id="g"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs>'
        '<rect width="80" height="40" fill="url(#g)"/></svg>'
    )
    original = source.read_bytes()
    _, analysis = _prepare(source, tmp_path / "prepared")
    assert source.read_bytes() == original
    assert analysis["quality"]["source_type"] == "vector"
    assert analysis["quality"]["status"] == "caution"
    assert "many_shades" in analysis["quality"]["issues"]
    assert analysis["quality"]["working_pixels"] is None


def test_bitmap_gradient_reports_palette_reduction_without_claiming_logo_fidelity(tmp_path):
    image = Image.new("RGB", (240, 120))
    row = [(20 + round(210 * x / 239), 60, 230 - round(210 * x / 239)) for x in range(240)]
    image.putdata(row * 120)
    source = tmp_path / "gradient.png"
    image.save(source)
    _, analysis = _prepare(
        source,
        tmp_path / "prepared",
        params=GenerationParams(design_width_mm=20, background_mode="keep"),
        stitch_params=StitchParams(max_colors=4),
    )
    quality = analysis["quality"]
    assert quality["kind"] == "many_shades"
    assert quality["status"] == "caution"
    assert {"many_shades", "palette_reduced"} <= set(quality["issues"])
    assert quality["color_count"] <= 4


def test_detected_file_encoding_not_filename_determines_lossy_source_advice(tmp_path):
    source = tmp_path / "jpeg-with-png-name.png"
    _logo().save(source, format="JPEG", quality=95)
    _, analysis = _prepare(source, tmp_path / "prepared")
    assert analysis["quality"]["format"] == "JPEG"
    assert "lossy_source" in analysis["quality"]["issues"]


def test_explicit_svg_background_retracing_is_reported_without_claiming_source_pixels(tmp_path):
    source = tmp_path / "background.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 160 80">'
        '<rect width="160" height="80" fill="white"/>'
        '<rect x="40" y="20" width="80" height="40" fill="#174f80"/></svg>'
    )
    _, analysis = _prepare(
        source, tmp_path / "prepared", params=GenerationParams(background_mode="remove")
    )
    quality = analysis["quality"]
    assert quality["source_type"] == "vector"
    assert quality["status"] == "caution"
    assert "svg_background_retraced" in quality["issues"]
    assert quality["working_pixels"] is not None
    assert quality["source_pixels"] is quality["pixels_per_mm"] is None


def test_preflight_does_not_call_generation_or_persist_job_outputs(app, monkeypatch):
    module = importlib.import_module("embroidery_rungs.web.app")

    def unexpected_generation(*args, **kwargs):
        pytest.fail("Preflight must not generate stitches or machine files")

    monkeypatch.setattr(module, "generate", unexpected_generation)
    root = Path(app.config["OUTPUT_ROOT"])
    existing = root / "saved.pes"
    root.mkdir()
    existing.write_bytes(b"previous machine output")
    response = app.test_client().post(
        "/api/analyze", data={"file": (io.BytesIO(_png_bytes(_logo())), "logo.png")}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"]
    assert set(payload) == {"success", "input_analysis"}
    assert sorted(root.iterdir()) == [existing]
    assert existing.read_bytes() == b"previous machine output"


@pytest.mark.parametrize("raster", [False, True])
def test_preflight_and_real_generation_report_identical_final_input_analysis(app, tmp_path, raster):
    body = _png_bytes(_logo()) if raster else SVG
    name = "logo.png" if raster else "logo.svg"
    response = app.test_client().post(
        "/api/analyze",
        data={
            "file": (io.BytesIO(body), name),
            "design_width": "20",
            "fit_to_hoop": "true",
            "hoop_width": "50",
            "hoop_height": "40",
            "fabric": "stable",
            "stitch_type": "fill",
            "underlay": "false",
        },
    )
    assert response.status_code == 200
    assert not Path(app.config["OUTPUT_ROOT"]).exists()
    source = tmp_path / name
    source.write_bytes(body)
    stitch_params = StitchParams.for_fabric(
        "stable", hoop_width_mm=50, hoop_height_mm=40, underlay=False, stitch_type="fill"
    )
    generated = generate(
        source,
        tmp_path / "machine",
        GenerationParams(design_width_mm=20, fit_to_hoop=True),
        stitch_params=stitch_params,
    )
    assert response.get_json()["input_analysis"] == generated.input_analysis
    assert Path(generated.direct.pes_path).read_bytes().startswith(b"#PES")


@pytest.mark.parametrize(
    "settings",
    [
        {"design_width": "nan"},
        {"fit_to_hoop": "maybe"},
        {"raster_cleanup": "maybe"},
        {"raster_threshold": "256"},
        {"max_colors": "0"},
        {"stitch_type": "imaginary"},
        {"dpi": "1200"},
    ],
)
def test_preflight_and_generation_reject_the_same_invalid_settings_without_outputs(app, settings):
    errors = []
    for endpoint in ("/api/analyze", "/api/convert"):
        response = app.test_client().post(
            endpoint, data={"file": (io.BytesIO(SVG), "logo.svg"), **settings}
        )
        assert response.status_code == 400
        errors.append(response.get_json()["error"])
    assert errors[0] == errors[1]
    assert not Path(app.config["OUTPUT_ROOT"]).exists()


@pytest.mark.parametrize(
    "body,name",
    [
        (b"not an image", "bad.png"),
        (b"<svg broken", "bad.svg"),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><g><image href="data:image/png;base64,aGVsbG8=" width="20" height="20"/></g></svg>',
            "embedded.svg",
        ),
    ],
)
def test_invalid_file_bytes_or_nested_bitmaps_fail_preflight_and_conversion(app, body, name):
    for endpoint in ("/api/analyze", "/api/convert"):
        response = app.test_client().post(endpoint, data={"file": (io.BytesIO(body), name)})
        assert response.status_code == 400
        assert response.get_json()["error"]
    root = Path(app.config["OUTPUT_ROOT"])
    assert not root.exists() or not list(root.iterdir())


@pytest.mark.parametrize("endpoint", ["/api/analyze", "/api/convert"])
def test_preflight_shares_json_request_size_limit(tmp_path, endpoint):
    pytest.importorskip("flask")
    from embroidery_rungs.web.app import create_app

    root = tmp_path / "jobs"
    app = create_app({"TESTING": True, "OUTPUT_ROOT": str(root), "MAX_CONTENT_LENGTH": 100})
    response = app.test_client().post(endpoint, data={"file": (io.BytesIO(SVG), "drawing.svg")})
    assert response.status_code == 413
    assert response.get_json()["error"]
    assert not root.exists()


def test_preflight_shares_decoded_image_pixel_limit(app, monkeypatch):
    import embroidery_rungs.inputs as inputs

    monkeypatch.setattr(inputs, "MAX_RASTER_PIXELS", 4000)
    body = _png_bytes(Image.new("RGB", (64, 64), "black"))
    for endpoint in ("/api/analyze", "/api/convert"):
        response = app.test_client().post(endpoint, data={"file": (io.BytesIO(body), "large.png")})
        assert response.status_code == 400
        assert "megapixels" in response.get_json()["error"]
    root = Path(app.config["OUTPUT_ROOT"])
    assert not root.exists() or not list(root.iterdir())
