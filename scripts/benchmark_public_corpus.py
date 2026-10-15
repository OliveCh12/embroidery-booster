"""Procedural public artwork and independent source-intent measurements.

No fonts, downloaded logos, engine geometry or personal images are used. The
transparent reference is created before a background or JPEG encoding is added.
Its semantics are explicit fixture intent, never inferred from arbitrary images.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import runpy
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import resvg_py
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, binary_fill_holes, label, map_coordinates
from scipy.spatial import cKDTree
from skimage.color import rgb2lab

PIXELS_PER_MM = 8
PAINT_DISTANCE = 14.0


def render_svg(path, size=None, *, pixel_centres=False):
    root = ET.parse(path).getroot()
    if size is not None:
        root.set("width", str(size[0]) + "px")
        root.set("height", str(size[1]) + "px")
    if pixel_centres:
        box = [float(value) for value in root.attrib["viewBox"].split()]
        root.set("viewBox", f"{box[0] - 0.5} {box[1] - 0.5} {box[2]} {box[3]}")
    png = resvg_py.svg_to_bytes(
        svg_string=ET.tostring(root, encoding="unicode"), dpi=96, skip_system_fonts=True
    )
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def public_corpus(output: Path):
    """Generate 42 small, byte-reproducible cases with explicit source intent."""
    directory = output / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    reference_palettes = {}

    def add(name, path, reference=None, *, pixel_scale=PIXELS_PER_MM, **extra):
        case = {
            "name": name,
            "path": str(path.relative_to(output)),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width_mm": 80,
            "background": "auto",
            "cleanup": True,
            **extra,
        }
        if "expected_error" in case:
            case["expected_error_type"] = "ValueError"
        if reference is not None:
            reference_path = directory / (name + "-reference.png")
            Image.fromarray(reference).save(reference_path)
            ys, xs = np.nonzero(reference[..., 3] >= 128)
            bounds = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
            # Raster width includes the historical two tracing-padding pixels.
            # This keeps the source mm/pixel scale equal across file formats.
            if path.suffix != ".svg":
                case["width_mm"] = (bounds[2] - bounds[0] + 2) / pixel_scale
            case["oracle"] = {
                "path": str(reference_path.relative_to(output)),
                "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                "pixels_per_mm": pixel_scale,
                "bounds_px": bounds,
                "intent": "explicit_synthetic_foreground_and_paint",
                "palette": reference_palettes.get(id(reference), []),
            }
        cases.append(case)

    def svg(name, body):
        path = directory / (name + ".svg")
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
            'viewBox="0 0 80 70">' + body + "</svg>"
        )
        reference = render_svg(path, (80 * PIXELS_PER_MM, 70 * PIXELS_PER_MM))
        reference_palettes[id(reference)] = sorted(set(re.findall(r"#[0-9a-fA-F]{6}", body)))
        return path, reference

    def raster(name, reference, *, background="white", jpeg=None):
        image = Image.fromarray(reference)
        if background is not None:
            if isinstance(background, str):
                canvas = Image.new("RGBA", image.size, background)
            else:
                canvas = Image.fromarray(background).convert("RGBA")
            image = Image.alpha_composite(canvas, image).convert("RGB")
        path = directory / (name + (".jpg" if jpeg is not None else ".png"))
        image.save(path, **({"quality": jpeg, "subsampling": 2} if jpeg is not None else {}))
        add(name, path, reference)

    glyphs = {
        "j": "M29 12H38V47Q38 59 25 59Q14 59 14 48H23Q23 52 26 52Q29 52 29 47Z",
        "u": "M17 20H26V46Q26 52 32 52Q38 52 38 46V20H47V46Q47 61 32 61Q17 61 17 46Z",
        "n": "M16 58V20H25V24Q29 19 36 19Q49 19 49 33V58H40V34Q40 27 33 27Q25 27 25 35V58Z",
        "g": "M48 20V55Q48 67 34 67H22V59H34Q39 59 39 54V51Q35 55 29 55Q15 55 15 37Q15 19 30 19Q36 19 40 23V20ZM24 37Q24 47 31 47Q39 47 39 37Q39 27 31 27Q24 27 24 37Z",
        "l": "M25 10H34V49H47V58H25Z",
        "y": "M12 20H22L31 43L40 20H50L33 64H23L27 53Z",
    }
    for letter, path_data in glyphs.items():
        name = "glyph-" + letter
        source, reference = svg(name, f'<path fill="#171717" fill-rule="evenodd" d="{path_data}"/>')
        add(name + "-svg", source, reference)
        raster(name + "-png", reference)
        raster(name + "-jpeg75", reference, jpeg=75)
        if letter == "g":
            raster(name + "-jpeg35", reference, jpeg=35)
            raster(name + "-jpeg95", reference, jpeg=95)

    shapes = {
        "ring": '<circle cx="40" cy="35" r="22" fill="none" stroke="#171717" stroke-width="4"/>',
        "thin-curve": '<path d="M12 52C16 9 56 65 64 18" fill="none" stroke="#171717" stroke-width="1.2"/>',
        "column-widths": '<path fill="#171717" d="M7 12H70V16H7ZM7 27H70V34H7ZM7 45H70V59H7Z"/>',
        "mirrored-columns": '<path fill="#171717" d="M10 13H29V19H16V53H29V59H10Z"/><path fill="#171717" d="M70 13H51V19H64V53H51V59H70Z"/>',
        "flag": '<path fill="#012169" d="M0 0H80V70H0Z"/><path stroke="#ffffff" stroke-width="13" d="M0 0L80 70M0 70L80 0"/><path stroke="#c8102e" stroke-width="5" d="M0 0L80 70M0 70L80 0"/><path stroke="#ffffff" stroke-width="18" d="M40 0V70M0 35H80"/><path stroke="#c8102e" stroke-width="10" d="M40 0V70M0 35H80"/>',
    }
    for name, body in shapes.items():
        source, reference = svg(name, body)
        add(name + "-svg", source, reference)
        if name == "flag":
            raster(name + "-png", reference)

    source, badge = svg(
        "protected-white-badge",
        '<circle cx="40" cy="35" r="25" fill="#ffffff" stroke="#171717" stroke-width="1.4"/>'
        '<path fill="#e3202a" d="M18 27A23 23 0 0 1 62 27Q43 22 18 27Z"/>'
        '<path fill="#182c9b" d="M18 43A23 23 0 0 0 62 43Q43 49 18 43Z"/>'
        '<path fill="#171717" d="M25 31H28V39H25ZM32 31H42V34H35V36H42V39H32ZM47 31H55V34H50V39H47Z"/>',
    )
    add("protected-white-badge-svg", source, badge)
    raster("badge-gray", badge, background="#ededed")
    raster("badge-transparent", badge, background=None)
    y, x = np.indices(badge.shape[:2], dtype=float)
    unit = (x / x.max() + y / y.max()) / 2
    gradient = np.stack([225 - 55 * unit, 231 - 45 * unit, 238 - 30 * unit], axis=-1).astype(
        np.uint8
    )
    raster("badge-gradient", badge, background=gradient)
    noise = np.random.default_rng(661).normal(0, 2, (*unit.shape, 1))
    texture = np.clip(gradient.astype(float) + noise, 0, 255).astype(np.uint8)
    raster("badge-texture", badge, background=texture)

    _, accents = svg(
        "multi-accent-source",
        '<path fill="#171717" d="M8 25H72V45H8Z"/>'
        '<circle fill="#1e9c56" cx="21" cy="35" r="0.65"/>'
        '<circle fill="#aa2266" cx="59" cy="35" r="0.65"/>',
    )
    raster("multi-accent-png", accents, background=None)
    for quality in (35, 75, 95):
        raster("multi-accent-jpeg" + str(quality), accents, jpeg=quality)

    # Reuse the published, original fixture generator. Its separate reference()
    # supplies known flat-band intent before noise, shadows or JPEG compression.
    fixture = Path(__file__).resolve().parents[1] / "examples/quality/textured-five-paints.py"
    namespace = runpy.run_path(str(fixture))
    noisy, clean = namespace["generate"](), namespace["reference"]()
    reference_palettes[id(clean)] = [
        "#" + "".join(f"{v:02x}" for v in color)
        for color in np.unique(clean[..., :3].reshape(-1, 3), axis=0)
    ]
    for suffix, quality in (("png", None), ("jpeg75", 75)):
        path = directory / ("textured-five-paints." + ("png" if quality is None else "jpg"))
        image = Image.fromarray(noisy)
        if quality is not None:
            image = image.convert("RGB")
        image.save(path, **({"quality": quality, "subsampling": 2} if quality else {}))
        add(
            "textured-five-paints-" + suffix,
            path,
            clean,
            pixel_scale=(clean.shape[1] + 2) / 80,
            background="keep",
        )

    gradient_path = directory / "gradient-only.png"
    Image.fromarray(gradient).save(gradient_path)
    add(
        "gradient-only",
        gradient_path,
        np.dstack([gradient, np.full(unit.shape, 255, np.uint8)]),
        oracle_kind="continuous_paint",
        machine=False,
    )
    # The gradient is intentionally a full painted rectangle, not a removable
    # background. Only silhouette is scored: six threads cannot reproduce RGB.
    cases[-1]["oracle"]["silhouette_only"] = True

    for count in (4096, 4097):
        canvas = Image.new("RGBA", (260, 260))
        draw = ImageDraw.Draw(canvas)
        for index in range(count):
            col, row = index % 65, index // 65
            draw.rectangle((col * 4 + 1, row * 4 + 1, col * 4 + 2, row * 4 + 2), fill="#171717")
        source = directory / f"regions-{count}.png"
        canvas.save(source)
        add(
            f"regions-{count}",
            source,
            machine=False,
            background="keep",
            cleanup=False,
            expected_regions=count,
            **({"expected_error": "4096"} if count > 4096 else {}),
        )
    transparent = directory / "empty.png"
    Image.new("RGBA", (32, 32)).save(transparent)
    add("empty-transparent", transparent, expected_error="No shapes", machine=False)
    invalid = directory / "invalid.svg"
    invalid.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path')
    add("invalid-svg", invalid, expected_error="Invalid SVG", machine=False)
    assert len(cases) == 42
    manifest = output / "public-corpus.json"
    manifest.write_text(json.dumps(cases, indent=2, allow_nan=False))
    return manifest


def categorical(rgba, palette):
    """An incorrect paint never passes just because it is the nearest colour."""
    result = np.zeros(rgba.shape[:2], np.uint16)
    visible = rgba[..., 3] >= 128
    colors = np.asarray([[int(p[i : i + 2], 16) for i in (1, 3, 5)] for p in palette])
    tree = cKDTree(rgb2lab(colors[None].astype(float) / 255)[0])
    distances, indices = tree.query(rgb2lab(rgba[..., :3].astype(float) / 255)[visible])
    result[visible] = np.where(distances <= PAINT_DISTANCE, indices + 1, len(palette) + 1)
    return result


def source_scores(reference, actual, palette, *, silhouette_only=False, boundary_tolerance=1):
    """Spatial masks use a one-source-pixel edge tolerance, never bbox fitting."""
    reference_labels = categorical(reference, palette)
    actual_labels = categorical(actual, palette)
    target, produced = reference[..., 3] >= 128, actual[..., 3] >= 128

    def mask_score(expected, observed):
        expected_core = binary_erosion(expected, iterations=boundary_tolerance)
        observed_core = binary_erosion(observed, iterations=boundary_tolerance)
        intersection = int(np.count_nonzero(expected & observed))
        union = int(np.count_nonzero(expected | observed))
        components, count = label(expected)
        components_recalled = sum(
            bool(np.any(observed & (components == index))) for index in range(1, count + 1)
        )
        background_structure = np.ones((3, 3), bool)
        holes = binary_fill_holes(expected, structure=background_structure) & ~expected
        hole_labels, hole_count = label(holes, structure=background_structure)
        # Test each source counter in place; an equal-sized hole elsewhere cannot
        # compensate for a filled counter. One-pixel boundaries are not interiors.
        hole_cores = [
            binary_erosion(hole_labels == index, iterations=boundary_tolerance)
            for index in range(1, hole_count + 1)
        ]
        resolvable_holes = [core for core in hole_cores if core.any()]
        holes_preserved = sum(not np.any(observed & core) for core in resolvable_holes)
        return {
            "iou": intersection / union if union else 1.0,
            "missing_core_pixels": int(np.count_nonzero(expected_core & ~observed)),
            "extra_core_pixels": int(np.count_nonzero(observed_core & ~expected)),
            "source_components": int(count),
            "components_recalled": int(components_recalled),
            "source_holes": int(hole_count),
            "holes_with_resolvable_core": len(resolvable_holes),
            "holes_preserved": int(holes_preserved),
        }

    paint_scores = {}
    all_errors = []
    if not silhouette_only:
        reference_lab = rgb2lab(reference[..., :3].astype(float) / 255)
        actual_lab = rgb2lab(actual[..., :3].astype(float) / 255)
        distances = np.linalg.norm(reference_lab - actual_lab, axis=-1)
        for index, paint in enumerate(palette):
            mask = reference_labels == index + 1
            paint_scores[paint] = mask_score(mask, actual_labels == index + 1)
            errors = distances[binary_erosion(mask, iterations=boundary_tolerance) & produced]
            all_errors.extend(errors.tolist())
            paint_scores[paint]["colour_error_delta_e76"] = colour_error(errors)
    return {
        "scope": "Known synthetic source intent before encoding/background; no learned or candidate-derived semantic truth.",
        "colour_tolerance_delta_e76": PAINT_DISTANCE,
        "boundary_tolerance_source_pixels": boundary_tolerance,
        "silhouette": mask_score(target, produced),
        "paint": paint_scores,
        "colour_error_delta_e76": colour_error(np.asarray(all_errors)),
        "unmatched_colour_pixels": None
        if silhouette_only
        else int(np.count_nonzero(actual_labels == len(palette) + 1)),
    }


def colour_error(errors):
    """Missing source paint is measured by masks, not silently averaged as zero."""
    return {
        "matched_source_core_pixels": len(errors),
        "mean": float(np.mean(errors)) if len(errors) else None,
        "p95": float(np.percentile(errors, 95)) if len(errors) else None,
        "sum_squared": float(np.square(errors).sum()) if len(errors) else None,
    }


def source_oracle(
    reference_path, svg_path, geometry, capture, output, *, palette=None, silhouette_only=False
):
    """Project into the original, uncropped source grid without shape registration."""
    reference = np.asarray(Image.open(reference_path).convert("RGBA"))
    unique = np.unique(reference[reference[..., 3] >= 128, :3], axis=0)
    # Antialiased edge pixels are excluded from the palette, while masks retain
    # their positions. The generated SVG's literal paints provide fixture intent.
    if not palette:
        colors, counts = np.unique(
            reference[reference[..., 3] == 255, :3], axis=0, return_counts=True
        )
        colors = colors[counts >= 4]
        palette = ["#" + "".join(f"{v:02x}" for v in color) for color in colors]
    if len(palette) > 32:
        palette = ["#000000"]
        silhouette_only = True
    if not geometry:
        actual = render_svg(svg_path, (reference.shape[1], reference.shape[0]))
        alignment = "Native vector viewBox rendered on the full known source grid; no bbox fit."
    else:
        box = geometry["source_crop_box_px"]
        sample_height, sample_width = capture["sample_shape"]
        trim_x, trim_y = capture["trim_offset"]
        labels_shape = capture["labels_shape"]
        native = render_svg(svg_path, (labels_shape[1], labels_shape[0]), pixel_centres=True)
        yy, xx = np.indices(reference.shape[:2], dtype=float)
        coordinates = [
            ((yy + 0.5 - box[1]) * sample_height / (box[3] - box[1])) - 0.5 - trim_y + 1,
            ((xx + 0.5 - box[0]) * sample_width / (box[2] - box[0])) - 0.5 - trim_x + 1,
        ]
        actual = np.stack(
            [
                map_coordinates(native[..., c], coordinates, order=0, mode="constant", cval=0)
                for c in range(4)
            ],
            axis=-1,
        )
        alignment = "Original full source coordinates via observed crop, sample scale, pre-trim offset and one-pixel padding; integer pixel centres. No candidate-bbox fit."
    Image.fromarray(actual).save(output / "oracle-aligned.png")
    scores = source_scores(reference, actual, palette, silhouette_only=silhouette_only)
    scores["alignment"] = alignment
    scores["source_palette"] = palette
    scores["source_rgb_count"] = len(unique)
    return scores


def machine_source_oracle(direct, reference_path, oracle, output):
    """Measure top commands against a nominal 0.4 mm thread footprint.

    Fabric, support, locks and jumps are not simulated. Context points are never
    counted as new needles. Target scale and centre come from the known source.
    """
    from collections import Counter

    reference = np.asarray(Image.open(reference_path).convert("RGBA"))
    data = json.loads(Path(direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    codes = data["command_codes"]
    scale = oracle["pixels_per_mm"]
    bounds = oracle["bounds_px"]
    centre = np.asarray([(bounds[0] + bounds[2] - 1) / 2, (bounds[1] + bounds[3] - 1) / 2])
    supersampling = 4
    canvas = Image.new(
        "RGBA", (reference.shape[1] * supersampling, reference.shape[0] * supersampling)
    )
    draw = ImageDraw.Draw(canvas)
    counts = Counter()
    per_colour = Counter()
    block_peaks = []
    for run in data["top_layer_runs"]:
        local = Counter()
        for index in range(run["start"] + 1, run["end"]):
            x, y, command = commands[index]
            if (int(command) & codes["command_mask"]) != codes["stitch"]:
                continue
            needle = (int(x), int(y))
            local[needle] += 1
            counts[needle] += 1
            per_colour[(*needle, run["color_index"])] += 1
            a, b = (commands[index - 1 : index + 1, :2] / 10 * scale + centre) * supersampling
            draw.line(
                [tuple(a), tuple(b)],
                fill=data["threads"][run["color_index"]],
                width=max(1, round(0.4 * scale * supersampling)),
            )
        block_peaks.append(max(local.values(), default=0))
    canvas = canvas.resize((reference.shape[1], reference.shape[0]), Image.Resampling.BOX)
    actual = np.asarray(canvas)
    canvas.save(output / "oracle-machine-top.png")
    scores = source_scores(
        reference,
        actual,
        oracle["palette"],
        silhouette_only=oracle.get("silhouette_only", False),
        boundary_tolerance=max(1, round(0.4 * scale)),
    )
    scores.update(
        nominal_thread_width_mm=0.4,
        alignment="Known source bounds centre and native mm/pixel; no scaling or shape registration from emitted stitches.",
        repeated_needles={
            "top_cycles": sum(counts.values()),
            "distinct_positions": len(counts),
            "repeats_same_position": sum(value - 1 for value in counts.values()),
            "repeats_same_position_and_colour": sum(value - 1 for value in per_colour.values()),
            "peak_all_top": max(counts.values(), default=0),
            "peak_per_colour": max(per_colour.values(), default=0),
            "peak_within_one_block": max(block_peaks, default=0),
            "positions_with_three_or_more_cycles": sum(value >= 3 for value in counts.values()),
            "interpretation": "Exact 0.1 mm repeated penetrations are observations, not automatic evidence of bunching.",
        },
    )
    return scores
