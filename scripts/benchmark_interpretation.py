"""Benchmark interpretation, optional machine exports and known source intent.

The corpus is JSON with name, path (relative to corpus), width_mm, background,
cleanup and optional source_sha256. Quality mode saves independent colour-label
measurements; performance mode keeps these measurements outside the timed path.
Use --suite public for 42 generated SVG/PNG/JPEG cases. --input may append private
samples to that suite; no semantic source oracle is invented for user images.
--machine audits the library's balanced policy and PES/DST roundtrips. Run
performance mode alone after freezing sources and stopping other tests/builds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def harness_signature():
    directory = Path(__file__).resolve().parent
    hashes = {
        name: digest(directory / name)
        for name in (
            "benchmark_interpretation.py",
            "benchmark_public_corpus.py",
            "benchmark_fill_methods.py",
            "benchmark_reliability.py",
            "benchmark_variants.py",
        )
    }
    fixture = directory.parent / "examples/quality/textured-five-paints.py"
    if fixture.is_file():
        hashes["examples/quality/textured-five-paints.py"] = digest(fixture)
    return hashes


def report_failures(report):
    failures = []
    if not report["expected_outcome"]["passed"]:
        failures.append("unexpected_outcome")
    if report["expected_outcome"].get("trace_budget_boundary_passed") is False:
        failures.append("trace_budget_boundary")
    if report.get("deterministic") is False:
        failures.append("nondeterministic_output")
    failures.extend(
        key
        for key, passed in report.get("machine", {}).get("safety_checks", {}).items()
        if not passed
    )
    return failures


def source_manifest(root, commit=None):
    files = {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    manifest = {
        "commit": commit,
        "source_tree_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "files": files,
        "pyproject_sha256": digest(root.parent / "pyproject.toml")
        if (root.parent / "pyproject.toml").is_file()
        else None,
    }
    save(root.parent / "manifest.json", manifest)
    return manifest


def validate_corpus(cases):
    names = set()
    for case in cases:
        name = case.get("name")
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\0" in name
        ):
            raise ValueError("Corpus case names must be single nonempty basenames")
        if name in names:
            raise ValueError("Corpus case names must be unique: " + name)
        names.add(name)
    if not names:
        raise ValueError("Corpus must contain at least one case")


def topology(mask):
    import numpy as np
    from scipy.ndimage import binary_fill_holes, label

    components, count = label(mask)
    holes = binary_fill_holes(mask, structure=np.ones((3, 3), bool)) & ~mask
    hole_labels, hole_count = label(holes, structure=np.ones((3, 3), bool))
    return {
        "pixels": int(mask.sum()),
        "components": int(count),
        "holes": int(hole_count),
        "component_areas": sorted(map(int, np.bincount(components.ravel())[1:]), reverse=True),
        "hole_areas": sorted(map(int, np.bincount(hole_labels.ravel())[1:]), reverse=True),
    }


def svg_metrics(path):
    """Render final XML independently at its native viewBox grid, outside timings."""
    import io

    import numpy as np
    import resvg_py
    from PIL import Image
    from scipy.spatial import cKDTree

    root = ET.parse(path).getroot()
    box = [float(value) for value in root.attrib["viewBox"].split()]
    width, height = max(1, round(box[2])), max(1, round(box[3]))
    palette = sorted(
        {
            node.attrib[attribute].lower()
            for node in root.iter()
            for attribute in ("fill", "stroke")
            if node.attrib.get(attribute, "").startswith("#")
        }
    )
    canvas = [float(root.attrib[name][:-2]) for name in ["width", "height"]]
    # Decimal mm serialization can round the intrinsic aspect ratio down by one
    # row. Use the exact native grid for this categorical geometry measurement.
    root.set("width", str(width) + "px")
    root.set("height", str(height) + "px")
    png = resvg_py.svg_to_bytes(
        svg_string=ET.tostring(root, encoding="unicode"), dpi=96, skip_system_fonts=True
    )
    rgba = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))
    if rgba.shape[:2] != (height, width):
        raise ValueError("Independent renderer returned a different grid")
    labels = np.zeros(rgba.shape[:2], np.uint16)
    visible = rgba[..., 3] >= 128
    if palette and visible.any():
        rgb = [[int(paint[index : index + 2], 16) for index in [1, 3, 5]] for paint in palette]
        labels[visible] = cKDTree(rgb).query(rgba[visible, :3])[1] + 1
    np.savez_compressed(
        path.parent / "svg-labels.npz",
        labels=labels,
        palette=np.asarray(palette),
        canvas_size_mm=np.asarray(canvas),
    )
    return {
        "size_px": [rgba.shape[1], rgba.shape[0]],
        "canvas_size_mm": canvas,
        "palette": palette,
        "mask_sha256": hashlib.sha256(labels.astype("<u2").tobytes()).hexdigest(),
        "alpha": topology(visible),
        "paint": {paint: topology(labels == index + 1) for index, paint in enumerate(palette)},
        "method": "Independent resvg at native viewBox grid; alpha>=128, nearest literal RGB paint. Rendered vector fidelity, not source topology or sewout.",
    }


def generated_corpus(output, local_inputs, width_mm):
    """Small deterministic raster fixture set; no personal samples are required."""
    import shutil

    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    directory = output / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []

    def add(name, image, filename=None, width=20):
        path = directory / (filename or name + ".png")
        if image is not None:
            image.save(path)
        cases.append(
            {
                "name": name,
                "path": str(path.relative_to(output)),
                "width_mm": width,
                "background": "keep",
                "cleanup": True,
                "source_sha256": digest(path),
            }
        )

    if not local_inputs:
        body = Image.new("RGBA", (960, 240), "#ee2020")
        draw = ImageDraw.Draw(body)
        draw.rectangle((720, 0, 959, 239), fill="#2020ee")
        add("literal-flat", body)
        high = body.resize((3840, 960), Image.Resampling.NEAREST)
        ImageDraw.Draw(high).ellipse((1512, 312, 1608, 408), fill="#872087")
        aa = high.resize(body.size, Image.Resampling.LANCZOS)
        add("antialiased-accent", aa)
        jpeg = directory / "jpeg-accent.jpg"
        aa.convert("RGB").save(jpeg, quality=75, subsampling=2)
        add("jpeg-accent", None, jpeg.name)
        add("blurred-color-boundary", body.filter(ImageFilter.GaussianBlur(3)))
        ring = Image.new("RGBA", (960, 960))
        draw = ImageDraw.Draw(ring)
        draw.ellipse((48, 48, 912, 912), fill="#101010")
        draw.ellipse((144, 144, 816, 816), fill=(0, 0, 0, 0))
        add("transparent-counter", ring)
        narrow = Image.new("RGBA", (960, 960), "#101010")
        ImageDraw.Draw(narrow).rectangle((100, 100, 101, 147), fill=(0, 0, 0, 0))
        add("narrow-alpha-counter", narrow)
        x = np.linspace(0, 1, 1024)
        gradient = np.empty((512, 1024, 4), np.uint8)
        gradient[..., 0] = (20 + 220 * x).astype(np.uint8)
        gradient[..., 1] = (200 - 120 * x).astype(np.uint8)
        gradient[..., 2] = (220 - 100 * x).astype(np.uint8)
        gradient[..., 3] = 255
        add("continuous-gradient", Image.fromarray(gradient), width=80)
    for index, source in enumerate(local_inputs or []):
        if source.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            ".bmp",
            ".tif",
            ".tiff",
            ".svg",
        }:
            raise ValueError(
                "--input requires SVG or a supported raster; unsupported extension: "
                + source.suffix
            )
        name = "local-" + str(index)
        destination = directory / (name + source.suffix.lower())
        shutil.copy2(source, destination)
        add(name, None, destination.name, width=width_mm)
    corpus = output / "generated-corpus.json"
    save(corpus, cases)
    return corpus


def compare_refs(args):
    """Read Git archives and freeze current sources; never check out a revision."""
    import io
    import shutil
    import tarfile

    repository = next((path for path in args.source_root.parents if (path / ".git").exists()), None)
    if args.baseline_ref and repository is None:
        raise ValueError("Reference comparisons require a source root inside a Git repository")
    if args.output == args.source_root or args.source_root in args.output.parents:
        raise ValueError("Benchmark output must be outside the source tree")
    snapshots = args.output / "snapshots"
    sources = {}
    references = (
        [("main", args.baseline_ref), ("previous", args.previous_ref)] if args.baseline_ref else []
    )
    for tag, reference in references:
        commit = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "--verify", reference + "^{commit}"],
            text=True,
        ).strip()
        payload = subprocess.check_output(
            ["git", "-C", str(repository), "archive", commit, "src", "pyproject.toml"]
        )
        target = snapshots / tag
        if target.exists():
            raise ValueError("Reference comparisons require a fresh output directory")
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            for member in archive:
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe source archive path")
                if member.isfile():
                    path = target / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as contents:
                        path.write_bytes(contents.read())
        sources[tag] = {"root": target / "src", "commit": commit}
    for specification in args.snapshot:
        tag, separator, root = specification.partition("=")
        if (
            not separator
            or not tag
            or tag in {"current", ".", ".."}
            or "/" in tag
            or "\\" in tag
            or tag in sources
        ):
            raise ValueError("Use unique --snapshot LABEL=/path/to/src entries")
        source = Path(root).resolve()
        if not (source / "embroidery_rungs" / "inputs.py").is_file():
            raise ValueError("Snapshot must contain embroidery_rungs/inputs.py: " + root)
        target = snapshots / tag / "src"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        project = source.parent / "pyproject.toml"
        if project.is_file():
            shutil.copy2(project, target.parent / project.name)
        sources[tag] = {"root": target, "commit": None}
    target = snapshots / "current" / "src"
    if target.exists():
        raise ValueError("Reference comparisons require a fresh output directory")
    shutil.copytree(
        args.source_root,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    sources["current"] = {"root": target, "commit": None}
    project = args.source_root.parent / "pyproject.toml"
    if project.is_file():
        shutil.copy2(project, target.parent / project.name)
    for source in sources.values():
        source["source_tree_sha256"] = source_manifest(source["root"], source["commit"])[
            "source_tree_sha256"
        ]
    rows = {}
    for tag, source in sources.items():
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--corpus",
            str(args.corpus),
            "--source-root",
            str(source["root"]),
            "--output",
            str(args.output / tag),
            "--mode",
            args.mode,
            "--repeats",
            str(args.repeats),
            "--warmups",
            str(args.warmups),
            "--max-colors",
            str(args.max_colors),
        ]
        if args.machine:
            command.append("--machine")
        if args.check:
            command.append("--check")
        if args.names:
            command += ["--names", *args.names]
        result = subprocess.run(command)
        if result.returncode and not (args.output / tag / "summary.json").is_file():
            raise RuntimeError("Benchmark reference failed: " + tag)
        rows[tag] = {
            row["case"]["name"]: row
            for row in json.loads((args.output / tag / "summary.json").read_text())
        }
    comparison = []
    for name, current in rows["current"].items():
        phases = {}
        for tag in sources:
            row = rows[tag][name]
            valid = not row["errors"] and not current["errors"]
            phases[tag] = {
                "source_sha256": row["source_sha256"],
                "source_equal_to_current": row["source_sha256"] == current["source_sha256"],
                "svg_equal_to_current": valid and row["svg_sha256"] == current["svg_sha256"],
                "diagnostics_equal_to_current": valid
                and row["diagnostics"] == current["diagnostics"],
                "errors": row["errors"],
                "timings": row.get("timings"),
                "peak_rss_bytes": row["peak_rss_bytes"],
                "expected_outcome": row["expected_outcome"],
                "machine": row.get("machine"),
                "source_oracle": row.get("source_oracle"),
                "machine_source_oracle": row.get("machine_source_oracle"),
            }
            if args.mode == "quality":
                phases[tag]["render_equal_to_current"] = valid and row.get(
                    "svg_reference"
                ) == current.get("svg_reference")
        comparison.append({"case": name, "phases": phases})
    save(
        args.output / "comparison.json",
        {
            "mode": args.mode,
            "measurement_harness_sha256": harness_signature(),
            "scope": "Interpretation and known synthetic source intent; optional machine exports. Fabric sewout is not measured.",
            "revisions": {
                tag: {
                    "commit": source["commit"],
                    "source_tree_sha256": source["source_tree_sha256"],
                    "snapshot": str(source["root"].relative_to(args.output)),
                }
                for tag, source in sources.items()
            },
            "cases": comparison,
        },
    )
    print("Comparison:", args.output / "comparison.json")
    if args.check and any(
        report_failures(row) for phase in rows.values() for row in phase.values()
    ):
        raise SystemExit(1)


def worker(args):
    import shutil

    import numpy as np

    sys.path.insert(0, str(args.source_root))
    import embroidery_rungs.inputs as inputs
    from embroidery_rungs import GenerationParams, StitchParams, generate

    imported = Path(inputs.__file__).resolve()
    if not imported.is_relative_to(args.source_root):
        raise RuntimeError("Worker imported an engine outside the requested snapshot")

    cases = json.loads(args.corpus.read_text())
    case = cases[args.worker]
    source = args.corpus.parent / case["path"]
    source_digest = digest(source)
    if case.get("source_sha256", source_digest) != source_digest:
        raise ValueError("Source checksum changed: " + case["name"])
    directory = args.output / case["name"]
    directory.mkdir(parents=True, exist_ok=True)
    durations = {}
    record = {}
    capture = {}
    capabilities = {}
    quality = args.mode == "quality"

    def measure_labels(labels, palette, canvas):
        return {
            "size_px": [labels.shape[1], labels.shape[0]],
            "canvas_size_mm": list(canvas),
            "alpha": topology(labels > 0),
            "paint": {paint: topology(labels == index + 1) for index, paint in enumerate(palette)},
        }

    names = [
        "bitmap_foreground",
        "sample_bitmap",
        "bitmap_colors",
        "clean_color_regions",
        "serialize_bitmap",
    ]
    for name in names:
        capabilities[name] = {"available": hasattr(inputs, name), "calls": 0}
        if not hasattr(inputs, name):
            continue
        original = getattr(inputs, name)

        def wrapped(*arguments, _name=name, _call=original, **kwargs):
            started = time.perf_counter()
            result = _call(*arguments, **kwargs)
            durations[_name] = durations.get(_name, 0) + time.perf_counter() - started
            capabilities[_name]["calls"] += 1
            if quality and _name == "bitmap_foreground":
                ys, xs = np.nonzero(result[..., 3] >= 128)
                if len(ys):
                    capture["source_crop_box_px"] = [
                        int(xs.min()),
                        int(ys.min()),
                        int(xs.max() + 1),
                        int(ys.max() + 1),
                    ]
            if quality and _name == "sample_bitmap":
                capture["sample_shape"] = list(result[0].shape[:2])
            if quality and _name == "serialize_bitmap":
                artwork = arguments[0]
                capture["labels_shape"] = list(artwork.labels.shape)
                np.savez_compressed(
                    directory / "labels-before-trace.npz",
                    labels=artwork.labels,
                    palette=np.asarray(artwork.palette),
                    canvas_size_mm=np.asarray(artwork.canvas_size_mm),
                )
                record["before_trace"] = measure_labels(
                    artwork.labels, artwork.palette, artwork.canvas_size_mm
                )
            elif quality and _name == "bitmap_colors":
                labels, palette, _ = result
                # Historical releases performed thumbnail sampling inline. Its
                # returned palette grid is still an observed frame, not a fit.
                capture.setdefault("sample_shape", list(labels.shape))
                ys, xs = np.nonzero(labels)
                if len(ys):
                    capture["trim_offset"] = [int(xs.min()), int(ys.min())]
                record["after_palette"] = {
                    "size_px": [labels.shape[1], labels.shape[0]],
                    "palette": palette,
                    "paint": {
                        paint: topology(labels == index + 1) for index, paint in enumerate(palette)
                    },
                }
            return result

        setattr(inputs, name, wrapped)

    samples = []
    errors = []
    diagnostics = {}
    machine = None
    generated = None
    signatures = []
    repeat_count = 1 if quality else args.repeats + args.warmups
    run_machine = args.machine and case.get("machine", True)
    for repeat in range(repeat_count):
        durations.clear()
        diagnostics = {}
        started = time.perf_counter()
        try:
            generation = GenerationParams(
                design_width_mm=case["width_mm"],
                fit_to_hoop=True,
                background_mode=case["background"],
                raster_cleanup=case["cleanup"],
            )
            stitches = StitchParams.for_fabric(
                "stable",
                stabilizer="cutaway",
                machine="brother-skitch-pp1",
                max_colors=args.max_colors,
            )
            if run_machine:
                generated = generate(
                    source, directory / "machine", generation, stitch_params=stitches
                )
                interpreted = Path(generated.original_path)
                diagnostics = generated.input_analysis
            elif source.suffix.lower() == ".svg":
                from embroidery_rungs.svg_manager import load_svg_paths

                interpreted, _, diagnostics = inputs.prepare_artwork(
                    source, directory, generation, stitches, preserve_colors=True
                )
                load_svg_paths(interpreted)
            else:
                interpreted = inputs.raster_to_svg(
                    source,
                    directory / "interpreted.svg",
                    width_mm=case["width_mm"],
                    preserve_colors=True,
                    max_colors=args.max_colors,
                    background_mode=case["background"],
                    cleanup=case["cleanup"],
                    diagnostics=diagnostics,
                    hoop_size_mm=(100, 100),
                )
        except Exception as error:
            errors.append({"type": type(error).__name__, "message": str(error)})
            break
        elapsed = time.perf_counter() - started
        # Hashing, independent rendering and machine readback are never timed.
        if Path(interpreted).resolve() != (directory / "interpreted.svg").resolve():
            shutil.copy2(interpreted, directory / "interpreted.svg")
        signature = {"svg": digest(directory / "interpreted.svg")}
        if generated is not None:
            signature.update(
                pes=digest(Path(generated.direct.pes_path)),
                dst=digest(Path(generated.direct.dst_path)),
            )
        signatures.append(signature)
        if not quality and repeat >= args.warmups:
            samples.append({"total": elapsed, **durations})
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "case": {key: value for key, value in case.items() if key != "path"},
        "source_sha256": source_digest,
        "mode": args.mode,
        "engine_snapshot": args.source_root.parent.name,
        "measurement_harness_sha256": harness_signature(),
        "source_mapping": capture,
        "imported_engine": str(imported.relative_to(args.source_root)),
        "capabilities": capabilities,
        "record": record,
        "diagnostics": diagnostics,
        "errors": errors,
        "samples": samples,
        "warmup_runs": 0 if quality else args.warmups,
        "deterministic": all(signature == signatures[0] for signature in signatures)
        if signatures
        else None,
        "output_signatures": signatures,
        "peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024),
        "memory_note": "Whole isolated process including imports/native allocations and warm-up. macOS ru_maxrss bytes; Linux KiB converted to bytes.",
        "svg_sha256": digest(directory / "interpreted.svg") if not errors else None,
    }
    expected_error = case.get("expected_error")
    report["expected_outcome"] = {
        "error_expected": expected_error is not None,
        "passed": (bool(errors) and expected_error in errors[0]["message"])
        and errors[0]["type"] == case.get("expected_error_type", errors[0]["type"])
        if expected_error is not None
        else not errors,
    }
    if samples:
        report["timings"] = {
            key: {
                "p50_seconds": float(np.median([sample.get(key, 0) for sample in samples])),
                "p95_seconds": float(np.percentile([sample.get(key, 0) for sample in samples], 95)),
            }
            for key in sorted({key for sample in samples for key in sample})
        }
    if run_machine and not errors:
        from benchmark_fill_methods import summarize

        machine = summarize(generated.direct)
        report["machine"] = machine
    if quality and not errors:
        report["svg_reference"] = svg_metrics(directory / "interpreted.svg")
        oracle = case.get("oracle")
        if oracle:
            from benchmark_public_corpus import source_oracle

            reference = args.corpus.parent / oracle["path"]
            if digest(reference) != oracle["sha256"]:
                raise ValueError("Reference checksum changed: " + case["name"])
            geometry = diagnostics.get("geometry")
            if source.suffix.lower() != ".svg" and not geometry and "source_crop_box_px" in capture:
                geometry = {"source_crop_box_px": capture["source_crop_box_px"]}
                box = ET.parse(directory / "interpreted.svg").getroot().attrib["viewBox"].split()
                capture["labels_shape"] = [round(float(box[3])), round(float(box[2]))]
            if source.suffix.lower() != ".svg" and (
                not geometry
                or not all(
                    key in capture for key in ("sample_shape", "trim_offset", "labels_shape")
                )
            ):
                report["source_oracle"] = {
                    "available": False,
                    "reason": "Historical snapshot does not expose the complete source-coordinate mapping.",
                }
            else:
                report["source_oracle"] = source_oracle(
                    reference,
                    directory / "interpreted.svg",
                    geometry,
                    capture,
                    directory,
                    palette=oracle.get("palette"),
                    silhouette_only=oracle.get("silhouette_only", False),
                )
                report["source_oracle"]["reference_sha256"] = oracle["sha256"]
            if run_machine and oracle.get("palette"):
                from benchmark_public_corpus import machine_source_oracle

                report["machine_source_oracle"] = machine_source_oracle(
                    generated.direct, reference, oracle, directory
                )
        if "expected_regions" in case:
            report["expected_outcome"]["trace_budget_boundary_passed"] = (
                diagnostics.get("cleanup", {}).get("regions_after") == case["expected_regions"]
            )
    report["failed_checks"] = report_failures(report)
    save(directory / "report.json", report)
    print(
        json.dumps(
            {
                "case": case["name"],
                "errors": errors,
                "palette": report.get("svg_reference", {}).get("palette", []),
                "timing": report.get("timings", {}).get("total"),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=["legacy", "public"],
        default="legacy",
        help="Generated fixture set: legacy seven rasters, or 42 public SVG/raster source-oracle cases",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Manifest with source paths relative to its directory; omit for seven generated fixtures",
    )
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        help="Local raster inputs copied into the output fixture directory",
    )
    parser.add_argument(
        "--width-mm", type=float, default=80, help="Physical width for --input sources"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("src"),
        help="Current or frozen src directory (default: src)",
    )
    parser.add_argument(
        "--baseline-ref",
        help="Compare a Git baseline, previous revision and current source without checkout",
    )
    parser.add_argument(
        "--previous-ref", help="Previous Git commit/ref; use together with --baseline-ref"
    )
    parser.add_argument(
        "--snapshot",
        action="append",
        default=[],
        help="Additional frozen source: LABEL=/path/to/src; repeatable",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["quality", "performance"], default="quality")
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--machine",
        action="store_true",
        help="Generate balanced machine files and audit PES/DST roundtrips outside timings",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero for unexpected errors, trace-budget failures, nondeterminism or machine safety/roundtrip failures; source IoU is descriptive",
    )
    parser.add_argument("--max-colors", type=int, default=6)
    parser.add_argument("--names", nargs="*")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.warmups < 0:
        parser.error("--warmups must be nonnegative")
    if bool(args.baseline_ref) != bool(args.previous_ref):
        parser.error("Use both --baseline-ref and --previous-ref")
    for name in ["source_root", "output"]:
        setattr(args, name, getattr(args, name).resolve())
    if args.corpus is not None:
        args.corpus = args.corpus.resolve()
    if not (args.source_root / "embroidery_rungs" / "inputs.py").is_file():
        parser.error("--source-root must contain embroidery_rungs/inputs.py")
    if args.worker is not None:
        worker(args)
        return
    if args.output == args.source_root or args.source_root in args.output.parents:
        parser.error("Benchmark output must be outside the source tree")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("Benchmark requires a fresh output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.corpus is not None and args.input:
        parser.error("Use either --corpus or --input")
    if args.corpus is None:
        if args.suite == "public":
            from benchmark_public_corpus import public_corpus

            args.corpus = public_corpus(args.output)
            if args.input:
                # Optional private samples have checksums and comparative metrics,
                # never an invented semantic source oracle.
                private = generated_corpus(args.output / "private", args.input, args.width_mm)
                extra = json.loads(private.read_text())
                for case in extra:
                    case["path"] = "private/" + case["path"]
                save(args.corpus, json.loads(args.corpus.read_text()) + extra)
        else:
            args.corpus = generated_corpus(args.output, args.input, args.width_mm)
    cases = json.loads(args.corpus.read_text())
    try:
        validate_corpus(cases)
    except ValueError as error:
        parser.error(str(error))
    if args.names and not any(case["name"] in args.names for case in cases):
        parser.error("--names matched no corpus cases")
    if args.baseline_ref or args.snapshot:
        compare_refs(args)
        return
    # Standalone runs also freeze their imports once for the entire corpus.
    import shutil

    frozen = args.output / "snapshot" / "src"
    shutil.copytree(args.source_root, frozen, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    project = args.source_root.parent / "pyproject.toml"
    if project.is_file():
        shutil.copy2(project, frozen.parent / project.name)
    args.source_root = frozen
    source_manifest(frozen)
    reports = []
    for index, case in enumerate(cases):
        if args.names and case["name"] not in args.names:
            continue
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--corpus",
            str(args.corpus),
            "--source-root",
            str(args.source_root),
            "--output",
            str(args.output),
            "--mode",
            args.mode,
            "--repeats",
            str(args.repeats),
            "--warmups",
            str(args.warmups),
            "--max-colors",
            str(args.max_colors),
            "--worker",
            str(index),
        ]
        if args.machine:
            command.append("--machine")
        result = subprocess.run(
            command,
            env={**os.environ, "PYTHONPATH": str(args.source_root)},
            capture_output=True,
            text=True,
            timeout=180,
        )
        print(result.stdout.strip(), flush=True)
        if result.returncode:
            print(result.stderr, file=sys.stderr, flush=True)
            raise RuntimeError("Benchmark worker failed: " + case["name"])
        reports.append(json.loads((args.output / case["name"] / "report.json").read_text()))
        save(args.output / "summary.json", reports)
    print("Report:", args.output / "summary.json")
    if args.check and any(report_failures(report) for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
