"""Trace small real paint and counters rather than hiding them in area scores."""

from __future__ import annotations

import io
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import resvg_py
from PIL import Image

from embroidery_rungs.interpretation import audit, tracing
from embroidery_rungs.interpretation.audit import audit_trace, topology
from embroidery_rungs.interpretation.tracing import serialize_bitmap, trace_path
from embroidery_rungs.interpretation.types import RasterArtwork
from embroidery_rungs.svg_manager import MAX_INPUT_BYTES


def _artwork(labels, palette=("#000000",), size=None):
    labels = np.asarray(labels, dtype=np.uint8)
    height, width = labels.shape
    return RasterArtwork(labels, palette, size or (float(width), float(height)))


def _root(path, shape, fill="#000000"):
    height, width = shape
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(width),
        height=str(height),
        viewBox=f"0 0 {width} {height}",
        attrib={"shape-rendering": "crispEdges"},
    )
    ET.SubElement(root, "path", fill=fill, attrib={"fill-rule": "evenodd", "d": path})
    return root


def test_one_pixel_accent_is_really_lost_by_previous_simplification():
    labels = np.zeros((12, 12), np.uint8)
    labels[6, 6] = 1
    path, nodes = trace_path(labels > 0, 0.5)
    initial = audit_trace(_root(path, labels.shape), _artwork(labels), node_count=nodes)
    assert initial["changed_pixels"] == 1
    assert initial["paints"]["alpha"]["source"]["components"] == 1
    assert initial["paints"]["alpha"]["rendered"]["components"] == 0


@pytest.mark.parametrize("counter_side", [1, 2, 3, 4])
def test_actual_alpha_counters_survive_simplification(counter_side):
    labels = np.zeros((18, 18), np.uint8)
    labels[2:16, 2:16] = 1
    labels[7 : 7 + counter_side, 7 : 7 + counter_side] = 0
    artwork = _artwork(labels)
    root, diagnostics = serialize_bitmap(artwork, 0.5, crisp_edges=True)
    assert diagnostics["final"]["passed"]
    assert diagnostics["final"]["paints"]["alpha"]["source"]["holes"] == 1
    assert diagnostics["final"]["paints"]["alpha"]["rendered"]["holes"] == 1
    assert diagnostics["final"]["silhouette_changed_pixels"] == 0
    assert root.get("viewBox") == "0 0 18 18"
    assert np.array_equal(artwork.labels, labels)
    if counter_side == 1:
        assert diagnostics["fallback"]
        assert diagnostics["initial"]["paints"]["alpha"]["rendered"]["holes"] == 0
        assert diagnostics["fallback_reason"] == "simplification_changed_topology"


def test_each_paint_keeps_its_tiny_accent_and_counter():
    labels = np.zeros((20, 24), np.uint8)
    labels[2:18, 2:22] = 1
    labels[4:15, 4:12] = 2
    labels[6:14, 14:20] = 3
    labels[9, 8] = 0
    labels[16, 15] = 2
    artwork = _artwork(labels, ("#010101", "#ffffff", "#fd0201"))
    root, diagnostics = serialize_bitmap(artwork, 0.5, crisp_edges=True)
    assert diagnostics["fallback"]
    assert diagnostics["final"]["changed_pixels"] == 0
    assert diagnostics["final"]["topology_preserved"]
    assert diagnostics["final"]["paints"]["#ffffff"]["source"]["components"] == 2
    assert len(root.findall("path")) == 3
    assert all(path.get("fill-rule") == "evenodd" for path in root)


def test_diagonally_touching_accents_remain_separate_in_fg4():
    labels = np.zeros((16, 16), np.uint8)
    labels[6, 6] = labels[7, 7] = 1
    _, diagnostics = serialize_bitmap(_artwork(labels), 0.5, crisp_edges=True)
    alpha = diagnostics["final"]["paints"]["alpha"]
    assert alpha["source"] == alpha["rendered"] == {"components": 2, "holes": 0}


def test_counter_connected_diagonally_to_outside_is_not_a_bg8_hole():
    mask = np.zeros((8, 8), bool)
    mask[1:7, 1:7] = True
    mask[1, 1] = mask[2, 2] = mask[3, 3] = False
    assert topology(mask) == {"components": 1, "holes": 0}
    labels = mask.astype(np.uint8)
    _, diagnostics = serialize_bitmap(_artwork(labels), 0.5, crisp_edges=True)
    assert diagnostics["final"]["passed"]


def test_audit_uses_original_pixel_centres_and_does_not_move_emitted_svg():
    labels = np.zeros((12, 12), np.uint8)
    labels[6, 6] = 1
    root, diagnostics = serialize_bitmap(_artwork(labels, size=(24, 36)), 0, crisp_edges=True)
    assert diagnostics["final"]["audit_viewbox"] == [-0.5, -0.5, 12, 12]
    assert diagnostics["final"]["grid"] == "integer_pixel_centres"
    assert root.get("viewBox") == "0 0 12 12"
    assert root.get("width") == "24mm"
    assert root.get("height") == "36mm"
    # A native ordinary SVG samples half-integers; this is why the audit copy
    # documents its alignment rather than silently moving output geometry.
    png = resvg_py.svg_to_bytes(
        svg_string=ET.tostring(root, encoding="unicode"),
        width=12,
        height=12,
        dpi=96,
        skip_system_fonts=True,
    )
    assert not np.asarray(Image.open(io.BytesIO(png)))[..., 3].any()


