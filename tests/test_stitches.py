import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import covered_by, linestrings
from shapely.geometry import LineString, Polygon

from embroidery_rungs import StitchParams, generate
from embroidery_rungs.stitching.paths import fill_paths, resample_running, satin_points
from embroidery_rungs.stitching.planner import build_stitch_plan
from embroidery_rungs.stitching.regions import RegionFrame
from embroidery_rungs.stitching.selection import _split_columns

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def column(length=30.0, width=4.0):
    x = np.linspace(0, length, 21)
    return {
        "type": "satin",
        "rail_a": np.column_stack([x, np.full(len(x), -width / 2)]),
        "rail_b": np.column_stack([x, np.full(len(x), width / 2)]),
    }


def sew_segments(plan):
    commands = np.asarray(plan.commands)
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    return np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + plan.origin_mm


def test_rounded_locks_stay_inside_a_mirrored_thin_stepped_boundary():
    # Reduced from the eagle's fine colour fringe. The top path is legal, but
    # re-rounding its end lock previously crossed the allowed boundary.
    polygon = Polygon(
        [
            (7.33, 0.29),
            (6.16, 0.29),
            (6.08, 0.46),
            (4.58, 0.46),
            (4.50, 0.62),
            (1.33, 0.71),
            (3.75, 0.79),
        ]
    )
    frame = RegionFrame(np.diag([1.0, -1.0]), np.array([35.726557377, 16.322622951]))
    allowance = polygon.buffer(0.010703613 + 0.08)
    plan = build_stitch_plan(
        [
            {
                "type": "fill",
                "polygon": polygon,
                "compensation": 0.010703613,
                "fill_angle_deg": 15,
                "finish_inset": 0,
                "underlay": False,
                "frame": frame,
            }
        ],
        StitchParams(),
        origin_mm=(39.848852459, 35.976393443),
    )
    assert plan.stats["omitted_regions"] == 0
    assert plan.stats["short_stitches"] == 0
    assert any(b.kind == "lock" for b in plan.blocks)
    assert covered_by(
        linestrings(sew_segments(plan)), frame.geometry_to_world(allowance).buffer(0.08)
    ).all()


def test_satin_density_is_physical_and_compensation_is_per_side():
    e = column()
    params = StitchParams(underlay=False, pull_compensation_mm=0)
    points = satin_points(e["rail_a"], e["rail_b"], params)
    assert np.allclose(np.abs(points[:, 1]), 2)
    assert len(points) == 152
    assert np.diff(points[:-1:2, 0]).max() <= 0.401
    compensated = satin_points(e["rail_a"], e["rail_b"], replace(params, pull_compensation_mm=0.2))
    assert np.allclose(np.abs(compensated[:, 1]), 2.2)
    coarse = satin_points(e["rail_a"], e["rail_b"], replace(params, satin_spacing_mm=0.8))
    assert len(points) > len(coarse) * 1.8


def test_curved_satin_keeps_outer_coverage_and_avoids_inner_hole():
    angle = np.linspace(0, np.pi / 2, 101)
    unit = np.column_stack([np.cos(angle), np.sin(angle)])
    a, b = unit * 2, unit * 7
    params = StitchParams(underlay=False, pull_compensation_mm=0)
    points = satin_points(a, b, params)
    polygon = Polygon(np.vstack([a, b[::-1]]))
    segments = linestrings(np.stack([points[:-1], points[1:]], axis=1))
    assert covered_by(segments, polygon.buffer(0.001)).all()
    outer = points[np.isclose(np.linalg.norm(points, axis=1), 7, atol=0.002)]
    assert np.linalg.norm(np.diff(outer, axis=0), axis=1).max() <= 0.405
    # Short stitches move inner penetrations into the column instead of repeatedly
    # stabbing the crowded inner rail.
    assert np.any((np.linalg.norm(points, axis=1) > 2.1) & (np.linalg.norm(points, axis=1) < 5))


def test_running_preserves_curve_and_maximum_length():
    angle = np.linspace(0, np.pi, 301)
    original = np.column_stack([10 * np.cos(angle), 10 * np.sin(angle)])
    points = resample_running(original, 2.5)
    assert np.linalg.norm(np.diff(points, axis=0), axis=1).max() <= 2.501
    assert LineString(original).hausdorff_distance(LineString(points)) <= 0.121
    assert np.allclose(points[[0, -1]], original[[0, -1]])


