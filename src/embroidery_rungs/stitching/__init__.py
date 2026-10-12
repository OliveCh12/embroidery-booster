"""Direct embroidery engine; geometric paths and machine planning are separate."""

from .params import StitchParams
from .planner import StitchPlan, build_stitch_plan

__all__ = ["StitchParams", "StitchPlan", "build_stitch_plan"]
