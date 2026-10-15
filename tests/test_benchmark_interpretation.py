"""The public benchmark must detect bad outputs independently of engine audits."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RUNNER = SCRIPTS / "benchmark_interpretation.py"
SPEC = importlib.util.spec_from_file_location(
    "public_corpus_test_helpers", SCRIPTS / "benchmark_public_corpus.py"
)
PUBLIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC)


def rgba(mask, color=(23, 23, 23)):
    result = np.zeros((*mask.shape, 4), np.uint8)
    result[mask] = [*color, 255]
    return result


def test_public_corpus_is_reproducible_with_explicit_intent(tmp_path):
    manifests = []
    for name in ("a", "b"):
        manifests.append(json.loads(PUBLIC.public_corpus(tmp_path / name).read_text()))
    assert manifests[0] == manifests[1]
    cases = {case["name"]: case for case in manifests[0]}
    assert len(cases) == 42
    assert {"glyph-g-jpeg35", "glyph-g-jpeg75", "glyph-g-jpeg95"} <= cases.keys()
    assert cases["protected-white-badge-svg"]["oracle"]["palette"] == [
        "#171717",
        "#182c9b",
        "#e3202a",
        "#ffffff",
    ]
    assert cases["regions-4096"]["expected_regions"] == 4096
    assert cases["regions-4097"]["expected_error"] == "4096"
    assert cases["gradient-only"]["oracle"]["silhouette_only"]
    assert cases["textured-five-paints-png"]["width_mm"] == 80
    assert len(cases["textured-five-paints-png"]["oracle"]["palette"]) == 5


def test_spatial_oracle_detects_missing_outer_accent_without_recropping():
    target = np.zeros((30, 40), bool)
    target[10:20, 5:20] = True
    target[10:14, 32:36] = True
    actual = target.copy()
    actual[:, 30:] = False
    scores = PUBLIC.source_scores(rgba(target), rgba(actual), ["#171717"])
    assert scores["silhouette"]["source_components"] == 2
    assert scores["silhouette"]["components_recalled"] == 1
    assert scores["silhouette"]["missing_core_pixels"] == 4


def test_equal_counter_counts_cannot_hide_a_moved_hole():
    target = np.zeros((30, 40), bool)
    target[2:28, 2:38] = True
    target[7:13, 7:13] = False
    actual = np.zeros_like(target)
    actual[2:28, 2:38] = True
    actual[17:23, 27:33] = False
    scores = PUBLIC.source_scores(rgba(target), rgba(actual), ["#171717"])
    assert scores["silhouette"]["source_holes"] == 1
    assert scores["silhouette"]["holes_preserved"] == 0
    assert scores["silhouette"]["extra_core_pixels"] > 0


def test_nearest_wrong_colour_is_rejected():
    target = np.ones((10, 10), bool)
    scores = PUBLIC.source_scores(rgba(target), rgba(target, (210, 20, 20)), ["#171717"])
    assert scores["paint"]["#171717"]["iou"] == 0
    assert scores["unmatched_colour_pixels"] == 100


def test_counter_open_to_exterior_diagonally_is_not_a_hole():
    mask = np.zeros((8, 8), bool)
    mask[1:7, 1:7] = True
    mask[1, 1] = mask[2, 2] = mask[3, 3] = False
    scores = PUBLIC.source_scores(rgba(mask), rgba(mask), ["#171717"])
    assert scores["silhouette"]["source_holes"] == 0


def test_trace_oracle_uses_integer_pixel_centres_without_moving_output(tmp_path):
    target = np.zeros((12, 12), bool)
    target[6, 6] = True
    source = tmp_path / "reference.png"
    Image.fromarray(rgba(target)).save(source)
    svg = tmp_path / "actual.svg"
    text = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14mm" height="14mm" '
        'viewBox="0 0 14 14" shape-rendering="crispEdges">'
        '<path fill="#171717" d="M7 6.5L7.5 7L7 7.5L6.5 7Z"/></svg>'
    )
    svg.write_text(text)
    assert not PUBLIC.render_svg(svg, (14, 14))[..., 3].any()
    scores = PUBLIC.source_oracle(
        source,
        svg,
        {"source_crop_box_px": [0, 0, 12, 12]},
        {"sample_shape": [12, 12], "trim_offset": [0, 0], "labels_shape": [14, 14]},
        tmp_path,
        palette=["#171717"],
    )
    assert scores["silhouette"]["iou"] == 1
    assert svg.read_text() == text


@pytest.fixture
def isolated_case(tmp_path):
    root = tmp_path / "engine" / "src"
    package = root / "embroidery_rungs"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "class GenerationParams:\n def __init__(self, **kwargs): pass\n"
        "class StitchParams:\n @classmethod\n def for_fabric(cls, *args, **kwargs): return cls()\n"
        'def generate(*args, **kwargs): raise AssertionError("not a machine fixture")\n'
    )
    (package / "inputs.py").write_text(
        "def raster_to_svg(source, destination, **kwargs):\n"
        ' destination.write_text(\'<svg xmlns="http://www.w3.org/2000/svg" width="4mm" height="4mm" viewBox="0 0 4 4"><path fill="#171717" d="M0 0H4V4H0Z"/></svg>\')\n'
        " return str(destination)\n"
    )
    image = tmp_path / "input.png"
    Image.new("RGBA", (4, 4), "black").save(image)
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "name": "isolated",
                    "path": image.name,
                    "width_mm": 4,
                    "background": "keep",
                    "cleanup": True,
                }
            ]
        )
    )
    return root, corpus


def run_case(tmp_path, isolated_case, *flags):
    root, corpus = isolated_case
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--source-root",
            str(root),
            "--corpus",
            str(corpus),
            "--output",
            str(tmp_path / "output"),
            *flags,
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_subprocess_imports_snapshot_and_reports_absent_hooks(tmp_path, isolated_case):
    result = run_case(tmp_path, isolated_case)
    assert result.returncode == 0, result.stderr
    row = json.loads((tmp_path / "output" / "summary.json").read_text())[0]
    assert row["imported_engine"] == "embroidery_rungs/inputs.py"
    assert all(
        capability == {"available": False, "calls": 0}
        for capability in row["capabilities"].values()
    )
    assert row["record"] == {}
    assert row["expected_outcome"]["passed"]


def test_historical_inline_sampling_has_an_observed_source_mapping(tmp_path, isolated_case):
    import hashlib

    root, corpus = isolated_case
    image = tmp_path / "input.png"
    mask = np.zeros((12, 12), bool)
    mask[4:8, 4:8] = True
    Image.fromarray(rgba(mask)).save(image)
    cases = json.loads(corpus.read_text())
    cases[0]["oracle"] = {
        "path": image.name,
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "palette": ["#171717"],
    }
    corpus.write_text(json.dumps(cases))
    (root / "embroidery_rungs" / "inputs.py").write_text(
        "import numpy as np\nfrom PIL import Image\n"
        "def bitmap_foreground(rgba): return rgba\n"
        'def bitmap_colors(rgba): return (rgba[...,3]>=128).astype(np.uint8), ["#171717"], False\n'
        "def raster_to_svg(source, destination, **kwargs):\n"
        ' rgba=bitmap_foreground(np.asarray(Image.open(source).convert("RGBA")))\n'
        " y,x=np.nonzero(rgba[...,3]>=128)\n"
        " labels,_,_=bitmap_colors(rgba[y.min():y.max()+1,x.min():x.max()+1])\n"
        ' destination.write_text(\'<svg xmlns="http://www.w3.org/2000/svg" width="6mm" height="6mm" viewBox="0 0 6 6" shape-rendering="crispEdges"><path fill="#171717" d="M.5 .5H4.5V4.5H.5Z"/></svg>\')\n'
        " return str(destination)\n"
    )
    result = run_case(tmp_path, isolated_case, "--check")
    assert result.returncode == 0, result.stderr
    row = json.loads((tmp_path / "output" / "summary.json").read_text())[0]
    assert not row["capabilities"]["sample_bitmap"]["available"]
    assert not row["capabilities"]["serialize_bitmap"]["available"]
    assert row["source_mapping"]["source_crop_box_px"] == [4, 4, 8, 8]
    assert row["source_oracle"]["silhouette"]["iou"] == 1


def test_check_exits_nonzero_for_unexpected_success(tmp_path, isolated_case):
    _, corpus = isolated_case
    cases = json.loads(corpus.read_text())
    cases[0]["expected_error"] = "fixture must fail"
    corpus.write_text(json.dumps(cases))
    result = run_case(tmp_path, isolated_case, "--check")
    assert result.returncode == 1, result.stderr
    row = json.loads((tmp_path / "output" / "summary.json").read_text())[0]
    assert row["failed_checks"] == ["unexpected_outcome"]


def test_expected_error_has_no_vacuous_determinism_claim(tmp_path, isolated_case):
    root, corpus = isolated_case
    (root / "embroidery_rungs" / "inputs.py").write_text(
        'def raster_to_svg(*args, **kwargs): raise ValueError("expected fixture error")\n'
    )
    cases = json.loads(corpus.read_text())
    cases[0]["expected_error"] = "fixture error"
    corpus.write_text(json.dumps(cases))
    result = run_case(tmp_path, isolated_case, "--check")
    assert result.returncode == 0, result.stderr
    row = json.loads((tmp_path / "output" / "summary.json").read_text())[0]
    assert row["deterministic"] is None
    assert row["output_signatures"] == []
    assert row["failed_checks"] == []


def test_hard_checks_do_not_claim_semantic_iou_is_a_machine_gate():
    spec = importlib.util.spec_from_file_location("interpretation_runner_checks", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = {
        "expected_outcome": {"passed": True},
        "deterministic": True,
        "machine": {"safety_checks": {"machine_roundtrip": False, "within_hoop": True}},
        "source_oracle": {"silhouette": {"iou": 0.1}},
    }
    assert module.report_failures(report) == ["machine_roundtrip"]
    report["machine"]["safety_checks"]["machine_roundtrip"] = True
    assert module.report_failures(report) == []


def test_warmup_count_and_repeat_determinism_on_fake_engine(tmp_path, isolated_case):
    result = run_case(
        tmp_path,
        isolated_case,
        "--mode",
        "performance",
        "--warmups",
        "2",
        "--repeats",
        "3",
    )
    assert result.returncode == 0, result.stderr
    row = json.loads((tmp_path / "output" / "summary.json").read_text())[0]
    assert row["warmup_runs"] == 2
    assert len(row["samples"]) == 3
    assert len(row["output_signatures"]) == 5
    assert row["deterministic"]
    assert "svg_reference" not in row


def test_snapshot_comparison_filters_same_cases(tmp_path, isolated_case):
    root, _ = isolated_case
    result = run_case(
        tmp_path, isolated_case, "--snapshot", "baseline=" + str(root), "--names", "isolated"
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "output" / "comparison.json").read_text())
    assert set(report["revisions"]) == {"baseline", "current"}
    assert [row["case"] for row in report["cases"]] == ["isolated"]
    assert all(phase["source_equal_to_current"] for phase in report["cases"][0]["phases"].values())


def test_top_needle_audit_excludes_context_underlay_and_jump(tmp_path):
    mask = np.ones((20, 20), bool)
    reference = tmp_path / "reference.png"
    Image.fromarray(rgba(mask)).save(reference)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "commands": [[0, 0, 0], [0, 0, 1], [0, 0, 0], [0, 0, 0], [2, 0, 0]],
                "command_codes": {"stitch": 0, "command_mask": 255},
                "top_layer_runs": [{"start": 1, "end": 5, "color_index": 0}],
                "threads": ["#171717"],
            }
        )
    )
    scores = PUBLIC.machine_source_oracle(
        SimpleNamespace(plan_path=plan),
        reference,
        {"pixels_per_mm": 8, "bounds_px": [0, 0, 20, 20], "palette": ["#171717"]},
        tmp_path,
    )
    repeats = scores["repeated_needles"]
    assert repeats["top_cycles"] == 3
    assert repeats["peak_all_top"] == 2
    assert repeats["repeats_same_position_and_colour"] == 1