def test_tatami_clips_holes_and_staggers_rows():
    polygon = Polygon(
        [(0, 0), (30, 0), (30, 20), (0, 20)], [[(10, 5), (20, 5), (20, 15), (10, 15)]]
    )
    paths = list(fill_paths(polygon, 27, 0.4, 3.6))
    assert len(paths) > 50
    assert all(polygon.buffer(1e-8).covers(LineString(p)) for p in paths)
    assert max(np.linalg.norm(np.diff(p, axis=0), axis=1).max() for p in paths) < 4.0


@pytest.mark.parametrize("mode", ["fill", "split"])
def test_wide_regions_underlay_and_bounded_stitches(mode):
    element = column(width=15)
    params = StitchParams(wide_mode=mode, max_stitch_mm=6.0)
    plan = build_stitch_plan([element], params)
    assert plan.stats["underlay_stitches"] > 0
    assert plan.stats["fill_regions"] == (mode == "fill")
    assert plan.stats["satin_regions"] == (mode == "split")
    assert plan.stats["max_stitch_mm"] <= 6.15
    assert plan.stats["short_stitches"] == 0
    assert plan.stats["unsafe_connections"] == 0
    allowed = Polygon(np.vstack([element["rail_a"], element["rail_b"][::-1]])).buffer(0.25)
    assert covered_by(linestrings(sew_segments(plan)), allowed).all()


@pytest.mark.parametrize("compensation", [0, 0.15])
def test_divided_columns_keep_outer_rails_and_stagger_internal_penetrations(compensation):
    params = StitchParams(underlay=False, pull_compensation_mm=compensation)
    element = column(width=7.8)
    element["stitch_type"] = "satin"
    divided = _split_columns([element], 7.5, params)
    assert len(divided) == 2
    np.testing.assert_array_equal(divided[0]["rail_a"], element["rail_a"])
    np.testing.assert_array_equal(divided[-1]["rail_b"], element["rail_b"])
    plan = build_stitch_plan(divided, params)
    assert plan.stats["max_stitch_mm"] <= 7.5
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    top = np.vstack(
        [block.points + plan.origin_mm for block in plan.blocks if block.kind == "satin"]
    )
    seam = top[np.abs(top[:, 1]) < 1]
    assert np.ptp(seam[:, 1]) > 0.5


def test_taper_quantization_and_separate_regions_use_jumps():
    taper = {
        "type": "satin",
        "rail_a": [[0, 0], [10, -2], [25, -0.75]],
        "rail_b": [[0, 0], [10, 2], [25, 0.75]],
    }
    running = {"type": "running", "points": [[40, 0], [60, 0]]}
    plan = build_stitch_plan([taper, running], StitchParams(pull_compensation_mm=0, underlay=False))
    assert plan.stats["trims"] >= 2
    assert plan.stats["jumps"] >= 2
    assert plan.stats["short_stitches"] == 0
    segments = sew_segments(plan)
    # No stitched bridge across the empty 15 mm gap.
    assert not np.any((segments[:, 0, 0] < 30) & (segments[:, 1, 0] > 30))
    assert np.issubdtype(np.asarray(plan.commands).dtype, np.integer)


@pytest.mark.parametrize(
    "extra",
    [
        {"satin_spacing_mm": float("nan")},
        {"pull_compensation_mm": -1},
        {"hoop_width_mm": 0},
        {"wide_mode": "unknown"},
        {"thread_color": "red"},
        {"max_stitches": 10},
    ],
)
def test_invalid_stitch_settings_before_output(tmp_path, extra):
    with pytest.raises(ValueError):
        generate(
            EXAMPLES / "satin-demo.svg",
            tmp_path / "output",
            method="direct",
            stitch_params=StitchParams(**extra),
        )
    assert not (tmp_path / "output").exists()


def test_hoop_and_budget_fail_without_silent_scaling():
    with pytest.raises(ValueError, match="hoop"):
        build_stitch_plan([column(length=150)])
    with pytest.raises(ValueError, match="budget"):
        build_stitch_plan([column(length=80)], StitchParams(max_stitches=100))


