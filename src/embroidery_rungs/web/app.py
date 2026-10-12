"""Bounded, isolated Flask jobs; no destructive work at import or startup."""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import threading
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.image_processor import render_preview
from embroidery_rungs.stitching.params import MACHINE_PROFILES

from . import services


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
        QUALITY_REPORT_DIR=Path.cwd() / "output/quality-comparison",
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
            inkscape=services.has_inkscape(),
            inkstitch=services.has_inkstitch(),
            direct=True,
            direct_formats=["pes", "dst"],
            quality_report=(Path(app.config["QUALITY_REPORT_DIR"]) / "comparison.json").is_file(),
            recommended_method="direct",
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
            method = request.form.get("method", "inkstitch")
            if method not in ("inkstitch", "direct", "both"):
                raise ValueError("Unknown generation method.")
            params = GenerationParams(
                spacing=float(request.form.get("spacing", 3)),
                density=float(request.form.get("density", 1)),
                dpi=int(request.form.get("dpi", 150)),
                auto_optimize=request.form.get("auto_optimize", "false") == "true",
                debug=request.form.get("debug", "false") == "true",
                design_width_mm=float(request.form["design_width"])
                if request.form.get("design_width")
                else None,
                fit_to_hoop=request.form.get("fit_to_hoop", "false") == "true",
                raster_threshold=int(request.form["raster_threshold"])
                if request.form.get("raster_threshold")
                else None,
                raster_invert=request.form.get("raster_invert", "false") == "true",
            )
            params.validate()
            stitch_params = StitchParams.for_fabric(
                request.form.get("fabric", "custom"),
                thread_weight=int(request.form.get("thread_weight", 40)),
                stabilizer=request.form.get("stabilizer", "unspecified"),
                machine=request.form.get("machine", "generic"),
            )
            stitch_params.hoop_width_mm = float(request.form.get("hoop_width", 100))
            stitch_params.hoop_height_mm = float(request.form.get("hoop_height", 100))
            if method != "inkstitch":
                stitch_params.max_colors = int(
                    request.form.get("max_colors", stitch_params.max_colors)
                )
                stitch_params.preserve_colors = (
                    request.form.get("preserve_colors", "true") == "true"
                )
                for field, name in (
                    ("stitch_spacing", "satin_spacing_mm"),
                    ("running_length", "running_length_mm"),
                    ("fill_spacing", "fill_spacing_mm"),
                    ("fill_angle", "fill_angle_deg"),
                    ("max_stitch", "max_stitch_mm"),
                    ("max_satin_width", "max_satin_width_mm"),
                    ("pull_compensation", "pull_compensation_mm"),
                ):
                    setattr(
                        stitch_params,
                        name,
                        float(request.form.get(field, getattr(stitch_params, name))),
                    )
                stitch_params.underlay = request.form.get("underlay", "true") == "true"
                stitch_params.wide_mode = request.form.get("wide_mode", "fill")
                stitch_params.fill_gaps = request.form.get("fill_gaps", "true") == "true"
                stitch_params.auto_select = request.form.get("auto_select", "true") == "true"
                stitch_params.auto_fill_angle = (
                    request.form.get("auto_fill_angle", "true") == "true"
                )
                stitch_params.thread_color = request.form.get("thread_color", "#176d9c")
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
            # Keep legacy calls unchanged; comparison shares the same geometry.
            result = (
                generate(source, directory, params)
                if method == "inkstitch" and not params.fit_to_hoop
                else generate(source, directory, params, method=method, stitch_params=stitch_params)
            )
            job = directory.name

            def url(path):
                return f"/api/file/{job}/{Path(path).relative_to(directory).as_posix()}"

            files = {
                "Satin (Ink/Stitch)": url(result.satin_path),
                "Combiné (éditable)": url(result.ready_path),
                "Rungs seuls": url(result.rungs_path),
            }
            preview = directory / "preview.png"
            preview.write_bytes(
                render_preview(result.satin_path, *result.artwork_size_mm, max_dimension=1000)
            )
            artwork_preview = directory / "artwork.png"
            artwork_preview.write_bytes(
                render_preview(result.original_path, *result.artwork_size_mm, max_dimension=1000)
            )
            warnings = list(result.warnings)
            stitch_preview = None
            native_stats = None
            if method != "direct" and request.form.get("export", "false") == "true":
                try:
                    zipped = services.export_embroidery(
                        result.satin_path, directory / "embroidery.zip", stitch_params=stitch_params
                    )
                    files["Broderie (.dst/.pes)"] = url(zipped)
                    native_stats = services.native_export_stats(zipped)
                    if native_stats["max_stitch_mm"] > stitch_params.max_stitch_mm + 0.15:
                        warnings.append(
                            f"Ink/Stitch : point exporté maximal de {native_stats['max_stitch_mm']} mm malgré la limite demandée ; inspectez ce plan avant de broder."
                        )
                    stitch_preview = url(
                        services.render_stitch_preview(
                            result.satin_path,
                            directory / "stitches.png",
                            stitch_params=stitch_params,
                            align_source=True,
                        )
                    )
                    configured = services.configure_native_svg(
                        result.satin_path, directory / "inkstitch_configured.svg", stitch_params
                    )
                    files["Ink/Stitch · réglages tissu / fil"] = url(configured)
                except (RuntimeError, ValueError, OSError) as exc:
                    warnings.append(str(exc))
            direct = None
            if result.direct:
                warnings.extend(result.direct.warnings)
                direct = {
                    "files": {
                        "Direct · PES (Brother)": url(result.direct.pes_path),
                        "Direct · DST": url(result.direct.dst_path),
                        "Plan des points · SVG": url(result.direct.svg_path),
                        "Plan des points · JSON": url(result.direct.plan_path),
                    },
                    "preview": url(result.direct.preview_path),
                    "stats": result.direct.stats,
                    "decisions": result.direct.decisions,
                    "threads": result.direct.threads,
                    "coverage_basis": "quantized_top_layer"
                    if result.direct.params.auto_select
                    else "all_sewn_stitches",
                    "params": {
                        "spacing_mm": result.direct.params.satin_spacing_mm,
                        "underlay": result.direct.params.underlay,
                        "pull_compensation_mm": result.direct.params.pull_compensation_mm,
                        "fill_spacing_mm": result.direct.params.fill_spacing_mm,
                        "fabric": result.direct.params.fabric,
                        "thread_weight": result.direct.params.thread_weight,
                        "stabilizer": result.direct.params.stabilizer,
                        "machine": result.direct.params.machine,
                        "max_satin_width_mm": result.direct.params.max_satin_width_mm,
                    },
                }
            debug = {p.name: url(p) for p in (directory / "debug").glob("*.png")}
            succeeded = True
            return jsonify(
                success=True,
                job=job,
                method=method,
                direct=direct,
                native_stats=native_stats,
                files=files,
                warnings=warnings,
                preview=url(preview),
                artwork_preview=url(artwork_preview),
                artwork_svg=url(result.original_path),
                artwork_size_mm=result.artwork_size_mm,
                satin_preview=stitch_preview,
                debug_images=debug,
                converted_from=source.suffix[1:] if source.suffix.lower() != ".svg" else None,
                stats={
                    "rungs": result.rungs_count,
                    "columns": result.columns_count,
                    "running": result.running_count,
                    "coverage": round(result.coverage * 100, 1),
                    "seconds": round(
                        result.timings["total"]
                        - (result.direct.stats["seconds"] if result.direct else 0),
                        3,
                    ),
                    "total_seconds": round(result.timings["total"], 3),
                },
                params={
                    "spacing": result.params.spacing,
                    "density": result.params.density,
                    "dpi": result.params.dpi,
                },
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
            as_attachment=filename.lower().endswith((".svg", ".zip", ".pes", ".dst", ".json")),
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
