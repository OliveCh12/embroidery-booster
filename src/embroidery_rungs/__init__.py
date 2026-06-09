"""Embroidery Auto Rung Generator.

Public API::

    from embroidery_rungs import generate, GenerationParams

    result = generate("logo.svg", params=GenerationParams(auto_optimize=True))
    print(result.rungs_count, result.coverage)
"""

from .pipeline import generate, GenerationParams, GenerationResult

__all__ = ["generate", "GenerationParams", "GenerationResult"]
__version__ = "0.1.0"
