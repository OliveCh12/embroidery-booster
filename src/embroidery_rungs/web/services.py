"""Native Ink/Stitch configuration, exports and previews."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
from svgelements import SVG, Matrix, Point, Viewbox

from ..external import _run, _tool
from ..image_processor import render_preview
from ..stitching.params import StitchParams
from ..svg_manager import INKSTITCH_NS


def has_inkscape():
    return _tool("inkscape") is not None


def has_inkstitch():
    return _tool("inkstitch") is not None


def configure_native_svg(satin_svg, destination, params=None):
    """Material settings and bounded top/underlay stitches for the native engine."""
    from defusedxml.ElementTree import parse

    params = params or StitchParams()
    params.validate()
    tree = parse(satin_svg)
    for element in tree.getroot().iter():
        if not element.tag.endswith("}path"):
            continue
        element.set(f"{{{INKSTITCH_NS}}}trim_after", "true")
        if element.get(f"{{{INKSTITCH_NS}}}satin_column"):
            for name, value in {
                "zigzag_spacing_mm": params.satin_spacing_mm,
                "pull_compensation_mm": params.pull_compensation_mm,
                "max_stitch_length_mm": params.max_stitch_mm - 0.15,
                "center_walk_underlay": params.underlay,
                "center_walk_underlay_stitch_length_mm": min(2.0, params.max_stitch_mm - 0.15),
                "zigzag_underlay": params.underlay,
                "zigzag_underlay_spacing_mm": 3.0,
                "zigzag_underlay_inset_mm": 0.6,
                "zigzag_underlay_max_stitch_length_mm": min(
                    params.running_length_mm, params.max_stitch_mm - 0.15
                ),
            }.items():
                element.set(f"{{{INKSTITCH_NS}}}{name}", str(value).lower())
        else:
            element.set(
                f"{{{INKSTITCH_NS}}}running_stitch_length_mm",
                str(min(params.running_length_mm, params.max_stitch_mm - 0.15)),
            )
    tree.write(destination, encoding="utf-8", xml_declaration=True)
    return str(destination)


def native_export_stats(archive):
    with zipfile.ZipFile(archive) as bundle:
        filename = next((n for n in bundle.namelist() if n.lower().endswith(".pes")), None)
        if filename is None:
            raise ValueError("Ink/Stitch archive does not contain a PES file.")
        pattern = pe.read_pes(io.BytesIO(bundle.read(filename)))
    commands = np.asarray(pattern.stitches)
    if len(commands) < 2:
        raise ValueError("Ink/Stitch produced an empty stitch plan.")
    codes = commands[:, 2].astype(int) & pe.COMMAND_MASK
    sewn = (codes[:-1] == pe.STITCH) & (codes[1:] == pe.STITCH)
    lengths = np.linalg.norm(np.diff(commands[:, :2], axis=0), axis=1)[sewn] / 10
    return {
        "stitches": int(np.count_nonzero(codes == pe.STITCH)),
        "trims": int(np.count_nonzero(codes == pe.TRIM)),
        "max_stitch_mm": round(float(lengths.max(initial=0)), 2),
    }


def export_embroidery(satin_svg, zip_path, *, stitch_params=None):
    executable = _tool("inkstitch")
    if not executable:
        raise RuntimeError("Ink/Stitch is not installed; configure INKSTITCH_BIN.")
    destination = Path(zip_path)
    temporary = destination.with_suffix(".zip.part")
    try:
        with (
            tempfile.TemporaryDirectory(prefix=".native-", dir=destination.parent) as work,
            temporary.open("wb") as out,
        ):
            prepared = configure_native_svg(satin_svg, Path(work) / "configured.svg", stitch_params)
            _run(
                [
                    executable,
                    "--extension=zip",
                    "--format-dst=True",
                    "--format-pes=True",
                    "--format-threadlist=True",
                    prepared,
                ],
                timeout=180,
                output=out,
            )
        if not zipfile.is_zipfile(temporary):
            raise RuntimeError("Ink/Stitch did not produce a valid ZIP archive.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def render_stitch_preview(satin_svg, png_path, *, stitch_params=None, align_source=False):
    executable = _tool("inkstitch")
    if not executable:
        raise RuntimeError("Ink/Stitch is not installed; configure INKSTITCH_BIN.")
    with tempfile.TemporaryDirectory(prefix=".native-", dir=Path(png_path).parent) as work:
        prepared = configure_native_svg(satin_svg, Path(work) / "configured.svg", stitch_params)
        command = [executable, "--extension=stitch_plan_preview"]
        if align_source:
            command.append("--move-to-side=False")
        result = _run([*command, prepared], timeout=180)
    from defusedxml.ElementTree import fromstring

    root = fromstring(result.stdout)
    for parent in root.iter():
        for child in list(parent):
            if child.get("id") == "embroidery" or (
                child.tag.endswith("}use")
                and any("inkstitch" in value for value in child.attrib.values())
            ):
                parent.remove(child)
    # Ink/Stitch places its plan beside the original design, outside the page.
    # Fit the preview to that drawing rather than rendering an empty page.
    parsed = SVG.parse(io.StringIO(ET.tostring(root, encoding="unicode")), on_error="raise")
    bounds = parsed.bbox()
    if not bounds:
        raise RuntimeError("Ink/Stitch produced an empty stitch preview.")
    if not align_source:
        to_user = Matrix()
        vb = parsed.viewbox
        if vb:
            to_user = ~Matrix(
                Viewbox.viewbox_transform(
                    0,
                    0,
                    parsed.width,
                    parsed.height,
                    vb.x,
                    vb.y,
                    vb.width,
                    vb.height,
                    root.get("preserveAspectRatio"),
                )
            )
        low = Point(bounds[0], bounds[1]) * to_user
        high = Point(bounds[2], bounds[3]) * to_user
        width, height = high.x - low.x + 10, high.y - low.y + 10
        root.set("viewBox", f"{low.x - 5} {low.y - 5} {width} {height}")
        root.set("width", str(width))
        root.set("height", str(height))
    else:
        width, height = parsed.width, parsed.height
    ET.ElementTree(root).write(
        Path(png_path).with_suffix(".svg"), encoding="utf-8", xml_declaration=True
    )
    Path(png_path).write_bytes(
        render_preview(Path(png_path).with_suffix(".svg"), width, height, max_dimension=1400)
    )
    return str(png_path)
