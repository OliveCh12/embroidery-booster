"""Embroidery Auto Rung Generator.

Public API::

    from embroidery_rungs import generate, GenerationParams

    result = generate("logo.svg", params=GenerationParams(auto_optimize=True))
    print(result.rungs_count, result.coverage)
"""

from .pipeline import GenerationParams, GenerationResult, generate
from .stitching.params import StitchParams

__all__ = ["generate", "GenerationParams", "GenerationResult", "StitchParams"]
__version__ = "0.3.0"
