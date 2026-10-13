from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import Point, Polygon, box

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


@pytest.mark.parametrize("width", [7.8, 9, 20])
def test_strict_satin_divides_broad_columns_without_raising_the_float_limit(tmp_path, width):
    svg = document(tmp_path, f'<rect x="5" y="5" width="50" height="{width}"/>')
    plan, _ = digitize(
        svg, StitchParams(stitch_type="satin", auto_adjust=False, max_satin_width_mm=7.5)
    )
    assert {d["method"] for d in plan.decisions} == {"satin"}
    assert plan.decisions[0]["split_satin_columns"] >= 2
    assert plan.decisions[0]["safe_satin_width_mm"] == plan.params.max_satin_width_mm == 7.5
    assert plan.stats["max_stitch_mm"] <= 7.5
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.stats["crowded_satin_penetrations"] == plan.stats["unsafe_connections"] == 0


@pytest.mark.parametrize(
    "shape",
    [
        '<path d="M10 10H40V14H14V40H10Z"/>',
        '<path d="M10 10H50V14H32V45H28V14H10Z"/>',
    ],
    ids=["corner", "branch"],
)
def test_incomplete_corners_and_branches_keep_the_machine_gate_and_explain_failure(tmp_path, shape):
    svg = document(tmp_path, shape)
    automatic, _ = digitize(svg, StitchParams())
    assert {d["method"] for d in automatic.decisions} == {"fill"}
    assert automatic.stats["structural_coverage"] >= 0.999
    assert automatic.stats["unsafe_connections"] == automatic.stats["short_stitches"] == 0
    with pytest.raises(
        ValueError, match="Satin requested.*uncovered areas or crowded penetrations"
    ):
        digitize(svg, StitchParams(stitch_type="satin"))


@pytest.mark.parametrize("choice", ["auto", "satin"])
def test_broad_ring_satin_preserves_the_counter(tmp_path, choice):
    svg = document(
        tmp_path,
        '<circle cx="40" cy="35" r="20" fill="none" stroke="black" stroke-width="8"/>',
    )
    plan, _ = digitize(
        svg, StitchParams.for_fabric(machine="brother-skitch-pp1", stitch_type=choice)
    )
    assert {d["method"] for d in plan.decisions} == {"satin"}
    assert plan.decisions[0]["split_satin_columns"] > 0
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.stats["max_stitch_mm"] <= 7
    assert plan.stats["unsafe_connections"] == plan.stats["crowded_satin_penetrations"] == 0
    commands = np.asarray(plan.commands)
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + plan.origin_mm
    assert not intersects(linestrings(segments), Point(40, 35).buffer(15.6)).any()


def test_automatic_satin_does_not_divide_compact_bodies(tmp_path):
    plan, _ = digitize(
        document(tmp_path, '<rect x="5" y="5" width="30" height="30"/>'), StitchParams()
    )
    assert {d["method"] for d in plan.decisions} == {"fill"}
    assert plan.decisions[0]["split_satin_columns"] == 0


def test_forced_micro_detail_explains_machine_resolution(tmp_path):
    svg = document(tmp_path, '<rect x="5" y="5" width="2" height="0.2"/>')
    with pytest.raises(ValueError, match="minimum sewable satin width"):
        digitize(svg, StitchParams(stitch_type="satin"))


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
        document(tmp_path, '<rect x="5" y="5" width="40" height="20"/>' + detail),
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
