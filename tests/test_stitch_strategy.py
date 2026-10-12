from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from embroidery_rungs.stitching.consistency import RegionCandidate, _color_policy
from embroidery_rungs.stitching.digitizer import digitize
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.regions import RegionFrame
from embroidery_rungs.svg_manager import load_svg_paths


def document(tmp_path, content):
    source = tmp_path / "strategy.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
        f'viewBox="0 0 80 70">{content}</svg>'
    )
    return load_svg_paths(source)[0]


@pytest.mark.parametrize("choice", ["auto", "satin"])
def test_safe_narrow_logo_retains_uniform_satin(choice):
    svg, _ = load_svg_paths(Path(__file__).resolve().parents[1] / "examples/quality/straight.svg")
    plan, _ = digitize(svg, StitchParams(stitch_type=choice))
    assert {d["method"] for d in plan.decisions} == {"satin"}
    assert plan.stats["max_stitch_mm"] <= plan.params.max_stitch_mm
    assert plan.stats["short_stitches"] == plan.stats["crowded_satin_penetrations"] == 0
    assert plan.stats["structural_coverage"] >= 0.999


def test_requested_fill_is_uniform_and_never_computes_mat(tmp_path, monkeypatch):
    def unwanted_mat(*args, **kwargs):
        raise AssertionError("Explicit fill does not need a medial axis")

    monkeypatch.setattr("embroidery_rungs.stitching.consistency.compute_medial_axis", unwanted_mat)
    svg = document(
        tmp_path,
        '<rect x="5" y="5" width="35" height="3"/>'
        '<path fill-rule="evenodd" d="M5 20H50V60H5Z M20 30H30V45H20Z"/>',
    )
    plan, _ = digitize(svg, StitchParams(stitch_type="fill"))
    assert {d["method"] for d in plan.decisions} == {"fill"}
    assert all(not d["mat_evaluated"] for d in plan.decisions)
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.analysis["requested_stitch_type"] == "fill"
    assert plan.analysis["strategy_policy"] == "explicit_uniform"


@pytest.mark.parametrize("width", [9, 20])
def test_strict_satin_rejects_unsafe_float_without_silent_fill(tmp_path, width):
    svg = document(tmp_path, f'<rect x="5" y="5" width="50" height="{width}"/>')
    with pytest.raises(ValueError, match="Satin requested.*safe.*Use automatic or fill"):
        digitize(svg, StitchParams(stitch_type="satin", auto_adjust=False, max_satin_width_mm=12))


def test_explicit_running_preserves_contours_and_reports_solid_coverage_honestly(tmp_path):
    svg = document(tmp_path, '<path fill-rule="evenodd" d="M5 5H45V35H5Z M15 12H30V25H15Z"/>')
    plan, _ = digitize(svg, StitchParams(stitch_type="running"))
    assert {d["method"] for d in plan.decisions} == {"running"}
    assert {b.kind for b in plan.blocks if b.kind in ("satin", "fill", "running")} == {"running"}
    assert plan.stats["structural_coverage"] < 0.5
    assert plan.analysis["quality_status"] == "needs_review"
    assert any(
        "contours/centerlines rather than solid fill" in warning for warning in plan.warnings
    )
    assert plan.stats["short_stitches"] == 0


def test_auto_fill_coherence_preserves_columns_counters_and_small_details():
    frame = RegionFrame(np.eye(2), np.zeros(2))

    def member(shape, method, width):
        return RegionCandidate(
            SimpleNamespace(frame=frame),
            [{"type": method}],
            {"method": method, "width_mm": width},
            [shape],
            StitchParams(),
        )

    groups = {
        0: [member(box(0, 0, 20, 20), "fill", 20)],
        1: [member(box(30, 0, 33, 2), "satin", 2)],
        2: [member(box(0, 30, 20, 32), "satin", 2)],
        3: [member(box(40, 0, 41, 2), "satin", 1)],
        4: [
            member(
                Polygon(box(30, 30, 35, 35).exterior, [box(31, 31, 34, 34).exterior]), "satin", 3
            )
        ],
    }
    policies, angle, converted = _color_policy(groups, StitchParams())
    assert policies == {0: "fill", 1: "fill", 2: "satin", 3: "satin", 4: "satin"}
    assert converted == {1}
    assert angle is not None
    assert _color_policy(groups, StitchParams(stitch_type="satin"))[2] == set()


def test_invalid_stitch_strategy_is_rejected():
    with pytest.raises(ValueError, match="stitch_type"):
        StitchParams(stitch_type="random").validate()


def test_substantive_color_fill_keeps_small_detail_geometry_angle(tmp_path):
    detail = '<circle cx="55" cy="30" r="0.6"/>'
    isolated, _ = digitize(document(tmp_path, detail), StitchParams())
    with_body, _ = digitize(
        document(tmp_path, '<rect x="5" y="5" width="40" height="10"/>' + detail),
        StitchParams(),
    )
    small = next(d for d in with_body.decisions if d["area_mm2"] < 4)
    large = next(d for d in with_body.decisions if d["area_mm2"] >= 4)
    assert large["method"] == small["method"] == "fill"
    assert large["strategy_scope"] == "color"
    assert small["strategy_scope"] == "region"
    assert small["canonical_fill_angle_deg"] == isolated.decisions[0]["canonical_fill_angle_deg"]
    assert small["fill_angle_deg"] == isolated.decisions[0]["fill_angle_deg"]
    assert small["canonical_fill_angle_deg"] != large["canonical_fill_angle_deg"]


def test_strict_satin_rechecks_the_final_color_plan(monkeypatch):
    from embroidery_rungs.stitching import digitizer

    measure = digitizer.measure_plan

    def final_coverage_loss(*args, **kwargs):
        metrics, image = measure(*args, **kwargs)
        metrics["structural_coverage"] = 0.99
        return metrics, image

    monkeypatch.setattr(digitizer, "measure_plan", final_coverage_loss)
    svg, _ = load_svg_paths(Path(__file__).resolve().parents[1] / "examples/quality/straight.svg")
    with pytest.raises(ValueError, match="Satin requested.*final machine plan"):
        digitizer.digitize(svg, StitchParams(stitch_type="satin"))
