import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import box
from svgelements import Matrix

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.image_processor import rasterize_svg
from embroidery_rungs.stitching.coverage import audit_coverage
from embroidery_rungs.stitching.planner import build_stitch_plan
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


def incomplete_plan():
    target = np.zeros((500, 720), dtype=bool)
    target[120:480, 120:600] = True
    target[240:300, 180:240] = False
    params = StitchParams()
    elements = [
        {"type": "fill", "polygon": box(10, 10, 30, 40).difference(box(15, 20, 20, 25))},
        {"type": "fill", "polygon": box(31.3, 10, 50, 40)},
    ]
    return (
        build_stitch_plan(elements, params),
        elements,
        target,
        Matrix.scale(12 / UNITS_PER_MM),
        params,
    )


def test_actual_stitch_audit_repairs_submillimetre_seam_without_filling_source_hole():
    plan, elements, mask, transform, params = incomplete_plan()
    before, _ = measure_stitches(plan.commands, plan.origin_mm, mask, 12, (0, 0))
    repaired = audit_coverage(plan, elements, mask, transform, params)
    after, _ = measure_stitches(repaired.commands, repaired.origin_mm, mask, 12, (0, 0))
    assert before["largest_gap_mm2"] > 5
    assert after["structural_coverage"] >= 0.999
    assert after["largest_gap_mm2"] < 0.05
    assert repaired.stats["coverage_repairs"] > 0
    assert not intersects(linestrings(sewn_segments(repaired)), box(15.3, 20.3, 19.7, 24.7)).any()


@pytest.mark.parametrize("settings", [{"auto_select": False}, {"fill_gaps": False}])
def test_manual_settings_disable_coverage_repairs(settings):
    plan, elements, mask, transform, params = incomplete_plan()
    repaired = audit_coverage(plan, elements, mask, transform, replace(params, **settings))
    assert repaired.commands == plan.commands
    assert repaired.stats["coverage_repairs"] == 0
    assert repaired.stats["largest_gap_mm2"] > 5
    assert any("coverage leaves" in warning for warning in repaired.warnings)


def test_optional_repair_failure_preserves_valid_plan_and_reports_reason(monkeypatch):
    plan, elements, mask, transform, params = incomplete_plan()

    def budget_error(*args):
        raise ValueError("Stitch budget exceeded")

    monkeypatch.setattr("embroidery_rungs.stitching.coverage.build_stitch_plan", budget_error)
    repaired = audit_coverage(plan, elements, mask, transform, params)
    assert repaired.commands == plan.commands
    assert any("budget exceeded" in warning for warning in repaired.warnings)
