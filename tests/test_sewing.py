"""Physical planning regressions; geometric checks do not replace a sew-out."""

import io
import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import covers, linestrings
from shapely.geometry import Polygon, box

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.cli import main
from embroidery_rungs.stitching.paths import fill_paths
from embroidery_rungs.stitching.planner import (
    UnstitchableRegion,
    _compensated_fill,
    _machine_points,
    build_stitch_plan,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/quality"


@pytest.mark.parametrize("angle", [0, 30, 90, 145])
def test_pull_compensation_extends_only_along_sewn_rows(angle):
    from shapely.affinity import rotate

    source = rotate(box(0, 0, 20, 10), angle, origin=(0, 0))
    compensated = _compensated_fill(source, 0.25, angle)
    aligned = rotate(compensated, -angle, origin=(0, 0))
    assert aligned.bounds == pytest.approx((-0.25, 0, 20.25, 10), abs=1e-8)
    assert compensated.buffer(1e-8).covers(source)
    assert compensated.area == pytest.approx(205)


@pytest.mark.parametrize("angle", [0, 45, 90])
def test_directional_compensation_retains_counters_and_concavities(angle):
    source = Polygon(
        [(0, 0), (30, 0), (30, 20), (15, 20), (15, 10), (0, 10)],
        [[(20, 5), (26, 5), (26, 15), (20, 15)]],
    )
    compensated = _compensated_fill(source, 0.25, angle)
    assert compensated.is_valid
    assert compensated.intersection(box(20.01, 5.01, 25.99, 14.99)).is_empty
    assert compensated.intersection(box(0, 10.5, 14.5, 20)).is_empty


@pytest.mark.parametrize("fabric", ["stable", "stretch", "textured"])
def test_fill_foundation_is_inset_and_does_not_cross_a_hole(fabric):
    source = Polygon(box(0, 0, 30, 20).exterior, [box(10, 6, 20, 14).exterior])
    plan = build_stitch_plan([{"type": "fill", "polygon": source}], StitchParams.for_fabric(fabric))
    blocks = [b for b in plan.blocks if b.kind == "underlay"]
    assert blocks
    for block in blocks:
        points = block.points + plan.origin_mm
        assert covers(
            source.buffer(-0.3), linestrings(np.stack([points[:-1], points[1:]], axis=1))
        ).all()
    assert plan.stats["short_stitches"] == 0
    assert plan.stats["max_stitch_mm"] <= 8


def test_stretch_satin_adds_support_without_increasing_top_density():
    element = {"type": "satin", "rail_a": [[0, 0], [30, 0]], "rail_b": [[0, 4], [30, 4]]}
    plans = [
        build_stitch_plan([element], StitchParams(fabric=fabric))
        for fabric in ("stable", "stretch")
    ]
    assert plans[1].stats["underlay_stitches"] > plans[0].stats["underlay_stitches"]
    assert sum(len(b.points) for b in plans[1].blocks if b.kind == "satin") == sum(
        len(b.points) for b in plans[0].blocks if b.kind == "satin"
    )


def test_tatami_honors_physical_minimum_instead_of_fixed_point_three():
    assert list(fill_paths(box(0, 0, 0.2, 2), 0, 0.4, 3, minimum=0.1))
    assert not list(fill_paths(box(0, 0, 0.2, 2), 0, 0.4, 3, minimum=0.3))


def test_quantized_cap_is_retained_when_last_step_is_too_short():
    points = _machine_points(np.array([[0, 0], [1, 0], [1.12, 0]]), np.zeros(2), 0.25)
    assert points[-1] == pytest.approx([1.1, 0])
    assert np.linalg.norm(np.diff(points, axis=0), axis=1).min() >= 0.25


@pytest.mark.parametrize("kind", ["fill", "running"])
def test_subresolution_region_cannot_export_a_phantom_single_penetration(kind):
    element = (
        {"type": "fill", "polygon": box(0, 0, 0.1, 0.1)}
        if kind == "fill"
        else {
            "type": "running",
            "points": [[0, 0], [0.1, 0]],
        }
    )
    with pytest.raises(UnstitchableRegion, match="enlarge"):
        build_stitch_plan([element])


def test_tiny_component_is_explicitly_omitted_without_aborting_other_regions(tmp_path):
    source = tmp_path / "detail.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70"><rect x="10" y="30" width="40" height="4"/><rect x="65" y="20" width=".08" height=".08"/></svg>'
    )
    result = generate(source, tmp_path / "out", method="direct").direct
    assert any(d["method"] == "omitted" for d in result.decisions)
    assert result.stats["omitted_regions"] == 1
    assert any("omitted" in w for w in result.warnings)
    data = json.loads(Path(result.plan_path).read_text())
    assert all(b["end"] - b["start"] >= 2 for b in data["top_layer_runs"])


