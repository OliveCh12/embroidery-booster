#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <satin.svg> [output_dir]; ZIP=1 also exports machine files" >&2
  exit 1
fi
"${PYTHON_BIN:-python}" - "$@" <<'PY'
import os
import sys
from pathlib import Path
from embroidery_rungs.web.services import export_embroidery, render_stitch_preview
source = Path(sys.argv[1]).resolve()
directory = Path(sys.argv[2]) if len(sys.argv) > 2 else source.parent
directory.mkdir(parents=True, exist_ok=True)
print(render_stitch_preview(source, directory / (source.stem + '_plan.png')))
if os.environ.get('ZIP') == '1':
    print(export_embroidery(source, directory / (source.stem + '.zip')))
PY
