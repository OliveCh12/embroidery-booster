"""Direct embroidery generation from SVG and bitmap artwork.

from embroidery_rungs import GenerationParams, StitchParams, generate

result = generate("logo.svg", params=GenerationParams(fit_to_hoop=True),
                  stitch_params=StitchParams.for_fabric("stable"))
print(result.direct.pes_path)
"""

from .pipeline import GenerationParams, GenerationResult, generate
from .stitching.params import StitchParams

__all__ = ["generate", "GenerationParams", "GenerationResult", "StitchParams"]
__version__ = "0.4.0"
