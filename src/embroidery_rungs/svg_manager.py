"""Validated SVG geometry and its physical coordinate transform."""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from pathlib import Path as FilePath
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from svgelements import SVG, Matrix, Path, Shape, Viewbox

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
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
            raise ValueError(f"Unsupported SVG element <{tag}>; convert it to vector paths first.")
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
