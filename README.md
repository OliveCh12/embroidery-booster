# 🧵 Embroidery Auto Rung Generator

**Automated Rung Placement for Ink/Stitch Satin Columns**

This tool automatically generates "rungs" (direction lines) for embroidery satin stitches using the Medial Axis Transform algorithm. It is designed to streamline the workflow for the "Fill to Satin" tool in Ink/Stitch.

## 🚀 Quick Start

1.  **Setup:**
    ```bash
    ./setup_and_run.sh
    ```

2.  **Run:**
    ```bash
    source venv/bin/activate
    python3 embroidery_auto_rung_generator.py your_design.svg
    ```

3.  **Result:**
    Check the `output/` folder.
    -   `your_design_ready.svg`: Open this in Inkscape! It contains your shape + generated rungs.
    -   `your_design_rungs.svg`: Just the rungs.
    -   `your_design.svg`: A copy of your original file.

## ✨ Features

-   **Automatic Rung Generation**: Uses Medial Axis Transform to find the optimal direction for satin stitches.
-   **Ink/Stitch Ready**: Generates files compatible with the "Fill to Satin" extension.
-   **Smart Output**: Creates a combined "ready-to-edit" SVG file.
-   **Auto-Preview**: Can automatically open the result in Inkscape (macOS).

## 🛠 Options

```bash
python3 embroidery_auto_rung_generator.py [input] [options]

Options:
  -s, --spacing <mm>    Spacing between rungs (default: 3.0)
  -d, --dpi <int>       DPI for processing (default: 150)
  --no-preview          Do not open Inkscape automatically
  --debug               Save debug images
```

## 📦 Project Structure

-   `embroidery_auto_rung_generator.py`: Main script.
-   `output/`: Generated files are saved here.
-   `setup_and_run.sh`: Installation helper.
# embroidery-booster
