import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import box

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.cli import main
from embroidery_rungs.stitching.quality import measure_stitches

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/quality"


@pytest.mark.parametrize(
    "shape,method",
    [
        ("straight", "satin"),
        ("ring", "satin"),
        ("star", "fill"),
        ("taper", "fill"),
        ("holes", "fill"),
        ("thin", "satin"),
    ],
)
def test_automatic_selection_retains_columns_and_fills_missing_surfaces(tmp_path, shape, method):
    result = generate(
        EXAMPLES / f"{shape}.svg", tmp_path, GenerationParams(auto_optimize=True), method="both"
    )
    assert {d["method"] for d in result.direct.decisions} == {method}
    assert result.direct.stats["unsafe_connections"] == 0
    assert result.direct.stats["short_stitches"] == 0
    assert result.direct.stats["max_stitch_mm"] <= 8
    if shape == "holes":
        assert result.direct.stats["fill_regions"] == 1
        assert result.direct.stats["gap_fill_regions"] == 0
        assert result.direct.stats["trims"] < 25
        data = json.loads(Path(result.direct.plan_path).read_text())
        commands = np.asarray(data["commands"])
        sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
        segments = (
            np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
        )
        for hole in (box(20.5, 20.5, 34.5, 39.5), box(45.5, 30.5, 59.5, 49.5)):
            assert not intersects(linestrings(segments), hole).any()


def test_manual_controls_and_auto_preserve_legacy_svgs(tmp_path):
    source = EXAMPLES / "holes.svg"
    old = generate(source, tmp_path)
    files = [Path(p) for p in (old.rungs_path, old.ready_path, old.satin_path)]
    content = [p.read_bytes() for p in files]
    automatic = generate(source, tmp_path, method="both")
    assert automatic.direct.decisions
    assert [p.read_bytes() for p in files] == content
    manual = generate(
        source, tmp_path, method="direct", stitch_params=StitchParams(auto_select=False)
    )
    assert manual.direct.decisions == []
    assert [p.read_bytes() for p in files] == content


def test_manual_fill_angle_is_honored(tmp_path):
    direct = generate(
        EXAMPLES / "holes.svg",
        tmp_path,
        method="direct",
        stitch_params=StitchParams(auto_fill_angle=False, fill_angle_deg=27),
    ).direct
    assert direct.decisions[0]["fill_angle_deg"] == 27


def test_complex_swoosh_does_not_choose_hundreds_of_cuts_for_the_same_coverage(tmp_path):
    result = generate(
        EXAMPLES.parent / "nike.svg",
        tmp_path,
        GenerationParams(auto_optimize=True),
        method="direct",
        stitch_params=StitchParams(hoop_width_mm=500, hoop_height_mm=500),
    )
    assert result.direct.stats["trims"] < 50
    assert result.direct.stats["unsafe_connections"] == 0
    assert result.direct.stats["short_stitches"] == 0
    assert result.direct.stats["max_stitch_mm"] <= 8


def test_material_and_thread_presets_with_explicit_overrides():
    stable = StitchParams.for_fabric("stable")
    stretch = StitchParams.for_fabric("stretch", stabilizer="cutaway")
    fine = StitchParams.for_fabric("stable", thread_weight=60)
    assert stretch.pull_compensation_mm > stable.pull_compensation_mm
    assert stretch.satin_spacing_mm > stable.satin_spacing_mm
    assert fine.fill_spacing_mm < stable.fill_spacing_mm
    explicit = StitchParams.for_fabric(
        "stretch", thread_weight=60, satin_spacing_mm=0.6, underlay=False
    )
    assert explicit.satin_spacing_mm == 0.6
    assert not explicit.underlay
    for fabric in ("custom", "stable", "stretch", "textured"):
        for weight in (30, 40, 60):
            StitchParams.for_fabric(fabric, thread_weight=weight).validate()


def test_cli_material_options_are_saved_and_manual_values_win(tmp_path, capsys):
    assert (
        main(
            [
                str(EXAMPLES / "straight.svg"),
                "--method",
                "direct",
                "--fabric",
                "stretch",
                "--thread-weight",
                "60",
                "--stabilizer",
                "cutaway",
                "--stitch-spacing",
                "0.5",
                "--fill-angle",
                "23",
                "--output-dir",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    settings = data["direct"]["params"]
    assert settings["fabric"] == "stretch"
    assert settings["thread_weight"] == 60
    assert settings["stabilizer"] == "cutaway"
    assert settings["satin_spacing_mm"] == 0.5
    assert not settings["auto_fill_angle"]


def test_quality_metrics_use_sewn_segments_and_exclude_jumps():
    target = np.zeros((60, 120), dtype=bool)
    target[20:40, 10:30] = True
    target[20:40, 90:110] = True
    commands = [
        [10, 30, pe.JUMP],
        [10, 30, pe.STITCH],
        [30, 30, pe.STITCH],
        [90, 30, pe.JUMP],
        [90, 30, pe.STITCH],
        [110, 30, pe.STITCH],
    ]
    metrics, image = measure_stitches(commands, (0, 0), target, 10, (0, 0))
    assert not np.asarray(image)[:, 40:80].any()
    assert metrics["max_stitch_mm"] == 2
    assert metrics["structural_coverage"] > metrics["coverage"]
