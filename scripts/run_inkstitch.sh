#!/bin/bash
# Wrapper script to run Ink/Stitch from command line on macOS

INKSTITCH_BIN="$HOME/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/inkstitch/inkstitch.app/Contents/MacOS/inkstitch"

if [ ! -f "$INKSTITCH_BIN" ]; then
    echo "Error: Ink/Stitch executable not found at $INKSTITCH_BIN"
    exit 1
fi

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <input_svg_file> [output_zip_file]"
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="${2:-${INPUT_FILE%.*}.zip}"

echo "Running Ink/Stitch on $INPUT_FILE..."
"$INKSTITCH_BIN" --extension=zip --format-dst=True --format-pes=True --format-threadlist=True "$INPUT_FILE" > "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo "Success! Output saved to $OUTPUT_FILE"
else
    echo "Ink/Stitch failed."
    exit 1
fi
