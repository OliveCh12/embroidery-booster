"""Orient raster inputs and normalize embedded colour profiles before segmentation."""

from __future__ import annotations

import io

from PIL import Image, ImageOps


def normalize_image(image: Image.Image) -> tuple[Image.Image, dict]:
    orientation = image.getexif().get(274, 1)
    oriented = ImageOps.exif_transpose(image)
    diagnostics = {
        "source_mode": image.mode,
        "orientation_applied": orientation in (2, 3, 4, 5, 6, 7, 8),
        "icc_status": "absent",
        "color_space": "assumed_sRGB",
    }
    profile = oriented.info.get("icc_profile")
    if profile:
        try:
            from PIL import ImageCms
        except ImportError:
            diagnostics.update(icc_status="unavailable")
        else:
            try:
                source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
                target = ImageCms.createProfile("sRGB")
                # LAB's A band is chroma, never transparency. Palette and
                # transparency-key images need RGBA decoding to retain alpha.
                if oriented.mode == "LA":
                    colour, alpha = oriented.getchannel("L"), oriented.getchannel("A")
                elif oriented.mode in ("RGB", "L"):
                    colour = oriented
                    alpha = oriented.convert("RGBA").getchannel("A")
                elif oriented.mode in ("CMYK", "LAB"):
                    colour, alpha = oriented, None
                else:
                    rgba = oriented.convert("RGBA")
                    colour, alpha = rgba.convert("RGB"), rgba.getchannel("A")
                converted = ImageCms.profileToProfile(
                    colour,
                    source,
                    target,
                    renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                    outputMode="RGB",
                ).convert("RGBA")
                if alpha is not None:
                    converted.putalpha(alpha)
                diagnostics.update(icc_status="converted", color_space="sRGB")
                return converted, diagnostics
            except (OSError, TypeError, ValueError, ImageCms.PyCMSError) as exc:
                diagnostics.update(icc_status="ignored_invalid", icc_error=str(exc))
    try:
        return oriented.convert("RGBA"), diagnostics
    except (OSError, ValueError) as exc:
        raise ValueError(f"Raster colour mode {oriented.mode} needs a valid ICC profile.") from exc
