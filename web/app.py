"""Flask server: convert any file to embroidery-ready satin.

Thin orchestration over the ``embroidery_rungs`` library and the ``services``
module (Inkscape / Ink/Stitch). Each request runs in an isolated job directory
so outputs keep their real names and never clobber each other.
"""

import io
import os
import re
import glob
import shutil
import logging
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from embroidery_rungs import generate, GenerationParams
import services

app = Flask(__name__)

OUTPUT_ROOT = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# Clear stale job directories from previous runs.
for _d in glob.glob(os.path.join(OUTPUT_ROOT, "*")):
    if os.path.isdir(_d):
        shutil.rmtree(_d, ignore_errors=True)

_TRAVEL_RE = re.compile(r"travel (\d+)px -> (\d+)px \(-(\d+)%\)")
_JOB_RE = re.compile(r"^[0-9a-f]{12,}$")


@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "index.html")


def _url(job, *parts):
    return "/api/file/" + job + "/" + "/".join(parts)


@app.route("/api/convert", methods=["POST"])
def convert():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Aucun fichier fourni."}), 400

    spacing = float(request.form.get("spacing", 3.0))
    density = float(request.form.get("density", 1.0))
    auto_optimize = request.form.get("auto_optimize", "false") == "true"

    job = uuid4().hex
    job_dir = os.path.join(OUTPUT_ROOT, job)
    os.makedirs(job_dir, exist_ok=True)

    filename = secure_filename(file.filename) or "input"
    in_path = os.path.join(job_dir, filename)
    file.save(in_path)
    ext = os.path.splitext(filename)[1].lower()

    # Capture library logs for the UI.
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    lib_logger = logging.getLogger("embroidery_rungs")
    lib_logger.addHandler(handler)
    lib_logger.setLevel(logging.INFO)

    warnings = []
    try:
        try:
            svg_path = services.convert_to_svg(in_path, job_dir)
        except Exception as e:
            return jsonify({"error": f"Conversion impossible : {e}"}), 400

        try:
            result = generate(svg_path, output_dir=job_dir,
                              params=GenerationParams(spacing=spacing, density=density,
                                                      auto_optimize=auto_optimize, debug=True))
        except Exception as e:
            return jsonify({"error": f"Échec du traitement : {e}"}), 500
    finally:
        lib_logger.removeHandler(handler)

    logs = log_stream.getvalue()
    base = os.path.splitext(os.path.basename(result.satin_path))[0].replace("_satin", "")

    # Downloadable files.
    files = {
        "Satin (Ink/Stitch)": _url(job, os.path.basename(result.satin_path)),
        "Combiné (éditable)": _url(job, os.path.basename(result.ready_path)),
        "Rungs seuls": _url(job, os.path.basename(result.rungs_path)),
    }

    # Embroidery export and stitch preview are independent Ink/Stitch calls —
    # run them concurrently.
    zip_path = os.path.join(job_dir, base + ".zip")
    preview_png = os.path.join(job_dir, base + "_preview.png")
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_zip = pool.submit(services.export_embroidery, result.satin_path, zip_path)
        fut_prev = pool.submit(services.render_stitch_preview, result.satin_path, preview_png)

    try:
        fut_zip.result()
        files["Broderie (.dst/.pes)"] = _url(job, os.path.basename(zip_path))
    except Exception as e:
        warnings.append(f"Export broderie indisponible : {e}")

    satin_preview = None
    try:
        fut_prev.result()
        satin_preview = _url(job, os.path.basename(preview_png))
    except Exception as e:
        warnings.append(f"Aperçu satin indisponible : {e}")

    # Debug images.
    debug_images = {}
    debug_dir = os.path.join(job_dir, "debug")
    if os.path.isdir(debug_dir):
        for name in sorted(os.listdir(debug_dir)):
            if name.endswith(".png"):
                debug_images[name] = _url(job, "debug", name)

    travel = _TRAVEL_RE.search(logs)
    return jsonify({
        "success": True,
        "job": job,
        "stats": {
            "rungs": result.rungs_count,
            "columns": result.columns_count,
            "running": result.running_count,
            "coverage": round(result.coverage * 100, 1),
            "travel_saved": int(travel.group(3)) if travel else None,
        },
        "converted_from": ext.lstrip(".") if ext != ".svg" else None,
        "files": files,
        "satin_preview": satin_preview,
        "debug_images": debug_images,
        "warnings": warnings,
        "logs": logs[-4000:],
    })


@app.route("/api/file/<job>/<path:filename>")
def serve_file(job, filename):
    if not _JOB_RE.match(job):
        return jsonify({"error": "Invalid job id"}), 400
    job_dir = os.path.join(OUTPUT_ROOT, job)
    download = filename.endswith((".svg", ".zip"))
    return send_from_directory(job_dir, filename, as_attachment=download)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
