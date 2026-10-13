"""Direct embroidery generation from SVG and bitmap artwork.

from embroidery_rungs import GenerationParams, StitchParams, generate

result = generate("logo.svg", params=GenerationParams(fit_to_hoop=True),
                  stitch_params=StitchParams.for_fabric("stable"))
print(result.direct.pes_path)
"""

from .pipeline import GenerationParams, GenerationResult, GenerationVariant, generate
from .stitching.params import StitchParams

__all__ = ["generate", "GenerationParams", "GenerationResult", "GenerationVariant", "StitchParams"]
__version__ = "0.5.1"
