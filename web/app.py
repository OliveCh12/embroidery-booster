"""Flask server exposing the rung generator as a small web app.

This is a thin client over the ``embroidery_rungs`` library: it never drives the
CLI or scrapes logs — it calls :func:`embroidery_rungs.generate` directly.
"""

import io
import os
import logging
import tempfile

from flask import Flask, request, jsonify, send_file, send_from_directory

from embroidery_rungs import generate, GenerationParams

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
DEBUG_FOLDER = os.path.join(OUTPUT_FOLDER, "debug")
for folder in (UPLOAD_FOLDER, OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/optimize", methods=["POST"])
def optimize_svg():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier fourni"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Aucun fichier sélectionné"}), 400
    if not file.filename.lower().endswith(".svg"):
        return jsonify({"error": "Le fichier doit être un SVG"}), 400

    spacing = float(request.form.get("spacing", 3.0))
    density = float(request.form.get("density", 1.0))

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    # Capture library logs to show them in the UI.
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    lib_logger = logging.getLogger("embroidery_rungs")
    lib_logger.addHandler(handler)
    lib_logger.setLevel(logging.INFO)

    try:
        params = GenerationParams(spacing=spacing, density=density, debug=True)
        result = generate(temp_path, output_dir=OUTPUT_FOLDER, params=params)
    except Exception as e:  # noqa: BLE001 - surface any failure to the client
        return jsonify({"error": f"Erreur lors du traitement: {e}"}), 500
    finally:
        lib_logger.removeHandler(handler)
        os.unlink(temp_path)

    debug_images = {}
    if os.path.isdir(DEBUG_FOLDER):
        for name in os.listdir(DEBUG_FOLDER):
            if name.startswith("debug_") and name.endswith((".png", ".svg")):
                debug_images[name] = f"{OUTPUT_FOLDER}/debug/{name}"

    return jsonify({
        "success": True,
        "rungs_count": result.rungs_count,
        "bridges": result.bridges_count,
        "intersections": result.bridges_count,
        "coverage": round(result.coverage * 100, 1),
        "command": (f'embroidery-rungs "{file.filename}" '
                    f"--spacing={spacing} --density={density} --debug"),
        "output_files": {
            "Rungs Only": os.path.basename(result.rungs_path),
            "Ready to Edit": os.path.basename(result.ready_path),
        },
        "debug_images": debug_images,
        "logs": log_stream.getvalue()[-2000:],
    })


@app.route("/api/download/<path:filename>")
def download_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Fichier non trouvé"}), 404
    return send_file(file_path, as_attachment=True)


@app.route("/debug/<path:filename>")
def serve_debug_image(filename):
    file_path = os.path.join(DEBUG_FOLDER, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Image de debug non trouvée"}), 404
    return send_file(file_path)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
