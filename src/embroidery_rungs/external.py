"""Discovery and bounded execution of optional desktop tools."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _tool(name):
    override = os.environ.get(f"{name.upper()}_BIN")
    default = (
        "/Applications/Inkscape.app/Contents/MacOS/inkscape"
        if name == "inkscape"
        else str(
            Path.home()
            / "Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/"
            "inkstitch/inkstitch.app/Contents/MacOS/inkstitch"
        )
    )
    candidate = override or shutil.which(name) or default
    return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None


def _run(command, timeout=120, output=None):
    try:
        return subprocess.run(
            command,
            check=True,
            timeout=timeout,
            stdout=output or subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{Path(command[0]).name} timed out after {timeout}s.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace")[-600:] if exc.stderr else ""
        raise RuntimeError(f"{Path(command[0]).name} failed: {detail}") from exc
