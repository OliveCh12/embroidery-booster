import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from PIL import Image, ImageDraw
from shapely import intersects, linestrings
from shapely.geometry import box

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.colors import separate_colors
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.stitching.planner import StitchBlock, StitchPlan
from embroidery_rungs.stitching.quality import measure_plan, measure_stitches
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

SOURCE = Path(__file__).resolve().parents[1] / "examples/quality/multicolor.svg"


def data_for(result):
    return json.loads(Path(result.direct.plan_path).read_text())


def exported_top(data, color):
    commands = []
    for run in data["top_layer_runs"]:
        if run["color_index"] == color:
            points = data["commands"][run["start"] : run["end"]]
            commands.append([*points[0][:2], pe.JUMP])
            commands.extend(points)
    return commands


def test_visible_color_layers_export_exact_palette_and_commands(tmp_path):
    result = generate(SOURCE, tmp_path, method="direct")
    data = data_for(result)
    assert set(result.direct.threads) == {"#1267c9", "#e83546", "#f3bb27"}
    assert data["coverage_basis"] == "quantized_top_layer"
    assert result.direct.stats["color_changes"] == 2
    commands = np.asarray(data["commands"])
    planned = commands[commands[:, 2] == pe.STITCH, :2]
    for filename in (result.direct.pes_path, result.direct.dst_path):
        pattern = pe.read(filename)
        actual = np.asarray(pattern.stitches)
        assert np.array_equal(
            actual[(actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2], planned
        )
        assert pattern.count_stitch_commands(pe.COLOR_CHANGE) == 2
        assert [thread.hex_color().lower() for thread in pattern.threadlist] == data["threads"]
        assert pattern.count_stitch_commands(pe.END) == 1
    # Colour changes happen after a trim, never through a stitched connector.
    for i in np.flatnonzero(commands[:, 2] == pe.COLOR_CHANGE):
        assert commands[i - 1, 2] == pe.TRIM
        assert commands[i + 1, 2] == pe.JUMP
    lengths = np.linalg.norm(np.diff(commands[:, :2], axis=0), axis=1) / 10
    assert lengths[commands[1:, 2] == pe.JUMP].max() <= 12.1
    document, _ = load_svg_paths(result.original_path)
    rgba, transform = rasterize_rgba(document, 305)
    labels, colors, _ = separate_colors(rgba)
    for index, color in enumerate(data["threads"]):
        metrics, _ = measure_stitches(
            exported_top(data, index),
            data["origin_mm"],
            labels == colors.index(color) + 1,
            transform.a * UNITS_PER_MM,
            [transform.e, transform.f],
        )
        assert metrics["structural_coverage"] >= 0.999
        assert metrics["largest_gap_mm2"] == 0
    # One method per component, no fill patches or mixed top layer.
    methods = {}
    for run in data["top_layer_runs"]:
        methods.setdefault((run["color_index"], run["region"]), set()).add(run["kind"])
    assert all(len(types) == 1 for types in methods.values())
    assert result.direct.stats["coverage_repairs"] == 0
    # Void in the blue counter survives even when other colours are planned.
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = (
        np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
    )
    assert not intersects(linestrings(segments), box(16, 16, 38, 36)).any()


@pytest.mark.parametrize("transparent", [False, True])
def test_color_bitmap_retains_red_blue_and_counter(tmp_path, transparent):
    image = Image.new("RGBA", (160, 100), (255, 255, 255, 0 if transparent else 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 70, 90), fill="#e83546")
    draw.rectangle((90, 10, 150, 90), fill="#1267c9")
    draw.rectangle((25, 25, 55, 75), fill=(255, 255, 255, 0 if transparent else 255))
    path = tmp_path / "logo.png"
    image.save(path)
    result = generate(path, tmp_path / "out", GenerationParams(design_width_mm=60), method="direct")
    assert set(result.direct.threads) == {"#1267c9", "#e83546"}
    assert result.direct.stats["structural_coverage"] >= 0.999
    assert data_for(result)["layers"][0]["largest_gap_mm2"] == 0


def test_opaque_svg_white_paint_is_an_intentional_thread(tmp_path):
    source = tmp_path / "white.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="20mm" viewBox="0 0 30 20"><rect width="30" height="20" fill="#1267c9"/><rect x="5" y="5" width="20" height="10" fill="white"/></svg>'
    )
    result = generate(source, tmp_path / "out", method="direct")
    assert set(result.direct.threads) == {"#ffffff", "#1267c9"}
    assert result.direct.stats["color_changes"] == 1