def test_skitch_profile_recommendations_and_verified_hoop_limit():
    params = StitchParams.for_fabric("stretch", machine="brother-skitch-pp1", stabilizer="cutaway")
    assert (params.max_colors, params.max_satin_width_mm) == (6, 7)
    params.validate()
    explicit = StitchParams.for_fabric(
        machine="brother-skitch-pp1", max_colors=12, max_satin_width_mm=8
    )
    explicit.validate()
    explicit.hoop_width_mm = 101
    with pytest.raises(ValueError, match="100 × 100"):
        explicit.validate()


def test_machine_profile_is_available_via_cli(tmp_path, capsys):
    assert (
        main(
            [
                str(EXAMPLES / "straight.svg"),
                "--method",
                "direct",
                "--machine",
                "brother-skitch-pp1",
                "--output-dir",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    settings = json.loads(capsys.readouterr().out)["direct"]["params"]
    assert settings["machine"] == "brother-skitch-pp1"
    assert settings["max_colors"] == 6
    assert settings["max_satin_width_mm"] == 7


def test_automatic_satin_reserves_compensation_before_the_length_cap(tmp_path):
    source = tmp_path / "broad-column.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70"><rect x="10" y="30" width="60" height="7.8"/></svg>'
    )
    result = generate(source, tmp_path / "out", method="direct").direct
    assert {d["method"] for d in result.decisions} == {"fill"}
    assert result.stats["satin_regions"] == 0
    assert result.stats["max_stitch_mm"] <= 8


def test_machine_profile_api_validation_and_defaults(tmp_path):
    from embroidery_rungs.web.app import create_app

    client = create_app({"TESTING": True, "OUTPUT_ROOT": str(tmp_path)}).test_client()
    assert (
        client.get("/api/capabilities").get_json()["machine_profiles"]["brother-skitch-pp1"][
            "max_area_mm"
        ]
        == 100
    )
    data = {
        "machine": "brother-skitch-pp1",
        "method": "direct",
        "file": (io.BytesIO((EXAMPLES / "straight.svg").read_bytes()), "logo.svg"),
    }
    result = client.post("/api/convert", data=data)
    assert result.status_code == 200
    assert result.get_json()["direct"]["params"]["machine"] == "brother-skitch-pp1"
    bad = client.post(
        "/api/convert",
        data={**data, "file": (io.BytesIO(b"svg"), "logo.svg"), "hoop_height": "120"},
    )
    assert bad.status_code == 400
    assert "100 × 100" in bad.get_json()["error"]


@pytest.mark.parametrize(
    "fabric,weight", [("stable", 40), ("stretch", 40), ("textured", 30), ("stable", 60)]
)
def test_sewout_coupon_has_safe_multicolor_machine_commands(tmp_path, fabric, weight):
    settings = StitchParams.for_fabric(
        fabric, thread_weight=weight, stabilizer="cutaway", machine="brother-skitch-pp1"
    )
    result = generate(
        EXAMPLES / "sewout.svg",
        tmp_path,
        GenerationParams(fit_to_hoop=True),
        method="direct",
        stitch_params=settings,
    ).direct
    assert result.stats["colors"] == 3
    assert result.stats["color_changes"] == 2
    assert result.stats["short_stitches"] == 0
    assert result.stats["max_stitch_mm"] <= settings.max_stitch_mm
    assert result.stats["structural_coverage"] >= 0.999
    assert result.stats["largest_gap_mm2"] <= 0.05
    assert result.stats["omitted_regions"] == 0
    data = json.loads(Path(result.plan_path).read_text())
    expected = np.array(data["commands"])
    for path in (result.pes_path, result.dst_path):
        pattern = pe.read(str(path))
        actual = np.array(pattern.stitches)
        assert np.array_equal(
            actual[(actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2],
            expected[expected[:, 2] == pe.STITCH, :2],
        )
        assert len(pattern.threadlist) == 3
