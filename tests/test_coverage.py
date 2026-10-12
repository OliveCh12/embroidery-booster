import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import box

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.image_processor import rasterize_svg
from embroidery_rungs.stitching.quality import measure_stitches
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def source_metrics(result):
    document, _ = load_svg_paths(result.original_path)
    mask, transform = rasterize_svg(document, dpi=305)
    data = json.loads(Path(result.direct.plan_path).read_text())
    scale = UNITS_PER_MM * transform.a
    return measure_stitches(
        data["commands"], data["origin_mm"], mask, scale, [transform.e, transform.f]
    )


def sewn_segments(plan):
    commands = np.asarray(plan.commands)
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    return np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + plan.origin_mm


@pytest.mark.parametrize(
    "name", ["thin", "tight-curve", "fine-ring", "fine-junction", "small-counter", "small-islands"]
)
def test_small_features_remain_covered_and_machine_safe(tmp_path, name):
    result = generate(EXAMPLES / "quality" / f"{name}.svg", tmp_path, method="direct")
    metrics, _ = source_metrics(result)
    assert metrics["structural_coverage"] >= (0.995 if name == "small-islands" else 0.999)
    assert metrics["largest_gap_mm2"] <= 0.05
    assert metrics["short_stitches"] == 0
    assert metrics["max_stitch_mm"] <= 8
    assert not any("Inkscape" in warning for warning in result.warnings)
    if name == "small-counter":
        data = json.loads(Path(result.direct.plan_path).read_text())
        commands = np.asarray(data["commands"])
        sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
        segments = (
            np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
        )
        assert not intersects(linestrings(segments), box(39.85, 34.65, 40.15, 35.35)).any()


@pytest.mark.parametrize("name", ["arabian", "margot", "satin-demo"])
def test_logo_coverage_at_practical_machine_size(tmp_path, name):
    result = generate(
        EXAMPLES / f"{name}.svg",
        tmp_path,
        GenerationParams(design_width_mm=80, fit_to_hoop=True),
        method="direct",
    )
    metrics, _ = source_metrics(result)
    assert metrics["structural_coverage"] >= 0.999
    assert metrics["largest_gap_mm2"] <= 0.1


def partial_rails(*args, **kwargs):
    element = {
        "type": "satin",
        "rail_a": [[10, 10], [20, 10], [30, 10]],
        "rail_b": [[10, 30], [20, 30], [30, 30]],
    }
    return [], [], [element]


@pytest.mark.parametrize("gap_fill", [False, True])
def test_incomplete_mat_rails_trigger_whole_region_fill_without_patches(
    tmp_path, monkeypatch, gap_fill
):
    monkeypatch.setattr("embroidery_rungs.stitching.consistency.generate_rungs", partial_rails)
    result = generate(
        EXAMPLES / "quality/holes.svg",
        tmp_path,
        method="direct",
        stitch_params=StitchParams(fill_gaps=gap_fill),
    )
    assert {d["method"] for d in result.direct.decisions} == {"fill"}
    assert result.direct.stats["structural_coverage"] >= 0.999
    assert result.direct.stats["largest_gap_mm2"] == 0
    assert result.direct.stats["gap_fill_regions"] == 0
    assert result.direct.stats["satin_regions"] == 0
    data = json.loads(Path(result.direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = (
        np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
    )
    assert not intersects(linestrings(segments), box(21, 21, 34, 39)).any()


def test_manual_incomplete_rails_report_missing_source_without_repair(tmp_path, monkeypatch):
    monkeypatch.setattr("embroidery_rungs.pipeline.generate_rungs", partial_rails)
    result = generate(
        EXAMPLES / "quality/straight.svg",
        tmp_path,
        method="direct",
        stitch_params=StitchParams(auto_select=False, fill_gaps=False),
    )
    assert result.direct.decisions == []
    assert result.direct.stats["coverage_repairs"] == 0
    assert result.direct.stats["structural_coverage"] < 0.5
    assert any("coverage leaves gaps" in warning for warning in result.direct.warnings)
