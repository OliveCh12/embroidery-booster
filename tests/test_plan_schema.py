import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs.stitching.digitizer import _combine
from embroidery_rungs.stitching.export import export_direct
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.planner import build_stitch_plan
from embroidery_rungs.svg_manager import load_svg_paths


def test_schema_three_describes_machine_coordinates_and_command_semantics(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/quality/multicolor.svg"
    svg, _ = load_svg_paths(source)
    requested = StitchParams(hoop_width_mm=90, hoop_height_mm=80)
    names, plan = export_direct(svg, tmp_path, "player", requested)
    data = json.loads((tmp_path / names[-1]).read_text())
    assert data["schema_version"] == 3
    assert data["units"] == "0.1mm"
    assert data["coordinate_frame"] == "hoop_center"
    assert data["hoop"] == {"width_mm": 90, "height_mm": 80, "bounds_mm": [-45, -40, 45, 40]}
    assert data["command_codes"] == {
        "stitch": pe.STITCH,
        "jump": pe.JUMP,
        "trim": pe.TRIM,
        "end": pe.END,
        "color_change": pe.COLOR_CHANGE,
        "command_mask": pe.COMMAND_MASK,
    }
    commands = np.asarray(data["commands"])
    points = commands[commands[:, 2] == pe.STITCH, :2]
    assert np.array_equal(data["machine_bounds_mm"], np.r_[points.min(0), points.max(0)] / 10)
    first = data["playback"]["first_stitch_index"]
    assert data["playback"]["first_point_units"] == data["commands"][first][:2]
    assert data["playback"]["command_count"] == len(commands)
    assert data["playback"]["color_changes"] == data["stats"]["colors"] - 1
    assert data["playback"]["stitch_count"] == int(np.count_nonzero(commands[:, 2] == pe.STITCH))
    assert data["playback"]["timing_basis"] == "needle_cycles_only"
    assert data["machine"]["speed_source"] == "simulation_assumption"
    assert data["requested_params"] == asdict(requested)
    assert data["params"] == asdict(plan.params)
    assert data["adjustments"] == plan.adjustments
    assert data["analysis"]["category"] == "multicolor"
    assert data["underlay_runs"]
    assert all(r["kind"] == "underlay" for r in data["underlay_runs"])
    assert all(r["kind"] in ("satin", "fill", "running") for r in data["top_layer_runs"])
    for run in data["runs"]:
        assert 0 <= run["start"] < run["end"] <= len(commands)
        assert 0 <= run["color_index"] < len(data["threads"])
    for filename in names[:2]:
        pattern = pe.read(str(tmp_path / filename))
        actual = np.asarray(pattern.stitches)
        assert np.array_equal(
            actual[(actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2], points
        )


def test_skitch_metadata_uses_verified_maximum_needle_rate(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/quality/straight.svg"
    svg, _ = load_svg_paths(source)
    names, _ = export_direct(
        svg, tmp_path, "skitch", StitchParams.for_fabric(machine="brother-skitch-pp1")
    )
    data = json.loads((tmp_path / names[-1]).read_text())
    assert data["machine"]["stitches_per_minute"] == 400
    assert data["machine"]["speed_source"] == "machine_profile"


def test_odd_machine_grid_span_cannot_overflow_exact_centered_hoop():
    params = StitchParams(hoop_width_mm=10.1, hoop_height_mm=10, underlay=False)
    plan = build_stitch_plan(
        [{"type": "running", "points": [[0, 0], [10.1, 0]]}], params, origin_mm=(0, 0)
    )
    with pytest.raises(ValueError, match="Centered machine coordinates.*hoop"):
        _combine([plan], ["#000000"], params, (0, 0))


def test_odd_machine_grid_span_fits_with_a_full_grid_unit_of_margin():
    params = StitchParams(hoop_width_mm=10.2, hoop_height_mm=10, underlay=False)
    plan = build_stitch_plan(
        [{"type": "running", "points": [[0, 0], [10.1, 0]]}], params, origin_mm=(0, 0)
    )
    combined = _combine([plan], ["#000000"], params, (0, 0))
    assert np.all(np.abs(np.asarray(combined.commands)[:, :2] / 10) <= [5.1, 5.0])
