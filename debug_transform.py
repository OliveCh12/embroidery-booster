import svgelements
from svgelements import SVG, Matrix

svg = SVG.parse('shape_2.svg')
print(f"ViewBox: {svg.viewbox}")
print(f"X, Y: {svg.x}, {svg.y}")

paths = list(svg.elements())
path = paths[0]
print(f"Path BBox: {path.bbox()}")

# Test transform logic
bbox = path.bbox()
padding = 20
scale = 1.56
transform = Matrix.translate(-bbox[0] + padding, -bbox[1] + padding) * Matrix.scale(scale)
print(f"Original Transform: {transform}")

offset_x = svg.viewbox.x
offset_y = svg.viewbox.y
correction = Matrix.translate(-offset_x, -offset_y)
corrected_transform = correction * transform
print(f"Corrected Transform: {corrected_transform}")

inv_transform = ~corrected_transform
print(f"Inverse Corrected: {inv_transform}")

# Test point
p_img = svgelements.Point(100, 100)
p_orig = p_img * inv_transform
print(f"Point (100, 100) -> {p_orig}")
