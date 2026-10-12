"""Validated SVG input and namespace-aware, physically scaled outputs."""

from __future__ import annotations

import copy
import io
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path as FilePath
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from svgelements import SVG, Matrix, Path, Point, Shape, Viewbox

SVG_NS = "http://www.w3.org/2000/svg"
INKSTITCH_NS = "http://inkstitch.org/namespace"
ET.register_namespace("", SVG_NS)
ET.register_namespace("inkstitch", INKSTITCH_NS)
UNITS_PER_MM = 96 / 25.4
MAX_INPUT_BYTES = 10 * 1024 * 1024


@dataclass
class SVGDocument:
    root: ET.Element
    width: float
    height: float
    user_to_world: Matrix

    @property
    def xml(self) -> str:
        return ET.tostring(self.root, encoding="unicode")


def load_svg_paths(svg_path):
    file = FilePath(svg_path)
    if file.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("SVG exceeds the 10 MiB input limit.")
    try:
        root = SafeET.fromstring(file.read_bytes())
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ValueError(f"Invalid SVG XML: {exc}") from exc
    if root.tag not in (f"{{{SVG_NS}}}svg", "svg"):
        raise ValueError("Expected an SVG document.")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"script", "foreignObject", "image", "text"}:
            raise ValueError(f"Unsupported SVG element <{tag}>; convert it to paths in Inkscape.")
        for key, value in element.attrib.items():
            if key.rsplit("}", 1)[-1] == "href" and not value.startswith("#"):
                raise ValueError("External SVG resources are not supported.")
            if key.lower().startswith("on"):
                raise ValueError("SVG event handlers are not supported.")
        if tag == "style" and element.text:
            css = element.text
            if "@import" in css.lower() or any(
                not x.strip(" \"'").startswith("#") for x in re.findall(r"url\((.*?)\)", css, re.I)
            ):
                raise ValueError("External CSS resources are not supported.")
    for value in (v for e in root.iter() for v in e.attrib.values()):
        if any(
            not x.strip(" \"'").startswith("#") for x in re.findall(r"url\((.*?)\)", value, re.I)
        ):
            raise ValueError("External SVG resources are not supported.")
    try:
        parsed = SVG.parse(io.StringIO(ET.tostring(root, encoding="unicode")), on_error="raise")
    except (ValueError, TypeError, IndexError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid SVG geometry: {exc}") from exc
    vb = parsed.viewbox
    width = float(parsed.width or (vb.width if vb else 0))
    height = float(parsed.height or (vb.height if vb else 0))
    if not all(math.isfinite(x) and x > 0 for x in (width, height)):
        raise ValueError("SVG needs positive width/height or a viewBox.")
    matrix = Matrix()
    if vb:
        if vb.width <= 0 or vb.height <= 0:
            raise ValueError("SVG viewBox dimensions must be positive.")
        matrix = Matrix(
            Viewbox.viewbox_transform(
                0,
                0,
                width,
                height,
                vb.x,
                vb.y,
                vb.width,
                vb.height,
                root.get("preserveAspectRatio"),
            )
        )
    matrix *= Matrix(root.get("transform", ""))
    # Resolve percentage/missing dimensions once, identically for renderer and parser.
    root.set("width", str(width))
    root.set("height", str(height))
    paths = [
        p if isinstance(p, Path) else Path(p) for p in parsed.elements() if isinstance(p, Shape)
    ]
    return SVGDocument(root, width, height, matrix), paths


def _root(svg: SVGDocument) -> ET.Element:
    return ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": f"{svg.width / UNITS_PER_MM:.6f}mm",
            "height": f"{svg.height / UNITS_PER_MM:.6f}mm",
            "viewBox": f"0 0 {svg.width:.6f} {svg.height:.6f}",
            "version": "1.1",
        },
    )


def _point(p, transform):
    q = Point(*p) * transform
    return f"{q.x:.5f},{q.y:.5f}"


def _polyline(points, transform):
    return "M " + " L ".join(_point(p, transform) for p in points)


def _satin_rail_paths(element, transform):
    rails = [[Point(*p) * transform for p in element[key]] for key in ("rail_a", "rail_b")]
    for index in (0, 1):
        length = sum(
            math.hypot(b.x - a.x, b.y - a.y)
            for a, b in zip(rails[index][:-1], rails[index][1:], strict=True)
        )
        if length > 0.0001:
            continue
        # A fan's point rail is valid geometry, but Ink/Stitch requires two polylines.
        other = rails[1 - index]
        other_length = sum(
            math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(other[:-1], other[1:], strict=True)
        )
        fraction = min(0.05, 0.02 * UNITS_PER_MM / max(other_length, 1e-8))
        rails[index] = [
            Point(a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction)
            for a, b in zip(rails[index], other, strict=True)
        ]
    return ["M " + " L ".join(f"{p.x:.5f},{p.y:.5f}" for p in rail) for rail in rails]


def _guides(root, rungs, bridges, transform):
    group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "generated_rungs", "fill": "none"})
    for name, lines, color in (("rungs", rungs, "#e02020"), ("bridges", bridges, "#1466c8")):
        g = ET.SubElement(
            group, f"{{{SVG_NS}}}g", {"id": name, "stroke": color, "stroke-width": ".3"}
        )
        for a, b in lines:
            ET.SubElement(g, f"{{{SVG_NS}}}path", {"d": _polyline((a, b), transform)})


def _write(root, path):
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def save_rungs_svg(output_path, rungs, bridges, transform, svg):
    root = _root(svg)
    _guides(root, rungs, bridges, ~transform)
    _write(root, output_path)


def save_combined_svg(output_path, rungs, bridges, transform, svg):
    root = copy.deepcopy(svg.root)
    # Image -> viewport CSS coordinates -> source viewBox coordinates.
    _guides(root, rungs, bridges, ~transform * ~svg.user_to_world)
    _write(root, output_path)


def save_satin_svg(output_path, elements, transform, svg):
    root = _root(svg)
    metadata = ET.SubElement(root, f"{{{SVG_NS}}}metadata")
    ET.SubElement(metadata, f"{{{INKSTITCH_NS}}}inkstitch_svg_version").text = "3"
    group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "embroidery"})
    inv = ~transform
    for i, element in enumerate(elements):
        attrs = {
            "id": f"{element['type']}_{i}",
            "style": "fill:none;stroke:#e02020;stroke-width:.5",
        }
        if element["type"] == "running":
            attrs["style"] = "fill:none;stroke:#1466c8;stroke-width:.5;stroke-dasharray:1.5,1"
            attrs[f"{{{INKSTITCH_NS}}}stroke_method"] = "running_stitch"
            attrs[f"{{{INKSTITCH_NS}}}running_stitch_length_mm"] = "2.5"
            attrs["d"] = _polyline(element["points"], inv)
        else:
            attrs[f"{{{INKSTITCH_NS}}}satin_column"] = "true"
            parts = _satin_rail_paths(element, inv)
            # Paired-node satin avoids ambiguous rail detection at shared inner
            # corners. Explicit direction guides live in the other SVG outputs.
            attrs["d"] = " ".join(parts)
        ET.SubElement(group, f"{{{SVG_NS}}}path", attrs)
    _write(root, output_path)


def open_in_inkscape(filepath):
    executable = shutil.which("inkscape")
    if executable:
        subprocess.Popen(
            [executable, str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return
    import sys

    if sys.platform == "darwin":
        subprocess.run(["open", "-a", "Inkscape", str(filepath)], check=False)