def test_direct_cli_and_invalid_method(tmp_path):
    from embroidery_rungs.cli import main

    assert (
        main(
            [
                str(EXAMPLES / "satin-demo.svg"),
                "--output-dir",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert (tmp_path / "satin-demo_direct.pes").is_file()
    with pytest.raises(ValueError, match="method"):
        generate(EXAMPLES / "satin-demo.svg", tmp_path, method="unknown")


@pytest.mark.parametrize(
    "source",
    sorted(EXAMPLES.rglob("*.svg")),
    ids=lambda path: path.relative_to(EXAMPLES).as_posix(),
)
def test_real_machine_exports_roundtrip_and_match_plan(tmp_path, source):
    result = generate(
        source,
        tmp_path,
        stitch_params=StitchParams(hoop_width_mm=500, hoop_height_mm=500),
    )
    direct = result.direct
    data = json.loads(Path(direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    planned = commands[commands[:, 2] == pe.STITCH, :2]
    assert len(planned) == direct.stats["stitches"] > 0
    for path in (direct.pes_path, direct.dst_path):
        pattern = pe.read(path)
        array = np.asarray(pattern.stitches)
        actual = array[(array[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2]
        assert np.array_equal(actual, planned)
        assert pattern.count_stitch_commands(pe.END) == 1
        assert len(pattern.threadlist) >= 1
    assert Path(direct.pes_path).read_bytes().startswith(b"#PES0060")
    assert Path(direct.preview_path).read_bytes().startswith(b"\x89PNG")
    assert direct.stats["short_stitches"] == 0
    assert direct.stats["max_stitch_mm"] <= 8.0
    assert direct.stats["width_mm"] == np.ptp(planned[:, 0]) / 10
    assert direct.stats["height_mm"] == np.ptp(planned[:, 1]) / 10


def test_machine_writer_failure_preserves_previous_outputs(tmp_path, monkeypatch):
    source = EXAMPLES / "satin-demo.svg"
    first = generate(source, tmp_path)
    paths = [
        Path(first.original_path),
        Path(first.direct.pes_path),
        Path(first.direct.dst_path),
        Path(first.direct.plan_path),
        Path(first.direct.svg_path),
        Path(first.direct.preview_path),
    ]
    originals = {p.name: p.read_bytes() for p in paths}

    def failed_writer(*args, **kwargs):
        raise OSError("writer failed")

    monkeypatch.setattr(pe, "write_dst", failed_writer)
    with pytest.raises(OSError, match="writer failed"):
        generate(source, tmp_path)
    assert {p.name: p.read_bytes() for p in paths} == originals
    assert not list(tmp_path.glob(".embroidery-*"))


def test_satin_outer_pitch_and_inner_penetrations_remain_regular_after_quantization():
    from scipy.spatial import cKDTree

    angle = np.linspace(0, np.pi / 2, 101)
    unit = np.column_stack([np.cos(angle), np.sin(angle)])
    params = StitchParams(underlay=False, pull_compensation_mm=0)
    points = np.rint(satin_points(unit * 2, unit * 7, params) * 10) / 10
    # Ignore the terminal cross-section: each side advances one physical row pitch.
    inner, outer = points[:-1:2], points[1:-1:2]
    outer_pitch = np.linalg.norm(np.diff(outer, axis=0), axis=1)
    assert outer_pitch.max() <= params.satin_spacing_mm + 0.12
    assert outer_pitch.min() >= params.satin_spacing_mm - 0.12
    assert cKDTree(inner).query(inner, k=2)[0][:, 1].min() >= 0.25
    plan = build_stitch_plan([{"type": "satin", "rail_a": unit * 2, "rail_b": unit * 7}], params)
    assert plan.stats["unsafe_connections"] == 0
    assert plan.stats["short_stitches"] == 0


def test_narrow_taper_keeps_regular_satin_and_bounded_cap_stitches(tmp_path):
    source = tmp_path / "narrow-taper.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="15mm" viewBox="0 0 50 15"><path d="M5 7.5L45 5.5L45 9.5Z"/></svg>'
    )
    result = generate(source, tmp_path / "out", method="direct")
    assert {d["method"] for d in result.direct.decisions} == {"satin"}
    assert result.direct.stats["structural_coverage"] >= 0.999
    assert result.direct.stats["short_stitches"] == 0
    assert result.direct.stats["max_stitch_mm"] < 4.5