def test_matching_component_counts_do_not_hide_moved_paint():
    expected = np.zeros((12, 12), np.uint8)
    expected[5, 5] = 1
    moved = np.zeros_like(expected)
    moved[5, 6] = 1
    path, nodes = trace_path(moved > 0, 0)
    result = audit_trace(
        _root(path, moved.shape), _artwork(expected, size=(24, 36)), node_count=nodes
    )
    assert result["topology_preserved"]
    assert not result["passed"]
    assert result["changed_pixels"] == 2
    assert result["changed_area_mm2"] == 12
    assert result["paints"]["alpha"]["contour"] == {
        "p95_mm": 2.0,
        "max_mm": 2.0,
        "missing_boundary": False,
    }


def test_render_once_per_complete_design_attempt(monkeypatch):
    labels = np.zeros((16, 20), np.uint8)
    labels[2:14, 2:10] = 1
    labels[2:14, 10:18] = 2
    artwork = _artwork(labels, ("#fd0000", "#ff0000"))
    calls = []
    render = audit.resvg_py.svg_to_bytes

    def tracked(**kwargs):
        calls.append(kwargs)
        return render(**kwargs)

    monkeypatch.setattr(audit.resvg_py, "svg_to_bytes", tracked)
    _, diagnostics = serialize_bitmap(artwork, 0.25, crisp_edges=True)
    assert len(calls) == diagnostics["render_attempts"] == 1
    assert diagnostics["final"]["passed"]


def test_conservative_contours_remove_only_collinear_nodes():
    labels = np.zeros((100, 160), np.uint8)
    labels[5:95, 5:155] = 1
    _, diagnostics = serialize_bitmap(_artwork(labels), 0, crisp_edges=True)
    assert diagnostics["final"]["nodes"] == 8
    assert diagnostics["final"]["changed_pixels"] == 0


@pytest.mark.parametrize("seed", range(4))
def test_dense_multicolour_masks_keep_every_pixel_and_topology(seed):
    labels = np.pad(np.random.default_rng(seed).integers(0, 4, size=(24, 32), dtype=np.uint8), 1)
    artwork = _artwork(labels, ("#000000", "#ffffff", "#dd0033"))
    _, diagnostics = serialize_bitmap(artwork, 0.5, crisp_edges=True)
    assert diagnostics["fallback"]
    assert diagnostics["initial"]["changed_pixels"] > 0
    assert diagnostics["final"]["changed_pixels"] == 0
    assert diagnostics["final"]["topology_preserved"]
    assert all(paint["contour"]["max_mm"] == 0 for paint in diagnostics["final"]["paints"].values())


def test_trace_budget_is_checked_before_any_render(monkeypatch):
    labels = np.zeros((8, 8), np.uint8)
    labels[3, 3] = 1
    root = _root("M " + "1,1 " * (MAX_INPUT_BYTES // 4), labels.shape)

    def unexpected(**kwargs):
        raise AssertionError("oversized SVG reached the renderer")

    monkeypatch.setattr(audit.resvg_py, "svg_to_bytes", unexpected)
    with pytest.raises(ValueError, match="10 MiB"):
        audit_trace(root, _artwork(labels), node_count=MAX_INPUT_BYTES)


@pytest.mark.parametrize("shape", [(3, 16_385), (4097, 4097)])
def test_native_raster_budget_is_checked_before_any_render(shape, monkeypatch):
    labels = np.zeros(shape, np.uint8)
    labels[1, 1] = 1

    def unexpected(**kwargs):
        raise AssertionError("oversized native grid reached the renderer")

    monkeypatch.setattr(audit.resvg_py, "svg_to_bytes", unexpected)
    with pytest.raises(ValueError, match="raster size limit"):
        audit_trace(_root("M 1,1 L 2,1 L 1,2 Z", shape), _artwork(labels), node_count=3)


def test_too_many_counters_are_rejected_before_contours_or_render(monkeypatch):
    labels = np.ones((204, 204), dtype=np.uint8)
    labels[[0, -1], :] = labels[:, [0, -1]] = 0
    labels[2:-2:2, 2:-2:2] = 0
    assert topology(labels > 0) == {"components": 1, "holes": 10_000}

    def unexpected(*args, **kwargs):
        raise AssertionError("over-budget counters reached tracing or rendering")

    monkeypatch.setattr(tracing, "find_contours", unexpected)
    monkeypatch.setattr(audit.resvg_py, "svg_to_bytes", unexpected)
    with pytest.raises(ValueError, match="10001 contours.*limit is 8192"):
        serialize_bitmap(_artwork(labels), 0.5, crisp_edges=True)
    assert np.count_nonzero(labels == 0) == 10_812


@pytest.mark.parametrize("shape", [(3, 16_385), (4097, 4097)])
def test_giant_grid_is_rejected_before_contours_or_render(shape, monkeypatch):
    labels = np.zeros(shape, np.uint8)
    labels[1, 1] = 1

    def unexpected(*args, **kwargs):
        raise AssertionError("over-budget grid reached tracing or rendering")

    monkeypatch.setattr(tracing, "find_contours", unexpected)
    monkeypatch.setattr(audit.resvg_py, "svg_to_bytes", unexpected)
    with pytest.raises(ValueError, match="raster size limit"):
        serialize_bitmap(_artwork(labels), 0.5, crisp_edges=True)


@pytest.mark.parametrize("tolerance", [-1, np.nan, np.inf])
def test_invalid_tolerance_is_rejected(tolerance):
    labels = np.zeros((8, 8), np.uint8)
    labels[3, 3] = 1
    with pytest.raises(ValueError, match="tolerance"):
        serialize_bitmap(_artwork(labels), tolerance, crisp_edges=True)
