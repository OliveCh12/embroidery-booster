#!/bin/bash
# Headless Ink/Stitch preview/export for a satin SVG (macOS).
#
# Usage: scripts/inkstitch_preview.sh <satin.svg> [output_dir]
#
# Produces, in output_dir (default: alongside the input):
#   <name>_plan.svg   - the design with Ink/Stitch's rendered stitch plan
#   <name>_plan.png   - a high-resolution raster of that stitch plan
#   <name>.zip        - embroidery files (.dst/.pes/threadlist) [if --zip is set]
#
# Set ZIP=1 to also export embroidery files.

set -euo pipefail

INKSTITCH="$HOME/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/inkstitch/inkstitch.app/Contents/MacOS/inkstitch"
INKSCAPE="/Applications/Inkscape.app/Contents/MacOS/inkscape"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <satin.svg> [output_dir]" >&2
    exit 1
fi
[ -x "$INKSTITCH" ] || { echo "Ink/Stitch not found: $INKSTITCH" >&2; exit 1; }
[ -x "$INKSCAPE" ]  || { echo "Inkscape not found: $INKSCAPE" >&2; exit 1; }

INPUT="$1"
OUTDIR="${2:-$(dirname "$INPUT")}"
NAME="$(basename "${INPUT%.*}")"
mkdir -p "$OUTDIR"

PLAN_SVG="$OUTDIR/${NAME}_plan.svg"
PLAN_PNG="$OUTDIR/${NAME}_plan.png"

echo "Rendering stitch plan for $INPUT..."
"$INKSTITCH" --extension=stitch_plan_preview "$INPUT" > "$PLAN_SVG"
# Ink/Stitch places the rendered stitch plan beside the design (outside the
# viewBox), so export the whole drawing area rather than just the viewBox.
"$INKSCAPE" --export-type=png --export-area-drawing --export-width=4000 \
    --export-filename="$PLAN_PNG" "$PLAN_SVG" 2>/dev/null

echo "  $PLAN_SVG"
echo "  $PLAN_PNG"

if [ "${ZIP:-0}" = "1" ]; then
    ZIP_OUT="$OUTDIR/${NAME}.zip"
    "$INKSTITCH" --extension=zip --format-dst=True --format-pes=True \
        --format-threadlist=True "$INPUT" > "$ZIP_OUT"
    echo "  $ZIP_OUT"
fi

echo "Done."
