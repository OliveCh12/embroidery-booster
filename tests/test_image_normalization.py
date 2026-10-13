import io
import sys

import numpy as np
import pytest
from PIL import Image, ImageCms

from embroidery_rungs.interpretation.normalize import normalize_image


def _profile(kind):
    return ImageCms.ImageCmsProfile(ImageCms.createProfile(kind)).tobytes()


def test_unprofiled_rgba_preserves_rgb_alpha_and_original_image():
    rgba = np.array([[[12, 99, 243, 0], [33, 44, 55, 128], [120, 70, 10, 255]]], dtype=np.uint8)
    original = Image.fromarray(rgba)
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), rgba)
    np.testing.assert_array_equal(np.asarray(original), rgba)
    assert diagnostics == {
        "source_mode": "RGBA",
        "orientation_applied": False,
        "icc_status": "absent",
        "color_space": "assumed_sRGB",
    }


def test_embedded_srgb_profile_preserves_transparency_and_literals():
    rgba = np.array([[[0, 0, 0, 0], [255, 0, 0, 128], [14, 15, 149, 255]]], dtype=np.uint8)
    original = Image.fromarray(rgba)
    original.info["icc_profile"] = _profile("sRGB")
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), rgba)
    assert diagnostics["icc_status"] == "converted"
    assert diagnostics["color_space"] == "sRGB"


def test_lab_tiff_uses_profile_conversion_instead_of_unmanaged_colour_conversion():
    original = Image.new("LAB", (3, 2), (128, 128, 128))
    profile = _profile("LAB")
    stream = io.BytesIO()
    original.save(stream, format="TIFF", icc_profile=profile)
    with Image.open(io.BytesIO(stream.getvalue())) as loaded:
        expected = ImageCms.profileToProfile(
            loaded,
            ImageCms.ImageCmsProfile(io.BytesIO(profile)),
            ImageCms.createProfile("sRGB"),
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            outputMode="RGB",
        )
        normalized, diagnostics = normalize_image(loaded)
    np.testing.assert_array_equal(np.asarray(normalized)[..., :3], np.asarray(expected))
    assert np.all(np.asarray(normalized)[..., 3] == 255)
    assert diagnostics["icc_status"] == "converted"


@pytest.mark.parametrize("profile", [b"not-an-icc-profile", "bad metadata"])
def test_invalid_profile_keeps_decodable_input_and_reports_the_fallback(profile):
    original = Image.new("RGBA", (4, 3), (20, 30, 40, 111))
    original.info["icc_profile"] = profile
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), np.asarray(original))
    assert diagnostics["icc_status"] == "ignored_invalid"
    assert diagnostics["icc_error"]


def test_exif_rotation_precedes_segmentation_and_preserves_source():
    original = Image.fromarray(np.arange(18, dtype=np.uint8).reshape(2, 3, 3))
    original.getexif()[274] = 6
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(
        np.asarray(normalized)[..., :3], np.rot90(np.asarray(original), -1)
    )
    assert normalized.size == (2, 3)
    assert original.size == (3, 2)
    assert original.getexif()[274] == 6
    assert diagnostics["orientation_applied"]


def test_palette_profile_keeps_partial_and_full_transparency():
    original = Image.new("P", (3, 1))
    original.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 9))
    original.putdata([0, 1, 2])
    original.info.update(transparency=bytes([0, 111, 255]), icc_profile=_profile("sRGB"))
    expected = np.asarray(original.convert("RGBA"))
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), expected)
    assert diagnostics["icc_status"] == "converted"


def test_rgb_profile_preserves_transparency_key():
    original = Image.new("RGB", (2, 1), (255, 0, 0))
    original.putpixel((1, 0), (0, 0, 255))
    original.info.update(transparency=(255, 0, 0), icc_profile=_profile("sRGB"))
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), np.asarray(original.convert("RGBA")))
    assert diagnostics["icc_status"] == "converted"


def test_gray_alpha_uses_gray_channel_for_profile_transform(monkeypatch):
    original = Image.new("LA", (2, 1), (128, 64))
    original.info["icc_profile"] = _profile("sRGB")

    def transform(colour, source, target, **kwargs):
        assert colour.mode == "L"
        assert colour.getpixel((0, 0)) == 128
        assert kwargs["outputMode"] == "RGB"
        return Image.new("RGB", colour.size, (146, 146, 146))

    monkeypatch.setattr(ImageCms, "profileToProfile", transform)
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), [[[146, 146, 146, 64]] * 2])
    assert diagnostics["icc_status"] == "converted"


def test_missing_colour_management_reports_fallback_without_breaking_decode(monkeypatch):
    original = Image.new("RGBA", (2, 2), (20, 30, 40, 111))
    original.info["icc_profile"] = _profile("sRGB")
    monkeypatch.delattr("PIL.ImageCms")
    monkeypatch.setitem(sys.modules, "PIL.ImageCms", None)
    normalized, diagnostics = normalize_image(original)
    np.testing.assert_array_equal(np.asarray(normalized), np.asarray(original))
    assert diagnostics["icc_status"] == "unavailable"
