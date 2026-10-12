"""Local component frames: rigid equivalents share decisions, never altered outlines."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt, find_objects, label
from shapely.affinity import affine_transform

from ..svg_manager import UNITS_PER_MM


def orientations(mask):
    rotation = np.array([[0, -1], [1, 0]])
    for turns in range(4):
        matrix = np.linalg.matrix_power(rotation, turns)
        rotated = np.rot90(mask, turns)
        yield rotated, matrix
        yield np.fliplr(rotated), matrix @ np.diag([-1, 1])


def design_symmetries(labels):
    """Allow raster edge noise, without imposing mirrors on an asymmetric flag."""
    result = []
    for transformed, matrix in orientations(labels):
        if np.array_equal(matrix, np.eye(2)) or transformed.shape != labels.shape:
            continue
        if np.count_nonzero(labels != transformed) <= 0.02 * np.count_nonzero(labels):
            result.append(matrix)
    return result


@dataclass(frozen=True)
class RegionFrame:
    matrix: np.ndarray
    offset: np.ndarray

    def to_world(self, points):
        return np.asarray(points) @ self.matrix + self.offset

    def to_local(self, points):
        return (np.asarray(points) - self.offset) @ self.matrix.T

    def geometry_to_world(self, geometry):
        a, b = self.matrix[0]
        c, d = self.matrix[1]
        return affine_transform(geometry, [a, c, b, d, *self.offset])

    def angle_to_world(self, angle):
        radians = math.radians(angle)
        vector = np.array([math.cos(radians), math.sin(radians)]) @ self.matrix
        return round(math.degrees(math.atan2(vector[1], vector[0])) % 180, 6)

    def angle_to_local(self, angle):
        radians = math.radians(angle)
        vector = np.array([math.cos(radians), math.sin(radians)]) @ self.matrix.T
        return math.degrees(math.atan2(vector[1], vector[0])) % 180


@dataclass
class Region:
    component: int
    group: int
    mask: np.ndarray
    source_mask: np.ndarray
    bounds: tuple[slice, slice]
    frame: RegionFrame


def _mask_key(mask):
    return mask.shape, np.packbits(mask).tobytes()


def _equivalence_cost(a, b):
    if max(abs(x - y) for x, y in zip(a.shape, b.shape, strict=True)) > 2:
        return None
    if abs(int(a.sum()) - int(b.sum())) > 0.03 * max(a.sum(), b.sum()):
        return None
    shape = np.maximum(a.shape, b.shape) + 4
    padded = []
    for mask in (a, b):
        canvas = np.zeros(shape, dtype=bool)
        start = (shape - mask.shape) // 2
        canvas[start[0] : start[0] + mask.shape[0], start[1] : start[1] + mask.shape[1]] = mask
        padded.append(canvas)
    left, right = padded
    # Similar area alone could confuse a counter or a fork with a solid column.
    # Four-connected foreground needs the dual eight-connected background;
    # otherwise a diagonal open channel can be mistaken for a closed counter.
    background = np.ones((3, 3), dtype=bool)
    if label(~left, background)[1] != label(~right, background)[1]:
        return None
    left_distance = None
    best = None
    # Odd/even raster bounds put otherwise equivalent centres half a pixel
    # apart. Compare nearby integer alignments before rejecting the outline;
    # the accepted area/topology/boundary tolerances themselves stay unchanged.
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            shifted = np.roll(right, (dr, dc), axis=(0, 1))
            mismatch = np.count_nonzero(left != shifted) / np.count_nonzero(left | shifted)
            if mismatch > 0.06 or (best is not None and mismatch >= best):
                continue
            if left_distance is None:
                left_distance = distance_transform_edt(~left)
            if left_distance[shifted & ~left].max(initial=0) > 2:
                continue
            if distance_transform_edt(~shifted)[left & ~shifted].max(initial=0) <= 2:
                best = mismatch
    return best


def canonical_regions(mask, transform, symmetries=()):
    """Canonicalize four-connected regions under rotations/reflections/translation.

    Approximate matches permit at most two raster pixels of boundary discrepancy,
    3% area difference and 6% disagreement, with identical hole topology. Only
    strategy is shared; every member keeps its own source geometry and is audited.
    """
    labels, _ = label(mask)
    inverse = ~transform
    world = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) / UNITS_PER_MM
    translation = np.array([inverse.e, inverse.f]) / UNITS_PER_MM
    scale = UNITS_PER_MM * math.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    design_center = (np.asarray(mask.shape)[::-1] - 1) / 2
    groups, exact, regions = [], {}, []
    for component, bounds in enumerate(find_objects(labels), 1):
        if bounds is None:
            continue
        source = labels[bounds] == component
        center = np.array(
            [(bounds[1].start + bounds[1].stop - 1) / 2, (bounds[0].start + bounds[0].stop - 1) / 2]
        )
        variants = list(orientations(source))
        canonical, orientation = min(variants, key=lambda pair: _mask_key(pair[0]))
        key = _mask_key(canonical)
        group = exact.get(key)
        if group is None:
            best = (float("inf"), float("inf"))
            for group_index, (reference, ref_center, ref_orientation) in enumerate(groups):
                for variant, matrix in variants:
                    cost = _equivalence_cost(reference, variant)
                    if cost is None:
                        continue
                    symmetry_match = any(
                        np.linalg.norm(
                            (ref_center - design_center) @ symmetry + design_center - center
                        )
                        <= 2
                        and np.array_equal(matrix, symmetry.T @ ref_orientation)
                        for symmetry in symmetries
                    )
                    score = (0 if symmetry_match else 1, cost)
                    if score < best:
                        best, group, canonical, orientation = score, group_index, variant, matrix
            if group is None:
                group = len(groups)
                groups.append((canonical.copy(), center, orientation))
            if _mask_key(canonical) == _mask_key(groups[group][0]):
                exact[key] = group
        else:
            reference, ref_center, ref_orientation = groups[group]
            for variant, matrix in variants:
                if _mask_key(variant) != _mask_key(reference):
                    continue
                if any(
                    np.linalg.norm((ref_center - design_center) @ symmetry + design_center - center)
                    <= 2
                    and np.array_equal(matrix, symmetry.T @ ref_orientation)
                    for symmetry in symmetries
                ):
                    canonical, orientation = variant, matrix
                    break
        matrix = scale * orientation.T @ world
        local_center = (np.asarray(canonical.shape)[::-1] - 1) / (2 * scale)
        frame = RegionFrame(matrix, center @ world + translation - local_center @ matrix)
        regions.append(
            Region(component, group, np.ascontiguousarray(canonical), source, bounds, frame)
        )
    return regions


def route_region_groups(groups):
    """Move whole regions; never reverse their internal satin phase or foundations."""
    if len(groups) < 2:
        return [element for group in groups for element in group]
    endpoints = []
    for group in groups:
        first, last = group[0], group[-1]

        def endpoint(element, start):
            if element["type"] == "fill":
                point = np.asarray(element["polygon"].representative_point().coords)[0]
            else:
                points = element.get("points")
                if points is None:
                    points = (element["rail_a"] + element["rail_b"]) / 2
                point = points[0 if start else -1]
            return element["frame"].to_world(point)

        endpoints.append((endpoint(first, True), endpoint(last, False)))
    endpoints = np.asarray(endpoints)
    visited = np.zeros(len(groups), dtype=bool)
    index = int(np.argmin(endpoints[:, 0].sum(axis=1)))
    result = []
    for _ in groups:
        visited[index] = True
        result.extend(groups[index])
        distances = np.linalg.norm(endpoints[:, 0] - endpoints[index, 1], axis=1)
        distances[visited] = np.inf
        index = int(np.argmin(distances))
    return result


def physical_elements(elements, transform):
    inverse = ~transform
    matrix = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) / UNITS_PER_MM
    offset = np.array([inverse.e, inverse.f]) / UNITS_PER_MM
    return [
        {
            "type": e["type"],
            **{
                key: np.asarray(e[key]) @ matrix + offset
                for key in ("points", "rail_a", "rail_b")
                if key in e
            },
        }
        for e in elements
    ]
