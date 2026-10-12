import io
import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from PIL import Image, ImageDraw

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.cli import main


def create_app(config):
    pytest.importorskip("flask")
    from embroidery_rungs.web.app import create_app as create_web_app

    return create_web_app(config)


def badge_bytes():
    image = Image.new("RGB", (160, 120), "#eeeeee")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 20, 120, 100), fill="white", outline="black", width=4)
    draw.rectangle((60, 40, 100, 50), fill="red")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize(
    "settings",
    [{"background_mode": "unknown"}, {"raster_cleanup": "true"}],
)
def test_invalid_interpretation_settings_fail_before_output(tmp_path, settings):
    with pytest.raises(ValueError):
        generate(tmp_path / "missing.png", tmp_path / "out", GenerationParams(**settings))
    assert not (tmp_path / "out").exists()


def test_web_background_controls_preserve_white_badge_and_report_machine_strategy(tmp_path):
    app = create_app({"TESTING": True, "OUTPUT_ROOT": tmp_path / "jobs"})
    response = app.test_client().post(
        "/api/convert",
        data={
            "file": (io.BytesIO(badge_bytes()), "badge.png"),
            "design_width": "35",
            "background_mode": "auto",
            "raster_cleanup": "true",
            "stitch_type": "fill",
        },
    )
    assert response.status_code == 200, response.get_json()
    result = response.get_json()
    assert "#eeeeee" not in result["direct"]["threads"]
    assert "#ffffff" in result["direct"]["threads"]
    assert result["input_analysis"]["background"]["applied"]
    assert result["direct"]["params"]["stitch_type"] == "fill"
    assert {d["method"] for d in result["direct"]["decisions"]} == {"fill"}
    plan = app.test_client().get(result["direct"]["files"]["plan_json"]).get_json()
    assert plan["input_analysis"] == result["input_analysis"]


@pytest.mark.parametrize(
    "setting",
    [{"background_mode": "invalid"}, {"raster_cleanup": "1"}, {"stitch_type": "meander"}],
)
def test_web_invalid_choices_do_not_leave_jobs(tmp_path, setting):
    jobs = tmp_path / "jobs"
    app = create_app({"TESTING": True, "OUTPUT_ROOT": jobs})
    response = app.test_client().post(
        "/api/convert", data={"file": (io.BytesIO(badge_bytes()), "badge.png"), **setting}
    )
    assert response.status_code == 400
    assert not jobs.exists()


def test_cli_explicit_satin_preserves_a_narrow_column(svg_file, tmp_path, capsys):
    source = svg_file('<rect x="10" y="20" width="100" height="8"/>')
    assert (
        main(
            [
                str(source),
                "-o",
                str(tmp_path / "satin"),
                "--stitch-type",
                "satin",
                "--background",
                "keep",
                "--no-raster-cleanup",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["params"]["background_mode"] == "keep"
    assert result["params"]["raster_cleanup"] is False
    assert {d["method"] for d in result["direct"]["decisions"]} == {"satin"}


def test_travel_and_lock_ranges_match_encoded_penetrations(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/quality/multicolor.svg"
    result = generate(source, tmp_path, stitch_params=StitchParams())
    plan = json.loads(Path(result.direct.plan_path).read_text())
    commands = np.asarray(plan["commands"])
    assert sum(plan["analysis"]["stitch_breakdown"].values()) == result.direct.stats["stitches"]
    assert (
        plan["analysis"]["stitch_breakdown"]["underlay"] == result.direct.stats["underlay_stitches"]
    )
    assert plan["analysis"]["stitch_breakdown"]["lock"] > 0
    accessory = [r for r in plan["runs"] if r["kind"] in ("travel", "lock")]
    assert {r["kind"] for r in accessory} == {"travel", "lock"}
    mask = np.zeros(len(commands), dtype=bool)
    for run in accessory:
        start, end = run["start"], run["end"]
        assert 0 <= start < end <= len(commands)
        assert np.all(commands[start + 1 : end, 2] == pe.STITCH)
        mask[start + 1 : end] = True
    for run in plan["top_layer_runs"]:
        assert not mask[run["start"] + 1 : run["end"]].any()
    pattern = pe.read(result.direct.pes_path)
    stitches = np.asarray(pattern.stitches)
    assert np.array_equal(
        stitches[(stitches[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2],
        commands[commands[:, 2] == pe.STITCH, :2],
    )
