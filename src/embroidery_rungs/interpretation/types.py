"""Immutable interpreted paint in the existing pixel-centred contour frame."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from numbers import Integral, Real

import numpy as np
from numpy.typing import ArrayLike


def _as_tuple(value: object, name: str) -> tuple:
    try:
        return tuple(value)
    except TypeError as exc:
        raise ValueError(f"Raster {name} must be a sequence.") from exc


@dataclass(frozen=True, eq=False)
class RasterArtwork:
    """Categorical paint; labels are already padded and zero means transparent."""

    labels: np.ndarray = field(repr=False)
    palette: tuple[str, ...]
    canvas_size_mm: tuple[float, float]
    source_crop_box_px: tuple[int, int, int, int] | None = None
    _visible_bounds_mm: tuple[float, float, float, float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        labels = np.asarray(self.labels)
        if labels.ndim != 2 or not labels.size or labels.dtype.kind not in "iu":
            raise ValueError("Raster labels must be a nonempty two-dimensional integer array.")
        palette = _as_tuple(self.palette, "palette")
        if not palette or any(
            not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
            for color in palette
        ):
            raise ValueError("Raster palette must contain RGB HEX colours.")
        if len({color.lower() for color in palette}) != len(palette):
            raise ValueError("Raster palette colours must be distinct.")
        if labels.min() < 0 or labels.max() > len(palette):
            raise ValueError("Raster labels must be zero or index an existing palette colour.")
        if not labels.any():
            raise ValueError("Raster artwork contains no visible paint.")
        size = _as_tuple(self.canvas_size_mm, "canvas size")
        if len(size) != 2 or any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            or value <= 0
            for value in size
        ):
            raise ValueError(
                "Raster canvas size must contain two positive finite millimetre values."
            )
        crop = self.source_crop_box_px
        if crop is not None:
            crop = _as_tuple(crop, "crop box")
            if (
                len(crop) != 4
                or any(isinstance(value, bool) or not isinstance(value, Integral) for value in crop)
                or min(crop) < 0
                or crop[2] <= crop[0]
                or crop[3] <= crop[1]
            ):
                raise ValueError("Raster crop box must be ordered nonnegative source pixel bounds.")
            crop = tuple(int(value) for value in crop)
        size = tuple(float(value) for value in size)
        # Bytes backing prevents a caller from re-enabling writes with setflags.
        immutable_labels = np.frombuffer(labels.tobytes(order="C"), dtype=labels.dtype).reshape(
            labels.shape
        )
        object.__setattr__(self, "labels", immutable_labels)
        object.__setattr__(self, "palette", palette)
        object.__setattr__(self, "canvas_size_mm", size)
        object.__setattr__(self, "source_crop_box_px", crop)
        rows = np.flatnonzero(labels.any(axis=1))
        columns = np.flatnonzero(labels.any(axis=0))
        sx, sy = self.pixel_size_mm
        object.__setattr__(
            self,
            "_visible_bounds_mm",
            (
                float((columns[0] - 0.5) * sx),
                float((rows[0] - 0.5) * sy),
                float((columns[-1] + 0.5) * sx),
                float((rows[-1] + 0.5) * sy),
            ),
        )

    @property
    def pixel_size_mm(self) -> tuple[float, float]:
        return (
            self.canvas_size_mm[0] / self.labels.shape[1],
            self.canvas_size_mm[1] / self.labels.shape[0],
        )

    def pixel_to_mm(self, points_xy: ArrayLike) -> np.ndarray:
        """Convert contour coordinates (..., x/y) without shifting pixel centres."""
        points = np.asarray(points_xy)
        if (
            points.ndim == 0
            or points.shape[-1] != 2
            or points.dtype.kind not in "iuf"
            or not np.isfinite(points).all()
        ):
            raise ValueError("Pixel coordinates must be finite numeric x/y pairs.")
        return points * self.pixel_size_mm

    @property
    def visible_bounds_mm(self) -> tuple[float, float, float, float]:
        return self._visible_bounds_mm

    @property
    def visible_size_mm(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.visible_bounds_mm
        return x1 - x0, y1 - y0

    def diagnostics(self) -> dict[str, object]:
        """JSON-ready physical geometry, separate from source/stitch quality."""
        return {
            "canvas_size_mm": list(self.canvas_size_mm),
            "visible_bounds_mm": list(self.visible_bounds_mm),
            "visible_size_mm": list(self.visible_size_mm),
            "pixel_size_mm": list(self.pixel_size_mm),
            "source_crop_box_px": (
                list(self.source_crop_box_px) if self.source_crop_box_px is not None else None
            ),
        }
