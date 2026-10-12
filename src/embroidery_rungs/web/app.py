"""Bounded, isolated Flask jobs; no destructive work at import or startup."""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import threading
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.image_processor import render_preview
from embroidery_rungs.stitching.params import MACHINE_PROFILES


class _RequestLogs(logging.Filter):
    def __init__(self):
        super().__init__()
        self.thread = threading.get_ident()

    def filter(self, record):
        return record.thread == self.thread


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        MAX_JOBS=2,
        OUTPUT_ROOT=os.environ.get("EMBROIDERY_OUTPUT_DIR", str(Path.cwd() / "output/web")),
        QUALITY_REPORT_DIR=Path.cwd() / "output/quality",
    )
    if config:
        app.config.update(config)
    semaphore = threading.BoundedSemaphore(app.config["MAX_JOBS"])
    lib_logger = logging.getLogger("embroidery_rungs")
    lib_logger.setLevel(logging.INFO)

    @app.get("/")
    def index():
        return jsonify(
            service="embroidery-booster", frontend="Next.js", capabilities="/api/capabilities"
        )

    @app.get("/quality/<path:filename>")
    def quality_file(filename):
        return send_from_directory(app.config["QUALITY_REPORT_DIR"], filename)

    @app.get("/api/capabilities")
    def capabilities():
        return jsonify(
            engine="direct",
            accepted_formats=["svg", "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"],
            direct=True,
            direct_formats=["pes", "dst"],
            quality_report=(Path(app.config["QUALITY_REPORT_DIR"]) / "comparison.json").is_file(),
            machine_profiles=MACHINE_PROFILES,
            material_presets={
                fabric: {
                    str(weight): {
                        "stitch_spacing": preset.satin_spacing_mm,
                        "fill_spacing": preset.fill_spacing_mm,
                        "pull_compensation": preset.pull_compensation_mm,
                        "underlay": preset.underlay,
                    }
                    for weight in (30, 40, 60)
                    for preset in (StitchParams.for_fabric(fabric, thread_weight=weight),)
                }
                for fabric in ("custom", "stable", "stretch", "textured")
            },
        )

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="Le fichier dépasse la limite de 10 Mio."), 413

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        styles = "'self' 'unsafe-inline'" if request.path.startswith("/quality/") else "'self'"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self'; style-src {styles}; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'"
        )
        return response

    @app.post("/api/convert")
    def convert():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify(error="Aucun fichier fourni."), 400
        try:
            if request.form.get("method", "direct") != "direct":
                raise ValueError("Only the direct stitch engine is supported.")
            retired = {
                "spacing",
                "density",
                "dpi",
                "auto_optimize",
                "debug",
                "export",
                "wide_mode",
                "fill_gaps",
                "auto_select",
            } & request.form.keys()
            if retired:
                raise ValueError("Unsupported settings: " + ", ".join(sorted(retired)))

            def boolean(name, default):
                value = request.form.get(name)
                if value is None:
                    return default
                if value not in ("true", "false"):
                    raise ValueError(f"{name} must be true or false.")
                return value == "true"

            params = GenerationParams(
                design_width_mm=float(request.form["design_width"])
                if request.form.get("design_width")
                else None,
                fit_to_hoop=boolean("fit_to_hoop", False),
                raster_threshold=int(request.form["raster_threshold"])
                if request.form.get("raster_threshold")
                else None,
                raster_invert=boolean("raster_invert", False),
            )
            params.validate()
            stitch_params = StitchParams.for_fabric(
                request.form.get("fabric", "custom"),
                thread_weight=int(request.form.get("thread_weight", 40)),
                stabilizer=request.form.get("stabilizer", "unspecified"),
                machine=request.form.get("machine", "generic"),
            )
            for field, name in (
                ("hoop_width", "hoop_width_mm"),
                ("hoop_height", "hoop_height_mm"),
                ("stitch_spacing", "satin_spacing_mm"),
                ("running_length", "running_length_mm"),
                ("fill_spacing", "fill_spacing_mm"),
                ("fill_angle", "fill_angle_deg"),
                ("max_stitch", "max_stitch_mm"),
                ("max_satin_width", "max_satin_width_mm"),
                ("pull_compensation", "pull_compensation_mm"),
            ):
                if field in request.form:
                    setattr(stitch_params, name, float(request.form[field]))
            if "max_colors" in request.form:
                stitch_params.max_colors = int(request.form["max_colors"])
            for name in ("preserve_colors", "underlay", "auto_adjust", "auto_fill_angle"):
                setattr(stitch_params, name, boolean(name, getattr(stitch_params, name)))
            stitch_params.thread_color = request.form.get(
                "thread_color", stitch_params.thread_color
            )
            stitch_params.validate()
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if not semaphore.acquire(blocking=False):
            return jsonify(error="Serveur occupé. Réessayez après le traitement en cours."), 503
        directory = Path(app.config["OUTPUT_ROOT"]).resolve() / uuid4().hex
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(_RequestLogs())
        lib_logger.addHandler(handler)
        succeeded = False
        try:
            directory.mkdir(parents=True)
            filename = secure_filename(upload.filename)
            if not filename:
                raise ValueError("Nom de fichier invalide.")
            source = directory / filename
            upload.save(source)
            result = generate(source, directory, params, stitch_params=stitch_params)
            job = directory.name

            def url(path):
                return f"/api/file/{job}/{Path(path).relative_to(directory).as_posix()}"

            artwork_preview = directory / "artwork.png"
            artwork_preview.write_bytes(
                render_preview(result.original_path, *result.artwork_size_mm, max_dimension=1000)
            )
            direct = result.direct
            succeeded = True
            return jsonify(
                success=True,
                job=job,
                direct={
                    "files": {
                        "pes": url(direct.pes_path),
                        "dst": url(direct.dst_path),
                        "preview_svg": url(direct.svg_path),
                        "plan_json": url(direct.plan_path),
                    },
                    "preview": url(direct.preview_path),
                    "stats": direct.stats,
                    "decisions": direct.decisions,
                    "threads": direct.threads,
                    "params": asdict(direct.params),
                    "requested_params": direct.requested_params,
                    "adjustments": direct.adjustments,
                    "analysis": direct.analysis,
                },
                warnings=list(dict.fromkeys([*result.warnings, *direct.warnings])),
                artwork_preview=url(artwork_preview),
                artwork_svg=url(result.original_path),
                artwork_size_mm=result.artwork_size_mm,
                converted_from=source.suffix.lower()[1:]
                if source.suffix.lower() != ".svg"
                else None,
                stats={"total_seconds": round(result.timings["total"], 3)},
                logs=stream.getvalue()[-4000:],
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 422
        except Exception:
            app.logger.exception("Embroidery generation failed")
            return jsonify(error="Échec du traitement. Consultez les logs du serveur."), 500
        finally:
            lib_logger.removeHandler(handler)
            semaphore.release()
            if not succeeded:
                shutil.rmtree(directory, ignore_errors=True)

    @app.get("/api/file/<job>/<path:filename>")
    def serve_file(job, filename):
        if not re.fullmatch(r"[0-9a-f]{32}", job):
            return jsonify(error="Invalid job id"), 400
        # The upload itself can contain active SVG content; SVG downloads are
        # attachments. Browser previews are raster PNGs generated by the server.
        return send_from_directory(
            Path(app.config["OUTPUT_ROOT"]) / job,
            filename,
            as_attachment=filename.lower().endswith((".svg", ".pes", ".dst", ".json")),
        )

    return app


def main():
    import argparse

    from waitress import serve

    parser = argparse.ArgumentParser(description="Embroidery Booster Python API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    serve(create_app(), host=args.host, port=args.port, threads=4)


if __name__ == "__main__":
    main()
