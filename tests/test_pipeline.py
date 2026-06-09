"""Smoke test for the generation pipeline.

Run with ``pytest`` (or ``python -m pytest``). Requires Inkscape or the PIL
rasterization fallback, plus the package installed (``pip install -e .``).
"""

import os

from embroidery_rungs import generate, GenerationParams, GenerationResult

EXAMPLE = os.path.join(os.path.dirname(__file__), os.pardir, "examples", "shapes.svg")


def test_generate_produces_rungs(tmp_path):
    result = generate(EXAMPLE, output_dir=str(tmp_path),
                      params=GenerationParams(debug=False))

    assert isinstance(result, GenerationResult)
    assert result.rungs_count > 0
    assert result.columns_count > 0
    assert 0.0 <= result.coverage <= 1.0
    for path in (result.original_path, result.rungs_path,
                 result.ready_path, result.satin_path):
        assert os.path.isfile(path), f"expected output file: {path}"


def test_missing_file_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        generate("does-not-exist.svg")
