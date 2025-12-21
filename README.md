# 🧵 Embroidery Auto Rung Generator

**Automated Rung Placement for Ink/Stitch Satin Columns**

This tool automatically generates "rungs" (direction lines) for embroidery satin stitches using the Medial Axis Transform algorithm. It is designed to streamline the workflow for the "Fill to Satin" tool in Ink/Stitch by creating structural guide lines rather than attempting complete coverage.

## 🎯 Design Philosophy

Unlike manual rung creation in Ink/Stitch where users place 3-10 rungs per shape as structural guides, this tool automatically generates an optimal number of rungs based on shape complexity. The algorithm:

- Uses Medial Axis Transform to find natural flow directions
- Places rungs at strategic locations along the skeleton
- Generates bridges at intersections for complex shapes
- Creates Ink/Stitch compatible output for "Fill to Satin" conversion

## 🚀 Quick Start

1.  **Setup:**
    ```bash
    ./setup_and_run.sh
    ```

2.  **Run:**
    ```bash
    source venv/bin/activate
    python3 -m embroidery_generator.main your_design.svg
    ```

3.  **Result:**
    Check the `output/` folder.
    -   `your_design_ready.svg`: Open this in Inkscape! It contains your shape + generated rungs.
    -   `your_design_rungs.svg`: Just the rungs.
    -   `your_design.svg`: A copy of your original file.

## ✨ Features

-   **Automatic Rung Generation**: Uses Medial Axis Transform to find optimal satin directions.
-   **Ink/Stitch Compatible**: Generates files ready for "Fill to Satin" conversion.
-   **Smart Spacing**: Adaptive rung placement based on shape complexity (3-8 rungs per segment).
-   **Bridge Generation**: Automatic bridges at intersections for complex shapes.
-   **Debug Visualization**: Optional debug output showing processing stages.
-   **Auto-Preview**: Can automatically open the result in Inkscape (macOS).

## 🛠 Options

```bash
python3 -m embroidery_generator.main [input] [options]

Options:
  -s, --spacing <mm>    Base spacing between rungs (default: 3.0, affects density)
  -d, --dpi <int>       DPI for processing (default: 150)
  --density <float>     Density multiplier (default: 1.0, higher = more rungs)
  --no-preview          Do not open Inkscape automatically
  --debug               Save debug images and analysis
  --verbose             Detailed logging output
```

## � Workflow with Ink/Stitch

1. **Generate Rungs**: Use this tool to create structural rungs for your shape
2. **Open in Inkscape**: The generated `_ready.svg` file opens automatically
3. **Convert to Satin**: In Inkscape, select your shape and rungs, then:
   - Extensions → Ink/Stitch → Tools: Satin → Fill to Satin...
   - Choose your satin parameters (underlay, density, etc.)
   - Click Apply
4. **Fine-tune**: Adjust satin parameters as needed in the Params dialog
5. **Embroider**: Export to your embroidery machine format

## 📊 Typical Output

- **Simple shapes**: 200-400 rungs with endpoints defined
- **Complex shapes**: 400-600 rungs with structural coverage
- **Bridges**: Automatic at intersections for complex shapes
- **Endpoint Coverage**: Always includes rungs at segment starts/ends

## 🎯 Key Features

- **Endpoint Rungs**: Always places rungs at segment extremities for proper satin definition
- **Adaptive Density**: Spacing-based rung placement with user control
- **Bridge Generation**: Automatic bridges at path intersections
- **InkStitch Ready**: Optimized for "Fill to Satin" conversion

This approach matches Ink/Stitch best practices where rungs define satin direction rather than attempting pixel-perfect coverage.
# embroidery-booster
