#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <satin.svg> [output.zip]" >&2
  exit 1
fi
"${PYTHON_BIN:-python}" - "$@" <<'PY'
import sys
from pathlib import Path
from embroidery_rungs.web.services import export_embroidery
source = Path(sys.argv[1])
destination = Path(sys.argv[2]) if len(sys.argv) > 2 else source.with_suffix('.zip')
print(export_embroidery(source, destination))
PY
