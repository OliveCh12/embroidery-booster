"""Physical stitch settings and editable material presets."""

from __future__ import annotations

import math
from dataclasses import dataclass

MACHINE_PROFILES = {
    "generic": {
        "label": "Cadre personnalisable",
        "hoop_width": 100.0,
        "hoop_height": 100.0,
        "max_colors": 12,
        "max_satin_width": 8.0,
        "max_area_mm": None,
    },
    "brother-skitch-pp1": {
        "label": "Brother Skitch PP1 · 100 × 100 mm",
        "hoop_width": 100.0,
        "hoop_height": 100.0,
        # Fewer spools and shorter satin floats are conservative starting points,
        # not undocumented hardware limits; explicit overrides remain available.
        "max_colors": 6,
        "max_satin_width": 7.0,
        "max_area_mm": 100.0,
    },
}


@dataclass
class StitchParams:
    satin_spacing_mm: float = 0.4
    running_length_mm: float = 2.5
    fill_spacing_mm: float = 0.4
    fill_length_mm: float = 4.0
    fill_angle_deg: float = 45.0
    max_stitch_mm: float = 8.0
    min_stitch_mm: float = 0.25
    pull_compensation_mm: float = 0.15
    underlay: bool = True
    trim_distance_mm: float = 3.0
    wide_mode: str = "fill"
    fill_gaps: bool = True
    max_satin_width_mm: float = 8.0
    hoop_width_mm: float = 100.0
    hoop_height_mm: float = 100.0
    thread_color: str = "#176d9c"
    max_stitches: int = 500_000
    auto_select: bool = True
    auto_fill_angle: bool = True
    fabric: str = "custom"
    thread_weight: int = 40
    stabilizer: str = "unspecified"
    max_colors: int = 12
    preserve_colors: bool = True
    machine: str = "generic"

    @classmethod
    def for_fabric(
        cls,
        fabric: str = "custom",
        *,
        thread_weight=40,
        stabilizer="unspecified",
        machine="generic",
        **overrides,
    ):
        """Material starting points; explicit settings always take precedence."""
        presets = {
            "custom": {},
            "stable": {
                "satin_spacing_mm": 0.4,
                "fill_spacing_mm": 0.4,
                "pull_compensation_mm": 0.15,
            },
            "stretch": {
                "satin_spacing_mm": 0.45,
                "fill_spacing_mm": 0.45,
                "pull_compensation_mm": 0.25,
                "underlay": True,
            },
            "textured": {
                "satin_spacing_mm": 0.35,
                "fill_spacing_mm": 0.35,
                "pull_compensation_mm": 0.2,
                "underlay": True,
            },
        }
        if fabric not in presets:
            raise ValueError("fabric must be 'custom', 'stable', 'stretch' or 'textured'.")
        if thread_weight not in (30, 40, 60):
            raise ValueError("thread_weight must be 30, 40 or 60.")
        if machine not in MACHINE_PROFILES:
            raise ValueError("Unknown machine profile.")
        profile = MACHINE_PROFILES[machine]
        values = {
            "hoop_width_mm": profile["hoop_width"],
            "hoop_height_mm": profile["hoop_height"],
            "max_colors": profile["max_colors"],
            "max_satin_width_mm": profile["max_satin_width"],
            **presets[fabric],
        }
        factor = {30: 1.25, 40: 1.0, 60: 0.75}[thread_weight]
        for name in ("satin_spacing_mm", "fill_spacing_mm"):
            values[name] = round(values.get(name, 0.4) * factor, 3)
        return cls(
            fabric=fabric,
            thread_weight=thread_weight,
            stabilizer=stabilizer,
            machine=machine,
            **(values | overrides),
        )

    def validate(self) -> None:
        if self.machine not in MACHINE_PROFILES:
            raise ValueError("Unknown machine profile.")
        if (
            isinstance(self.max_colors, bool)
            or not isinstance(self.max_colors, int)
            or not 1 <= self.max_colors <= 32
        ):
            raise ValueError("max_colors must be an integer between 1 and 32.")
        bounds = {
            "satin_spacing_mm": (0.2, 1.2),
            "running_length_mm": (0.5, 5.0),
            "fill_spacing_mm": (0.2, 1.2),
            "fill_length_mm": (1.0, 6.0),
            "max_stitch_mm": (2.0, 12.0),
            "min_stitch_mm": (0.1, 0.5),
            "pull_compensation_mm": (0.0, 0.5),
            "trim_distance_mm": (0.0, 10.0),
            "max_satin_width_mm": (2.0, 12.0),
            "hoop_width_mm": (10.0, 500.0),
            "hoop_height_mm": (10.0, 500.0),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"{name} must be between {low} and {high} mm.")
        limit = MACHINE_PROFILES[self.machine]["max_area_mm"]
        if limit is not None and max(self.hoop_width_mm, self.hoop_height_mm) > limit:
            raise ValueError("Brother Skitch PP1 supports a maximum 100 × 100 mm embroidery area.")
        if (
            not isinstance(self.fill_angle_deg, (int, float))
            or not math.isfinite(self.fill_angle_deg)
            or not -180 <= self.fill_angle_deg <= 180
        ):
            raise ValueError("fill_angle_deg must be between -180 and 180 degrees.")
        if self.wide_mode not in ("fill", "split"):
            raise ValueError("wide_mode must be 'fill' or 'split'.")
        if not all(
            isinstance(v, bool)
            for v in (
                self.underlay,
                self.fill_gaps,
                self.auto_select,
                self.auto_fill_angle,
                self.preserve_colors,
            )
        ):
            raise ValueError("underlay, fill_gaps and auto_select must be booleans.")
        if self.fabric not in ("custom", "stable", "stretch", "textured"):
            raise ValueError("Unknown fabric preset.")
        if self.thread_weight not in (30, 40, 60) or isinstance(self.thread_weight, bool):
            raise ValueError("thread_weight must be 30, 40 or 60.")
        if self.stabilizer not in ("unspecified", "cutaway", "tearaway", "washaway"):
            raise ValueError("Unknown stabilizer.")
        if not isinstance(self.max_stitches, int) or not 100 <= self.max_stitches <= 1_000_000:
            raise ValueError("max_stitches must be between 100 and 1000000.")
        import re

        if not isinstance(self.thread_color, str) or not re.fullmatch(
            r"#[0-9a-fA-F]{6}", self.thread_color
        ):
            raise ValueError("thread_color must be a six-digit hex color.")
