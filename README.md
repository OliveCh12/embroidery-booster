# Embroidery Auto Rung Generator

An automatic embroidery rung placement system that uses Medial Axis Transform (MAT) to generate optimal rung patterns for embroidery satins.

## Features

- **Automatic Parameter Optimization**: Finds optimal spacing and density for any SVG file to achieve ≤25 rungs without intersections
- **Web Interface**: Modern drag-and-drop interface for interactive parameter testing with real-time preview
- **Command Line Interface**: Full CLI support with manual parameter control
- **Debug Visualization**: Generates debug images showing skeleton, distance maps, and rung placement

## Project Structure

```
stich/
├── src/                    # Core Python modules
│   ├── __init__.py
│   ├── main.py            # CLI entry point
│   ├── svg_manager.py     # SVG loading and saving
│   ├── image_processor.py # Rasterization and skeletonization
│   ├── rung_generator.py  # Rung placement algorithm
│   ├── debug_utils.py     # Debug image generation
│   ├── geometry_utils.py  # Geometric utilities
│   ├── inputs/            # Sample SVG files
│   │   ├── svg/          # SVG test files
│   │   └── png/          # PNG test files
│   └── output/           # Generated files
│       ├── debug/        # Debug images
│       └── render/       # Rendered outputs
├── web/                   # Web interface
│   ├── app.py            # Flask API server
│   └── index.html        # Frontend interface
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Inkscape is installed (required for SVG rasterization)

## Usage

### Command Line

Run the generator on an SVG file:

```bash
# From project root
python -m src.main src/inputs/svg/nike.svg --auto-optimize --debug

# Manual parameters
python -m src.main src/inputs/svg/nike.svg --spacing 3.0 --density 1.0 --debug
```

### Web Interface

Start the web server:

```bash
cd web
python app.py
```

Then open http://localhost:8000 in your browser.

## Parameters

- `spacing`: Rung spacing in mm (default: 3.0)
- `density`: Density multiplier (default: 1.0, higher = more rungs)
- `dpi`: Processing DPI (default: 150, higher = better quality)
- `--auto-optimize`: Automatically find optimal parameters
- `--debug`: Save debug images
- `--verbose`: Verbose output

## Output Files

For input file `example.svg`, the following are generated in `src/output/`:

- `example.svg`: Original file copy
- `example_rungs.svg`: Rungs only
- `example_ready.svg`: Combined file ready for editing

Debug images are saved in `src/output/debug/` when `--debug` is used.

## Algorithm

1. **SVG Loading**: Parse SVG paths and extract endpoints
2. **Rasterization**: Convert to high-resolution binary image using Inkscape
3. **Skeletonization**: Compute medial axis transform using scikit-image
4. **Rung Generation**: Place rungs along skeleton with adaptive spacing
5. **Optimization**: Test configurations to minimize intersections while maximizing coverage

## Dependencies

- numpy: Numerical computations
- scipy: Scientific computing
- scikit-image: Image processing and skeletonization
- svgelements: SVG parsing
- networkx: Graph operations
- flask: Web framework
- flask-cors: CORS support
- Inkscape: SVG rasterization</content>
<parameter name="filePath">/Users/olivierchemla/Dev/perso/stich/README.md