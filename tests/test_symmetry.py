"""Public-API regressions for equivalent regions and their actual machine stitches."""

import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import box

from embroidery_rungs import StitchParams, generate


def _generate(tmp_path, content, *, name="shape", width=100, height=100, stitch_type="auto"):
    source = tmp_path / f"{name}.svg"
    source.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" '
        f'height="{height}mm" viewBox="0 0 {width} {height}">{content}</svg>'
    )
    result = generate(
        source,
        tmp_path / f"{name}-output",
        method="direct",
        stitch_params=StitchParams.for_fabric("stable", thread_weight=40, stitch_type=stitch_type),
    ).direct
    data = json.loads(Path(result.plan_path).read_text())
    _assert_machine_quality(result, data)
    return result, data


def _assert_machine_quality(result, data):
    assert result.stats["structural_coverage"] >= 0.999
    assert result.stats["largest_gap_mm2"] <= 0.05
    assert result.stats["omitted_regions"] == 0
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    lengths = np.linalg.norm(np.diff(commands[:, :2], axis=0), axis=1)[sewn] / 10
    assert len(lengths)
    assert lengths.min() >= result.params.min_stitch_mm - 0.001
    assert lengths.max() <= result.params.max_stitch_mm + 0.001
    assert data["top_layer_runs"]
    expected = commands[commands[:, 2] == pe.STITCH, :2]
    for path in (result.pes_path, result.dst_path):
        actual = np.asarray(pe.read(path).stitches)
        stitches = (actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH
        assert np.array_equal(actual[stitches, :2], expected)


def _top_runs(data):
    commands = np.asarray(data["commands"])
    return [
        (
            run,
            commands[run["start"] : run["end"], :2] / 10 + data["origin_mm"],
        )
        for run in data["top_layer_runs"]
    ]


def _fill_row_vectors(data, *, right):
    vectors = []
    for run, points in _top_runs(data):
        if run["kind"] != "fill" or (points[:, 0].mean() > 50) != right:
            continue
        differences = np.diff(points, axis=0)
        # Finish contours use <=1.5 mm steps; inspect the longer sewn tatami rows.
        lengths = np.linalg.norm(differences, axis=1)
        vectors.extend(differences[lengths > 2.0])
    vectors = np.asarray(vectors)
    assert len(vectors) > 10
    return vectors


def _assert_vectors_follow_angle(vectors, angle):
    radians = np.radians(angle)
    normal = np.array([-np.sin(radians), np.cos(radians)])
    deviation = np.abs(vectors @ normal) / np.linalg.norm(vectors, axis=1)
    # The writers retain the 0.1 mm grid; its rounding can slightly tilt a row.
    assert np.quantile(deviation, 0.95) < np.sin(np.radians(4))


@pytest.mark.parametrize("stitch_type,method", [("fill", "fill"), ("auto", "satin")])
def test_rotated_l_regions_share_strategy_and_actual_stitch_direction(
    tmp_path, stitch_type, method
):
    body = '<path d="M10 10H40V15H17V35H10Z"/><path d="M90 90H60V85H83V65H90Z"/>'
    result, data = _generate(tmp_path, body, stitch_type=stitch_type)
    decisions = result.decisions
    assert len(decisions) == 2
    assert {decision["method"] for decision in decisions} == {method}
    if method == "fill":
        assert decisions[0]["fill_angle_deg"] % 180 == pytest.approx(
            decisions[1]["fill_angle_deg"] % 180
        )
        angle = decisions[0]["fill_angle_deg"]
        _assert_vectors_follow_angle(_fill_row_vectors(data, right=False), angle)
        _assert_vectors_follow_angle(_fill_row_vectors(data, right=True), angle)
    else:
        assert decisions[0]["equivalence_group"] == decisions[1]["equivalence_group"]
        assert decisions[0]["satin_angle_deg"] % 180 == pytest.approx(
            decisions[1]["satin_angle_deg"] % 180
        )
        for right, decision in zip((False, True), decisions, strict=True):
            vectors = np.concatenate(
                [
                    np.diff(points, axis=0)
                    for run, points in _top_runs(data)
                    if run["kind"] == "satin" and (points[:, 0].mean() > 50) == right
                ]
            )
            vectors = vectors[np.linalg.norm(vectors, axis=1) > 2]
            assert len(vectors) > 10
            angles = np.arctan2(vectors[:, 1], vectors[:, 0])
            lengths = np.linalg.norm(vectors, axis=1)
            axial = (
                np.degrees(
                    np.arctan2(
                        np.sum(lengths * np.sin(2 * angles)),
                        np.sum(lengths * np.cos(2 * angles)),
                    )
                )
                / 2
            )
            # Satin alternates a cross-section with a step along the next row.
            # Its mean axial direction, rather than each diagonal, follows the rail angle.
            deviation = abs((axial - decision["satin_angle_deg"] + 90) % 180 - 90)
            assert deviation < 4
            assert decision["actual_top_metrics"]["crowded_satin_penetrations"] == 0
        assert result.stats["underlay_stitches"] > 0


def test_reflected_broad_columns_reflect_fill_angle_and_actual_rows(tmp_path):
    body = (
        '<g transform="translate(23 30) rotate(30)">'
        '<rect x="-16" y="-6" width="32" height="12"/></g>'
        '<g transform="translate(77 30) scale(-1 1) rotate(30)">'
        '<rect x="-16" y="-6" width="32" height="12"/></g>'
    )
    result, data = _generate(tmp_path, body, height=80)
    assert len(result.decisions) == 2
    assert {decision["method"] for decision in result.decisions} == {"fill"}
    left = _fill_row_vectors(data, right=False)
    right = _fill_row_vectors(data, right=True)
    angles = [decision["fill_angle_deg"] for decision in result.decisions]
    assert (angles[0] + angles[1]) % 180 == pytest.approx(0, abs=1e-8)

    # Compare actual thread directions modulo 180, independently of decision IDs.
    def axial_angle(vectors):
        angles = np.arctan2(vectors[:, 1], vectors[:, 0])
        return (
            np.degrees(np.arctan2(np.sin(2 * angles).mean(), np.cos(2 * angles).mean())) / 2 % 180
        )

    difference = abs(axial_angle(left) - axial_angle(right * [-1, 1]))
    assert min(difference, 180 - difference) < 2


def test_repeated_rings_receive_one_common_top_layer_strategy(tmp_path):
    body = (
        '<circle cx="24" cy="25" r="17" fill="none" stroke="black" stroke-width="4"/>'
        '<circle cx="76" cy="75" r="17" fill="none" stroke="black" stroke-width="4"/>'
    )
    result, data = _generate(tmp_path, body)
    assert len(result.decisions) == 2
    methods = {decision["method"] for decision in result.decisions}
    assert len(methods) == 1
    assert methods <= {"satin", "fill"}
    left = {run["kind"] for run, points in _top_runs(data) if points[:, 0].mean() < 50}
    right = {run["kind"] for run, points in _top_runs(data) if points[:, 0].mean() > 50}
    assert left == right == methods
    assert result.stats["crowded_satin_penetrations"] == 0


def test_repeated_generation_retains_identical_commands_and_machine_files(tmp_path):
    body = (
        '<path fill="#123a80" fill-rule="evenodd" '
        'd="M8 10H88V65H8Z M20 25H35V48H20Z M55 20H76V40H55Z"/>'
        '<rect x="30" y="72" width="42" height="4" fill="#c8102e"/>'
    )
    first, first_data = _generate(tmp_path, body, name="repeated")
    pes = Path(first.pes_path).read_bytes()
    dst = Path(first.dst_path).read_bytes()
    second, second_data = _generate(tmp_path, body, name="repeated")
    assert (
        np.asarray(first_data["commands"]).tobytes()
        == np.asarray(second_data["commands"]).tobytes()
    )
    assert first_data["top_layer_runs"] == second_data["top_layer_runs"]
    assert first_data["decisions"] == second_data["decisions"]
    assert Path(second.pes_path).read_bytes() == pes
    assert Path(second.dst_path).read_bytes() == dst


def test_translation_preserves_non_round_region_paths_in_local_coordinates(tmp_path):
    body = '<path d="M10 10H40V15H17V35H10Z"/>'
    # Integer pixels at the digitizer's 305 DPI isolate translation from resampling.
    offset = np.array([120, 60]) * 25.4 / 305
    first, first_data = _generate(tmp_path, body, name="original", width=80, height=80)
    second, second_data = _generate(
        tmp_path,
        f'<g transform="translate({offset[0]:.12f} {offset[1]:.12f})">{body}</g>',
        name="translated",
        width=80,
        height=80,
    )
    assert first.decisions[0]["method"] == second.decisions[0]["method"]
    assert first.decisions[0]["fill_angle_deg"] == second.decisions[0]["fill_angle_deg"]
    first_runs, second_runs = _top_runs(first_data), _top_runs(second_data)
    assert len(first_runs) == len(second_runs)
    for (a, points_a), (b, points_b) in zip(first_runs, second_runs, strict=True):
        assert a["kind"] == b["kind"]
        assert points_a.shape == points_b.shape
        np.testing.assert_allclose(points_a, points_b - offset, atol=0.100001, rtol=0)


@pytest.mark.parametrize("width,method", [(0.5, "fill"), (0.6, "fill"), (0.8, "satin")])
def test_narrow_fork_does_not_advertise_a_phantom_foundation(tmp_path, width, method):
    body = (
        f'<path fill="none" stroke="black" stroke-width="{width}" stroke-linejoin="round" '
        'd="M20 40L40 20L60 40M40 20V55"/>'
    )
    result, _ = _generate(tmp_path, body, width=80, height=80)
    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision["method"] == method
    actual_support = decision["actual_top_metrics"]["underlay_stitches"]
    assert result.stats["underlay_stitches"] == actual_support
    assert decision["underlay"] == (actual_support > 0)
    assert decision["underlay_strategy"] == ("center" if method == "satin" else "none")
    assert (actual_support > 0) == (method == "satin")


def test_equivalent_narrow_forks_share_the_actual_foundation_policy(tmp_path):
    body = (
        '<path fill="none" stroke="black" stroke-width="0.5" stroke-linejoin="round" '
        'd="M5 25L25 5L45 25M25 5V40 M95 75L75 95L55 75M75 95V60"/>'
    )
    result, _ = _generate(tmp_path, body)
    assert len(result.decisions) == 2
    assert len({d["equivalence_group"] for d in result.decisions}) == 1
    assert result.stats["underlay_stitches"] == 0
    for decision in result.decisions:
        assert decision["method"] == "fill"
        assert decision["equivalent_regions"] == 2
        assert decision["actual_top_metrics"]["underlay_stitches"] == 0
        assert not decision["underlay"]
        assert decision["underlay_strategy"] == "none"


def test_narrow_fill_keeps_its_counter_without_a_phantom_foundation(tmp_path):
    body = '<path fill-rule="evenodd" d="M10 30H30V31.3H10Z M10.35 30.35H29.65V30.95H10.35Z"/>'
    result, data = _generate(tmp_path, body, width=80, height=80)
    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision["method"] == "fill"
    assert result.stats["underlay_stitches"] == 0
    assert decision["actual_top_metrics"]["underlay_stitches"] == 0
    assert not decision["underlay"]
    assert decision["underlay_strategy"] == "none"
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = (
        np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
    )
    assert not intersects(linestrings(segments), box(10.55, 30.55, 29.45, 30.75)).any()
