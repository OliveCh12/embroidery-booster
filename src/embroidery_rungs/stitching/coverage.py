"""Audit exported stitches and repair significant blanks inside the source silhouette."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, find_objects, label
from shapely.ops import unary_union
from skimage.morphology import skeletonize
from svgelements import Matrix

from ..geometry_utils import get_skeleton_paths
from ..svg_manager import UNITS_PER_MM
from .planner import build_stitch_plan
from .quality import measure_stitches
from .selection import mask_polygons


def _repair_elements(patch, transform, scale, params):
    components, _ = label(patch)
    elements = []
    for i, bounds in enumerate(find_objects(components)):
        component = np.pad(components[bounds] == i + 1, 1)
        local = transform * Matrix.translate(1 - bounds[1].start, 1 - bounds[0].start)
        if distance_transform_edt(component).max() / scale <= 0.3:
            paths = get_skeleton_paths(
                skeletonize(component), min_len_px=max(1.0, params.min_stitch_mm * scale)
            )
            inverse = ~local
            matrix = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]])
            area = unary_union(mask_polygons(component, local, minimum_area=0)).buffer(0.15)
            for path in paths:
                points = (path["points"][:, ::-1] @ matrix + [inverse.e, inverse.f]) / UNITS_PER_MM
                elements.append({"type": "running", "points": points, "allowed_area": area})
        else:
            for polygon in mask_polygons(component, local):
                rectangle = np.asarray(polygon.minimum_rotated_rectangle.exterior.coords)
                sides = np.diff(rectangle, axis=0)
                direction = sides[np.argmax(np.linalg.norm(sides, axis=1))]
                elements.append(
                    {
                        "type": "fill",
                        "polygon": polygon,
                        "fill_angle_deg": (
                            float(np.degrees(np.arctan2(direction[1], direction[0])))
                            if params.auto_fill_angle
                            else params.fill_angle_deg
                        ),
                        "gap_fill": True,
                        "compensation": 0.0,
                        "underlay": False,
                    }
                )
    return elements


def audit_coverage(plan, elements, mask, transform, params):
    scale = UNITS_PER_MM * np.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    offset = np.array([transform.e, transform.f])

    def measure(candidate):
        return measure_stitches(candidate.commands, candidate.origin_mm, mask, scale, offset)

    metrics, image = measure(plan)
    repaired_regions = 0
    for _ in range(2 if params.auto_select and params.fill_gaps else 0):
        footprint = np.asarray(image, dtype=bool)
        distance = distance_transform_edt(~footprint) / scale
        core = mask & (distance > max(0.25, params.fill_spacing_mm / 2))
        components, count = label(core)
        sizes = np.bincount(components.ravel())
        significant = np.flatnonzero(sizes[1:] / scale**2 >= 0.05) + 1
        if count and len(significant):
            core = np.isin(components, significant)
            # Cover the blank plus a small seam overlap, clipped to the source.
            patch = mask & (distance_transform_edt(~core) / scale <= 0.3)
            repairs = _repair_elements(patch, transform, scale, params)
            if repairs:
                try:
                    candidate = build_stitch_plan(repairs + elements, params)
                except ValueError as exc:
                    plan.warnings.append(f"Coverage repair could not be applied: {exc}")
                    break
                repaired, repaired_image = measure(candidate)
                if repaired["structural_missing_mm2"] < metrics["structural_missing_mm2"]:
                    plan, metrics, image = candidate, repaired, repaired_image
                    repaired_regions += len(
                        {b.region for b in candidate.blocks if b.region < len(repairs)}
                    )
                    elements = repairs + elements
                else:
                    break
            else:
                break
        else:
            break
    plan.stats.update(
        coverage=metrics["coverage"],
        structural_coverage=metrics["structural_coverage"],
        structural_missing_mm2=metrics["structural_missing_mm2"],
        largest_gap_mm2=metrics["largest_gap_mm2"],
        uncovered_max_mm=metrics["uncovered_max_mm"],
        coverage_repairs=repaired_regions,
        coverage_pixels_per_mm=round(float(scale), 3),
    )
    if metrics["largest_gap_mm2"] >= 0.1 or metrics["structural_coverage"] < 0.999:
        plan.warnings.append(
            f"Stitch coverage leaves a blank of {metrics['largest_gap_mm2']:.2f} mm² "
            "inside the artwork. Inspect the preview or enlarge the design."
        )
    return plan