def test_palette_is_bounded_deterministic_and_antialias_does_not_add_threads():
    rgba = np.full((40, 256, 4), 255, dtype=np.uint8)
    rgba[..., 0] = np.arange(256)
    rgba[..., 2] = 255 - np.arange(256)
    a, colors, reduced = separate_colors(rgba, max_colors=4)
    b, again, _ = separate_colors(rgba, max_colors=4)
    assert reduced and 1 < len(colors) <= 4
    assert np.array_equal(a, b) and colors == again
    assert np.all(a > 0)
    rgba = np.zeros((100, 100, 4), dtype=np.uint8)
    rgba[:50] = [230, 10, 20, 255]
    rgba[50:] = [10, 20, 230, 255]
    rgba[49] = [120, 15, 125, 255]
    _, colors, reduced = separate_colors(rgba)
    # Rare edge blends must not become a third thread.
    assert len(colors) == 2


@pytest.mark.parametrize("orientation", ["flip_x", "flip_y", "rotate", "transpose"])
def test_thin_periodic_flat_colors_survive_every_raster_orientation(orientation):
    rgba = np.empty((600, 600, 4), dtype=np.uint8)
    rgba[..., :3] = np.array([[230, 20, 20], [20, 220, 20], [20, 20, 230]])[np.arange(600) % 3]
    rgba[..., 3] = 255
    orient = {
        "flip_x": lambda array: array[:, ::-1],
        "flip_y": lambda array: array[::-1],
        "rotate": lambda array: np.rot90(array),
        "transpose": lambda array: np.swapaxes(array, 0, 1),
    }[orientation]
    labels, colors, reduced = separate_colors(rgba, max_colors=6)
    changed, palette, changed_reduced = separate_colors(orient(rgba), max_colors=6)
    assert set(colors) == {"#e61414", "#14dc14", "#1414e6"}
    assert palette == colors
    assert not reduced and not changed_reduced
    assert np.array_equal(changed, orient(labels))


@pytest.mark.parametrize("orientation", ["flip_x", "rotate", "transpose"])
def test_quantized_gradient_palette_is_invariant_to_pixel_enumeration(orientation):
    rgba = np.empty((512, 512, 4), dtype=np.uint8)
    x = np.linspace(20, 230, 512).astype(np.int16)
    rgb = np.stack(np.broadcast_arrays(x[None, :], x[:, None], 255 - x[None, :]), axis=2)
    noise = np.random.default_rng(42).integers(-12, 13, size=rgb.shape)
    rgba[..., :3] = np.clip(rgb + noise, 0, 255)
    rgba[..., 3] = 255
    orient = {
        "flip_x": lambda array: array[:, ::-1],
        "rotate": lambda array: np.rot90(array),
        "transpose": lambda array: np.swapaxes(array, 0, 1),
    }[orientation]
    labels, colors, reduced = separate_colors(rgba, max_colors=6)
    changed, palette, changed_reduced = separate_colors(orient(rgba), max_colors=6)
    assert 1 < len(colors) <= 6
    assert reduced and changed_reduced
    assert palette == colors
    assert np.array_equal(changed, orient(labels))


def test_top_layer_audit_excludes_underlay_and_unsewn_jump():
    target = np.ones((100, 100), dtype=bool)
    blocks = [StitchBlock("underlay", np.array([[0, 5], [10, 5]]), 0)]
    plan = StitchPlan([[0, 50, pe.STITCH], [100, 50, pe.STITCH]], blocks, (0, 0), {})
    metrics, _ = measure_plan(plan, target, 10, (0, 0))
    assert metrics["coverage"] == 0
    assert metrics["structural_coverage"] == 0


def test_global_color_budget_and_palette_settings_are_validated(tmp_path):
    with pytest.raises(ValueError, match="budget"):
        generate(SOURCE, tmp_path, method="direct", stitch_params=StitchParams(max_stitches=100))
    assert not (tmp_path / "multicolor_direct.pes").exists()
    for value in (0, 33, True, 2.5):
        with pytest.raises(ValueError, match="max_colors"):
            StitchParams(max_colors=value).validate()


def test_similar_solid_paints_and_small_accents_remain_distinct():
    rgba = np.full((60, 90, 4), 255, dtype=np.uint8)
    rgba[:, :45, :3] = [253, 0, 0]
    rgba[:, 45:, :3] = [255, 0, 0]
    rgba[20:24, 20:24, :3] = [0, 230, 0]
    _, colors, _ = separate_colors(rgba)
    assert set(colors) == {"#fd0000", "#ff0000", "#00e600"}


