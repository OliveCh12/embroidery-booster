"""Bounded automatic interpretations, ranked by audited sewing geometry."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field, replace

import numpy as np

from .digitizer import digitize, prepare_digitizing
from .params import StitchParams
from .planner import StitchPlan
from .quality import coverage_needs_review

MAX_COMPARISON_REGIONS = 256


@dataclass
class PlannedVariant:
    id: str
    plan: StitchPlan
    layers: list[dict]
    quality: dict
    reasons: list[str]
    seconds: float
    equivalent_strategies: list[str] = field(default_factory=list)


def _quality(plan, layers):
    stats = plan.stats
    areas = {
        method: round(sum(d.get("area_mm2", 0) for d in plan.decisions if d["method"] == method), 2)
        for method in ("satin", "fill", "running", "omitted")
    }
    return {
        **{
            key: stats.get(key, 0)
            for key in (
                "coverage",
                "structural_coverage",
                "structural_missing_mm2",
                "largest_gap_mm2",
                "uncovered_max_mm",
                "spill_mm2",
                "unsafe_connections",
                "crowded_satin_penetrations",
                "short_stitches",
                "omitted_regions",
                "omitted_colors",
                "satin_regions",
                "fill_regions",
                "running_regions",
                "trims",
                "jump_length_mm",
            )
        },
        "failed_coverage_layers": sum(coverage_needs_review(layer) for layer in layers),
        "status": plan.analysis.get("quality_status", "needs_review"),
        "method_area_mm2": areas,
        "ranking_basis": "quantized_geometry_only",
    }


def _safety_rank(quality):
    hazards = sum(
        quality[key]
        for key in ("unsafe_connections", "crowded_satin_penetrations", "short_stitches")
    )
    # Ignore sub-grid differences between viable interpretations. Count and
    # appearance alone cannot justify a coverage loss or a crowded satin fan.
    return (
        bool(hazards),
        hazards,
        quality["status"] != "geometric_checks_passed",
        quality["omitted_colors"],
        math.floor(quality["method_area_mm2"]["omitted"] / 0.05 + 1e-9),
        quality["omitted_regions"],
        quality["failed_coverage_layers"],
        math.floor(max(0, quality["largest_gap_mm2"] - 0.05) / 0.05 + 1e-9),
        math.floor(quality["structural_missing_mm2"] / 0.05 + 1e-9)
        if quality["failed_coverage_layers"]
        else 0,
        math.floor(max(0, quality["uncovered_max_mm"] - 0.25) / 0.1 + 1e-9)
        if quality["failed_coverage_layers"]
        else 0,
    )


def _safe_satin_improvement(candidate, incumbent):
    proposed, current = candidate.quality, incumbent.quality
    if (
        proposed["status"] != "geometric_checks_passed"
        or current["status"] != "geometric_checks_passed"
    ):
        return False
    if any(
        quality[key]
        for quality in (proposed, current)
        for key in (
            "unsafe_connections",
            "crowded_satin_penetrations",
            "short_stitches",
            "omitted_colors",
            "omitted_regions",
            "failed_coverage_layers",
        )
    ):
        return False
    total_area = sum(current["method_area_mm2"].values())
    extra_satin = proposed["method_area_mm2"]["satin"] - current["method_area_mm2"]["satin"]
    return (
        extra_satin >= max(1.0, 0.02 * total_area)
        and proposed["coverage"] >= current["coverage"] - 0.005
        and proposed["structural_coverage"] >= current["structural_coverage"] - 0.0001
        and proposed["structural_missing_mm2"] <= current["structural_missing_mm2"] + 0.01
        and proposed["largest_gap_mm2"] <= current["largest_gap_mm2"] + 0.01
        and proposed["spill_mm2"] <= current["spill_mm2"] + max(0.25, 0.02 * total_area)
        and proposed["trims"] <= current["trims"] + max(2, current["trims"] * 0.1)
        and proposed["jump_length_mm"]
        <= current["jump_length_mm"] + max(10, 0.1 * current["jump_length_mm"])
    )


def recommend_variant(variants: list[PlannedVariant]) -> str:
    """Keep balanced on equivalent diagnostics; prefer substantive, audited satin."""
    best = variants[0]
    for candidate in variants[1:]:
        if candidate.id == "running_outline":
            continue
        proposed_rank, current_rank = _safety_rank(candidate.quality), _safety_rank(best.quality)
        if proposed_rank < current_rank:
            best = candidate
        elif (
            proposed_rank == current_rank
            and candidate.id in ("satin_preferred", "uniform_satin")
            and _safe_satin_improvement(candidate, best)
        ):
            best = candidate
    return best.id


def _fingerprint(plan):
    digest = hashlib.sha256(np.asarray(plan.commands, dtype="<i4").tobytes())
    digest.update("\0".join(plan.threads).encode("ascii"))
    return digest.digest()


def _complete_satin(variant):
    quality = variant.quality
    return (
        quality["status"] == "geometric_checks_passed"
        and variant.plan.decisions
        and all(d["method"] == "satin" for d in variant.plan.decisions)
        and not any(
            quality[key]
            for key in (
                "unsafe_connections",
                "crowded_satin_penetrations",
                "short_stitches",
                "omitted_regions",
                "omitted_colors",
                "failed_coverage_layers",
            )
        )
    )


def plan_variants(svg, params: StitchParams):
    """Compare supported styles on one artwork; retain machine safety gates."""
    if params.stitch_type != "auto":
        raise ValueError("Automatic strategy comparison requires stitch_type='auto'.")
    started = time.perf_counter()
    prepared = prepare_digitizing(svg, params)
    preparation_seconds = time.perf_counter() - started
    policies = (
        ("balanced", replace(params, auto_strategy="balanced")),
        ("satin_preferred", replace(params, auto_strategy="satin_preferred")),
        ("uniform_fill", replace(params, stitch_type="fill", auto_fill_angle=False)),
        ("uniform_satin", replace(params, stitch_type="satin")),
        ("running_outline", replace(params, stitch_type="running")),
    )
    variants, skipped, fingerprints = [], [], {}
    comparison_limited = prepared.analysis["region_count"] > MAX_COMPARISON_REGIONS
    if comparison_limited:
        # Each strategy independently audits its regions and complete plan.
        # Bound that additional work by geometry, never by a timing race or a
        # change to the primary design's colours, density or stitch safety.
        skipped.extend(
            {
                "id": variant_id,
                "reason": "comparison_region_budget",
                "region_count": prepared.analysis["region_count"],
                "limit": MAX_COMPARISON_REGIONS,
            }
            for variant_id, _ in policies[1:]
        )
        policies = policies[:1]
    for variant_id, variant_params in policies:
        if variant_id == "uniform_satin":
            complete = next((v for v in variants if _complete_satin(v)), None)
            if complete is not None:
                # A fully audited satin plan already fulfills this request.
                # Reuse it instead of generating an identical interpretation.
                complete.equivalent_strategies.append(variant_id)
                continue
        started = time.perf_counter()
        try:
            plan, layers = digitize(svg, variant_params, prepared=prepared)
        except ValueError as exc:
            if variant_id == "balanced":
                raise
            skipped.append({"id": variant_id, "reason": str(exc)})
            continue
        fingerprint = _fingerprint(plan)
        if fingerprint in fingerprints:
            fingerprints[fingerprint].equivalent_strategies.append(variant_id)
            continue
        reasons = ["shared_interpretation", "audit_first"]
        if variant_id == "uniform_fill":
            reasons.append("uniform_texture")
        elif variant_id == "uniform_satin":
            reasons.append("all_satin")
        elif variant_id == "running_outline":
            reasons.append("outline_only")
        elif variant_id == "satin_preferred":
            reasons.append("qualified_columns")
        else:
            reasons.append("balanced_default")
        if plan.analysis["quality_status"] == "needs_review":
            reasons.append("needs_review")
        quality = _quality(plan, layers)
        quality["purpose"] = "outline" if variant_id == "running_outline" else "surface"
        candidate = PlannedVariant(
            variant_id,
            plan,
            layers,
            quality,
            reasons,
            time.perf_counter()
            - started
            + (preparation_seconds if variant_id == "balanced" else 0),
        )
        variants.append(candidate)
        fingerprints[fingerprint] = candidate
    recommended = recommend_variant(variants)
    selected = next(v for v in variants if v.id == recommended)
    if recommended in ("satin_preferred", "uniform_satin") and _safe_satin_improvement(
        selected, variants[0]
    ):
        selected.reasons.append("safe_satin_gain")
    elif recommended != "balanced":
        selected.reasons.append("improved_geometry")
    elif comparison_limited:
        selected.reasons.append("comparison_limited")
    else:
        selected.reasons.append("no_meaningful_gain")
    return variants, recommended, skipped
