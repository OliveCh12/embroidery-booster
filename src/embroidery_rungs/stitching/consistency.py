"""One sewing policy for rigidly equivalent regions, checked on the machine grid."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, replace

import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Polygon
from svgelements import Matrix

from ..image_processor import compute_medial_axis
from ..svg_manager import UNITS_PER_MM
from .params import StitchParams
from .planner import UnstitchableRegion, build_stitch_plan
from .quality import measure_plan, satin_crowding
from .rails import generate_columns
from .regions import Region, canonical_regions, physical_elements, route_region_groups
from .selection import _fill_angle, fill_elements, mask_polygons, select_stitch_types


@dataclass
class RegionCandidate:
    region: Region
    elements: list[dict]
    decision: dict
    polygons: list[Polygon]
    params: StitchParams
    metrics: dict = field(default_factory=dict)


def _assign_policy(members, method, params, angle, finish_inset):
    if method == "fill":
        for member in members:
            local_angle = angle if params.auto_fill_angle else member.params.fill_angle_deg
            member.elements = fill_elements(
                member.polygons, local_angle, params, finish_inset=finish_inset
            )
        # Use the smallest bounded correction: never bloat a thinner counterpart
        # just to copy the larger one's compensation.
        compensation = min(e["compensation"] for m in members for e in m.elements)
        foundation = params.underlay and all(
            p.area >= 4 and not p.buffer(-0.2).is_empty for m in members for p in m.polygons
        )
        inset = {30: 0.5, 40: 0.4, 60: 0.3}[params.thread_weight]
        interiors = [p.buffer(-inset) for m in members for p in m.polygons]
        edge = foundation and all(
            not p.is_empty
            and min(piece.area for piece in ([p] if p.geom_type == "Polygon" else p.geoms))
            >= (4 if params.fabric in ("stretch", "textured") else 10)
            for p in interiors
        )
        for member in members:
            for element in member.elements:
                element.update(compensation=compensation, underlay=foundation, underlay_edge=edge)
        profile = "edge+cross" if edge else "cross" if foundation else "none"
    elif method == "satin":
        widths = [
            np.linalg.norm(e["rail_b"] - e["rail_a"], axis=1) for m in members for e in m.elements
        ]
        edge = params.fabric in ("stretch", "textured") and all(
            np.percentile(width, 25) >= 2.5 for width in widths
        )
        zigzag = all(width.max() >= 3 for width in widths)
        for member in members:
            for element in member.elements:
                element.update(underlay=params.underlay, underlay_edge=edge, underlay_zigzag=zigzag)
        profile = (
            "+".join(["center", *(["edge"] if edge else []), *(["zigzag"] if zigzag else [])])
            if params.underlay
            else "none"
        )
    else:
        if method == "omitted":
            for member in members:
                member.elements = []
        profile = "none"
    for member in members:
        for element in member.elements:
            element["frame"] = member.region.frame
    return profile


def _audit_members(members, method, params, origin, transform, scale):
    passed = True
    for member in members:
        region, elements = member.region, member.elements
        if not elements:
            member.metrics = {}
            continue
        offset = (
            np.array(
                [
                    transform.e - region.bounds[1].start,
                    transform.f - region.bounds[0].start,
                ]
            )
            + 3
        )
        target = np.pad(region.source_mask, 3)
        try:
            candidate = build_stitch_plan(elements, params, origin_mm=origin)
            metrics, _ = measure_plan(candidate, target, scale, offset)
            crowding = satin_crowding(candidate, params.min_stitch_mm)
            if method == "fill" and (
                metrics["structural_coverage"] < 0.9999 or metrics["largest_gap_mm2"] > 0.01
            ):
                for element in elements:
                    element["finish_inset"] = 0.0
                candidate = build_stitch_plan(elements, params, origin_mm=origin)
                metrics, _ = measure_plan(candidate, target, scale, offset)
            metrics["crowded_satin_penetrations"] = crowding
            metrics["underlay_stitches"] = candidate.stats["underlay_stitches"]
            member.metrics = metrics
            passed &= (
                metrics["structural_coverage"] >= 0.999
                and metrics["largest_gap_mm2"] <= 0.05
                and (
                    method != "satin"
                    or (crowding == 0 and candidate.stats["unsafe_connections"] == 0)
                )
            )
        except UnstitchableRegion as exc:
            member.metrics = {"error": str(exc)}
            passed = False
    return passed


def select_consistent_regions(mask, transform, params: StitchParams, origin, symmetries):
    scale = UNITS_PER_MM * math.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    local_transform = Matrix(scale / UNITS_PER_MM, 0, 0, scale / UNITS_PER_MM, 3, 3)
    groups: dict[int, list[RegionCandidate]] = defaultdict(list)
    for region in canonical_regions(mask, transform, symmetries):
        local_mask = np.pad(region.mask, 3)
        local_origin = (np.asarray(region.mask.shape)[::-1] - 1) / (2 * scale)
        # Rotating a temporary frame exchanges width/height; check the real hoop
        # only after restoring source coordinates. Manual angles remain global.
        local_params = replace(
            params,
            hoop_width_mm=max(params.hoop_width_mm, params.hoop_height_mm),
            hoop_height_mm=max(params.hoop_width_mm, params.hoop_height_mm),
            fill_angle_deg=params.fill_angle_deg
            if params.auto_fill_angle
            else region.frame.angle_to_local(params.fill_angle_deg),
        )
        safe_width = min(
            params.max_satin_width_mm,
            params.max_stitch_mm - 0.2 - 2 * params.pull_compensation_mm,
        )
        diameter = 2 * distance_transform_edt(local_mask).max() / scale
        # A clearly broad interior needs fill regardless of its MAT branches.
        # Two raster pixels of margin leave borderline counterparts to the full
        # satin gate and cohort consensus rather than treating edge noise as proof.
        broad = diameter > safe_width + 2 / scale
        elements = []
        if not broad:
            skeleton, distance = compute_medial_axis(local_mask)
            elements = generate_columns(
                skeleton,
                distance,
                local_mask,
                min_satin_width_px=0.5 * scale,
                pixels_per_mm=scale,
            )
        selected, decisions = select_stitch_types(
            physical_elements(elements, local_transform),
            local_mask,
            local_transform,
            local_params,
            origin_mm=local_origin,
        )
        if decisions:
            decisions[0]["mat_evaluated"] = not broad
            if broad:
                decisions[0]["reason"] = "exceeds_safe_satin_width"
            groups[region.group].append(
                RegionCandidate(
                    region,
                    selected,
                    decisions[0],
                    mask_polygons(local_mask, local_transform, minimum_area=0.001),
                    local_params,
                )
            )

    selected_groups, decisions = [], []
    for group, members in groups.items():
        methods = {m.decision["method"] for m in members}
        method = next(iter(methods)) if len(methods) == 1 else "fill"
        if method == "satin" and len({len(m.elements) for m in members}) > 1:
            method = "fill"
        representative = next((m for m in members if m.decision["method"] == "fill"), members[0])
        angle = _fill_angle(representative.polygons[0], representative.params)
        finish_inset = min(
            (e.get("finish_inset", 0.12) for m in members for e in m.elements), default=0.12
        )
        profile = _assign_policy(members, method, params, angle, finish_inset)
        if not _audit_members(members, method, params, origin, transform, scale) and method in (
            "satin",
            "running",
        ):
            # Grid phase can expose a crowded satin fan on only one counterpart.
            # Retain the strict gate; switch the whole cohort to the safer style.
            method = "fill"
            profile = _assign_policy(members, method, params, angle, finish_inset)
            _audit_members(members, method, params, origin, transform, scale)
        if method == "fill":
            if any("error" in m.metrics for m in members):
                method = "omitted"
                profile = _assign_policy(members, method, params, angle, finish_inset)
            elif any(e.get("finish_inset") == 0 for m in members for e in m.elements):
                for member in members:
                    for element in member.elements:
                        element["finish_inset"] = 0.0
                _audit_members(members, method, params, origin, transform, scale)

        if profile != "none" and any(m.metrics.get("underlay_stitches", 0) == 0 for m in members):
            # An inset may exist but have no support row surviving the minimum
            # length/grid filters. Do not advertise or inconsistently add a
            # phantom foundation on narrow counterparts.
            profile = "none"
            for member in members:
                for element in member.elements:
                    element["underlay"] = False
            _audit_members(members, method, params, origin, transform, scale)

        for member in members:
            region, decision, elements = member.region, member.decision, member.elements
            local_angle = elements[0]["fill_angle_deg"] if method == "fill" else None
            decisions.append(
                {
                    **decision,
                    "component": region.component,
                    "method": method,
                    "reason": "equivalent_region_consensus"
                    if method != decision["method"]
                    else decision["reason"],
                    "individual_method": decision["method"],
                    "equivalence_group": group + 1,
                    "equivalent_regions": len(members),
                    "canonical_fill_angle_deg": local_angle,
                    "fill_angle_deg": region.frame.angle_to_world(local_angle)
                    if local_angle is not None
                    else None,
                    "satin_spacing_mm": params.satin_spacing_mm,
                    "fill_spacing_mm": params.fill_spacing_mm,
                    "pull_compensation_mm": elements[0].get(
                        "compensation", params.pull_compensation_mm
                    )
                    if elements
                    else 0.0,
                    "underlay": profile != "none",
                    "underlay_strategy": profile,
                    "actual_top_metrics": member.metrics,
                }
            )
            if elements:
                selected_groups.append(elements)
    return route_region_groups(selected_groups), sorted(decisions, key=lambda d: d["component"])
