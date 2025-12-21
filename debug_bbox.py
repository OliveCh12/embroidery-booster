from svgelements import *

svg = SVG.parse('shape_2.svg')
print(f"ViewBox: {svg.viewbox}")
print(f"Viewport: {svg.width}, {svg.height}")
print(f"X, Y: {svg.x}, {svg.y}")

paths = []
for element in svg.elements():
    if isinstance(element, Path):
        paths.append(element)

bbox = None
for path in paths:
    if bbox is None:
        bbox = path.bbox()
    else:
        b = path.bbox()
        if b:
            bbox = (min(bbox[0], b[0]), min(bbox[1], b[1]), 
                    max(bbox[2], b[2]), max(bbox[3], b[3]))

print(f"BBox: {bbox}")