@pytest.mark.parametrize("accent", [[255, 0, 0], [0, 128, 127]])
def test_isolated_single_pixel_accents_remain_in_a_flat_paint_palette(accent):
    rgba = np.zeros((60, 100, 4), dtype=np.uint8)
    rgba[10:25, 10:90] = [0, 0, 255, 255]
    rgba[35:50, 10:90] = [0, 255, 0, 255]
    rgba[2, 2] = [*accent, 255]
    labels, colors, reduced = separate_colors(rgba)
    expected = "#" + "".join(f"{channel:02x}" for channel in accent)
    assert set(colors) == {"#0000ff", "#00ff00", expected}
    assert colors[labels[2, 2] - 1] == expected
    assert not reduced
    changed, palette, _ = separate_colors(np.rot90(rgba))
    assert palette == colors
    assert np.array_equal(changed, np.rot90(labels))


def test_monochrome_override_is_explicit_and_uses_chosen_thread(tmp_path):
    result = generate(
        SOURCE,
        tmp_path,
        method="direct",
        stitch_params=StitchParams(preserve_colors=False, thread_color="#20aa50"),
    )
    assert result.direct.threads == ["#20aa50"]
    assert result.direct.stats["color_changes"] == 0


def test_color_web_upload_exposes_ordered_palette_and_machine_downloads(tmp_path):
    import io

    from embroidery_rungs.web.app import create_app

    client = create_app({"TESTING": True, "OUTPUT_ROOT": str(tmp_path)}).test_client()
    response = client.post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SOURCE.read_bytes()), "logo.svg"),
            "method": "direct",
            "max_colors": "3",
        },
    )
    assert response.status_code == 200
    direct = response.get_json()["direct"]
    assert set(direct["threads"]) == {"#1267c9", "#e83546", "#f3bb27"}
    assert direct["stats"]["color_changes"] == 2
    assert client.get(direct["files"]["pes"]).data.startswith(b"#PES0060")
    bad = client.post(
        "/api/convert",
        data={
            "file": (io.BytesIO(SOURCE.read_bytes()), "logo.svg"),
            "method": "direct",
            "max_colors": "33",
        },
    )
    assert bad.status_code == 400


@pytest.mark.parametrize("name", ["flower", "margot", "arabian", "nike", "satin-demo"])
def test_complex_logos_have_top_layer_coverage_without_repair_patches(tmp_path, name):
    source = SOURCE.parents[1] / f"{name}.svg"
    result = generate(
        source, tmp_path, GenerationParams(design_width_mm=80, fit_to_hoop=True), method="direct"
    )
    assert result.direct.stats["structural_coverage"] >= 0.999
    assert result.direct.stats["largest_gap_mm2"] <= 0.05
    assert result.direct.stats["gap_fill_regions"] == 0
    assert result.direct.stats["unsafe_connections"] == 0
    assert result.direct.stats["crowded_satin_penetrations"] == 0


def test_pale_bitmap_foreground_is_not_erased_as_background(tmp_path):
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 80, 80), fill="#f5f5f5")
    source = tmp_path / "pale.png"
    image.save(source)
    result = generate(source, tmp_path / "out", method="direct")
    assert result.direct.threads == ["#f5f5f5"]
    assert result.direct.stats["structural_coverage"] == 1


def test_gradient_bitmap_uses_bounded_threads_and_valid_color_changes(tmp_path):
    rgb = np.empty((80, 120, 3), dtype=np.uint8)
    rgb[..., 0] = np.linspace(20, 230, 120).astype(np.uint8)
    rgb[..., 1] = 60
    rgb[..., 2] = np.linspace(230, 20, 120).astype(np.uint8)
    source = tmp_path / "gradient.png"
    Image.fromarray(rgb).save(source)
    result = generate(
        source,
        tmp_path / "out",
        GenerationParams(design_width_mm=40),
        method="direct",
        stitch_params=StitchParams(max_colors=4),
    )
    assert 1 < len(result.direct.threads) <= 4
    assert result.direct.stats["color_changes"] == len(result.direct.threads) - 1
    assert all(layer["structural_coverage"] >= 0.999 for layer in data_for(result)["layers"])
    assert (
        pe.read(result.direct.pes_path).count_stitch_commands(pe.COLOR_CHANGE)
        == len(result.direct.threads) - 1
    )
