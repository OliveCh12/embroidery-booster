import { describe, expect, it } from "vitest";
import { describeBackground, describeBitmapCleanup, describeNormalization, describeResampling, describeTraceAudit } from "./background-diagnostics";
import type { InputAnalysis } from "./types";

const legacy: NonNullable<InputAnalysis["background"]> = {
  mode: "auto", applied: true, reason: "border_connected_background",
  background_color: "#f2f2f2", border_confidence: 1,
  removed_fraction: 0.8643, interior_preserved_pixels: 500,
};

describe("background interpretation feedback", () => {
  it("keeps version 0.5 diagnostics readable without new model fields", () => {
    const summary = describeBackground(legacy);
    expect(summary.message).toContain("aplats intérieurs sont préservés");
    expect(summary.message).toContain("86,43 %");
    expect(summary.metrics).toEqual([{ label: "Bord compatible", value: "100 %" }]);
  });

  it("explains smooth border estimation separately from a uniform background", () => {
    const summary = describeBackground({ ...legacy, reason: "smooth_border_background", model: "smooth_gradient", border_error_rgb: 2.75, edge_refined_pixels: 21 });
    expect(summary.message).toContain("dégradé estimé depuis le bord");
    expect(summary.message).toContain("jusqu’aux contours");
    expect(summary.metrics).toContainEqual({ label: "Fond estimé", value: "Dégradé doux" });
    expect(summary.metrics).toContainEqual({ label: "Écart RGB au bord (p95)", value: "2,75" });
    expect(summary.metrics).toContainEqual({ label: "Pixels de contour affinés", value: "21" });
  });

  it("reports ambiguous backgrounds as preserved instead of claiming removal", () => {
    const summary = describeBackground({ ...legacy, applied: false, reason: "ambiguous_perimeter", border_confidence: 0, removed_fraction: 0.8, model: null });
    expect(summary.message).toContain("conservé pour préserver le dessin");
    expect(summary.message).not.toContain("% de l’image retirés");
    expect(summary.metrics).toEqual([{ label: "Bord compatible", value: "0 %" }]);
  });

  it("preserves zero fitting error and omits absent diagnostic values", () => {
    const summary = describeBackground({ ...legacy, model: "uniform", border_confidence: null, border_error_rgb: 0, edge_refined_pixels: 0 });
    expect(summary.metrics).toEqual([{ label: "Fond estimé", value: "Uni" }, { label: "Écart RGB au bord (p95)", value: "0" }]);
  });

  it("explains why a full-canvas gradient is preserved", () => {
    const summary = describeBackground({ ...legacy, applied: false, reason: "no_distinct_foreground", model: "smooth_gradient", removed_fraction: 0 });
    expect(summary.message).toBe("Aucun premier plan distinct du dégradé n’a été détecté : l’image est conservée.");
    expect(summary.metrics).toContainEqual({ label: "Fond estimé", value: "Dégradé doux" });
  });

  it("reports contour color recovery separately from contour refinement", () => {
    const summary = describeBackground({ ...legacy, edge_refined_pixels: 12, edge_recovered_pixels: 34 });
    expect(summary.metrics).toContainEqual({ label: "Pixels de contour affinés", value: "12" });
    expect(summary.metrics).toContainEqual({ label: "Pixels de contour décontaminés", value: "34" });
  });

  it("omits contour color recovery when absent in legacy diagnostics or disabled", () => {
    for (const background of [legacy, { ...legacy, edge_recovered_pixels: null }, { ...legacy, edge_recovered_pixels: 0 }]) {
      expect(describeBackground(background).metrics.some(item => item.label === "Pixels de contour décontaminés")).toBe(false);
    }
  });

  it("uses plain feedback for an unknown backend reason", () => {
    expect(describeBackground({ ...legacy, applied: false, reason: "future_background_policy" }).message).toBe("Le fond a été conservé.");
  });

  it("reports inferred monochrome counters without promising every opaque interior was preserved", () => {
    const summary = describeBackground({ ...legacy, counters_inferred: 2, counter_inference: "monochrome_broad_strokes" });
    expect(summary.message).toContain("interprétés comme des évidements");
    expect(summary.message).toContain("Désactivez le nettoyage");
    expect(summary.message).not.toContain("aplats intérieurs sont préservés");
    expect(summary.metrics).toContainEqual({ label: "Évidements monochromes", value: "2" });
  });

  it("describes a retained opaque counter without claiming it was removed or unwanted", () => {
    const summary = describeBackground({ ...legacy, counter_ambiguity: {
      reason: "opaque_interior_matches_removed_background", regions: 1, pixels: 54623,
      area_mm2: 374.86, structures: { compact_interior: 1 },
    } });
    expect(summary.message).toContain("son intention est ambiguë");
    expect(summary.message).toContain("PNG transparent");
    expect(summary.message).not.toContain("interprétés comme des évidements");
    expect(summary.metrics).toContainEqual({ label: "Aplats intérieurs ambigus", value: "1" });
  });
});

describe("bitmap ink recovery feedback", () => {
  const cleanup: NonNullable<InputAnalysis["cleanup"]> = {
    enabled: true, changed_pixels: 0, removed_pixels: 0, regions_before: 3, regions_after: 3,
    changed_area_mm2: 0, reason: "no_safe_speckles",
  };

  it("omits ink recovery when absent or disabled", () => {
    expect(describeBitmapCleanup(undefined)).toEqual([]);
    expect(describeBitmapCleanup(cleanup)).toEqual([]);
    expect(describeBitmapCleanup({ ...cleanup, dark_ink_edge_pixels: 0, alpha_fragments_removed: 0 })).toEqual([]);
  });

  it("explains gray alpha fringe recovery without claiming all grays were removed", () => {
    const messages = describeBitmapCleanup({ ...cleanup, dark_ink_edge_pixels: 1091 });
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("même fil noir");
    expect(messages[0]).toContain("gris opaques et accents colorés sont préservés");
  });

  it("reports the partial-alpha fragment separately from color cleanup", () => {
    const messages = describeBitmapCleanup({ ...cleanup, alpha_fragments_removed: 1, alpha_fragment_pixels: 1 });
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("1 fragment d’antialiasing trop fin retiré");
    expect(messages[0]).toContain("(1 pixel)");
    expect(messages[0]).toContain("détails opaques ou isolés sont préservés");
  });

  it("reports source colour refinement without promising new detail or stitch coverage", () => {
    const messages = describeBitmapCleanup({ ...cleanup, palette_refinement: {
      count: 1, masks_unchanged: true, changes: [{ from: "#c0692f", to: "#f37622" }],
    } });
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("1 couleur de fil ajustée");
    expect(messages[0]).toContain("Les contours et les découpes sont conservés");
    expect(describeBitmapCleanup({ ...cleanup, palette_refinement: {
      count: 0, masks_unchanged: true, changes: [],
    } })).toEqual([]);
  });
});

describe("contour verification feedback", () => {
  const passed = { changed_pixels: 0, topology_preserved: true, passed: true, nodes: 42, serialized_bytes: 1024 };
  const tracing = { fallback: false, render_attempts: 1, initial: passed, final: passed };

  it("does not invent verification for older results without an audit", () => {
    expect(describeTraceAudit(undefined)).toBeNull();
  });

  it("describes categorical source-grid fidelity separately from calculated stitches", () => {
    expect(describeTraceAudit(tracing)).toContain("grille de pixels");
    expect(describeTraceAudit(tracing)).toContain("avant le calcul des points");
    expect(describeTraceAudit(tracing)).not.toContain("brodable");
  });

  it("explains a repaired simplification using the final audit, even when initial topology failed", () => {
    const result = describeTraceAudit({ ...tracing, fallback: true, render_attempts: 2,
      initial: { ...passed, passed: false, topology_preserved: false, changed_pixels: 7 } });
    expect(result).toContain("Simplification du tracé réduite");
    expect(result).toContain("trous et îlots");
    expect(result).not.toContain("à vérifier");
  });

  it("does not approve changed pixels or topology just because a success flag is present", () => {
    expect(describeTraceAudit({ ...tracing, final: { ...passed, changed_pixels: 2 } })).toContain("2 pixels diffèrent");
    expect(describeTraceAudit({ ...tracing, final: { ...passed, topology_preserved: false } })).toContain("structure des trous ou îlots a changé");
    expect(describeTraceAudit({ ...tracing, final: { ...passed, passed: false } })).toContain("à vérifier");
  });
});

describe("source colour normalization feedback", () => {
  const normalization = { source_mode: "RGB", orientation_applied: false, icc_status: "absent", color_space: "assumed_sRGB" } as const;

  it("keeps normal RGB and older results quiet", () => {
    expect(describeNormalization(undefined)).toBeNull();
    expect(describeNormalization(normalization)).toBeNull();
  });

  it("reports source orientation and a real ICC conversion once", () => {
    const result = describeNormalization({ ...normalization, orientation_applied: true, icc_status: "converted", color_space: "sRGB" });
    expect(result).toBe("Orientation de l’image corrigée. Profil couleur intégré converti en sRGB.");
    expect(result).not.toContain("supposées");
  });

  it.each(["ignored_invalid", "unavailable"] as const)("does not claim an ICC conversion when status is %s", icc_status => {
    const result = describeNormalization({ ...normalization, icc_status });
    expect(result).toContain("couleurs supposées sRGB");
    expect(result).not.toContain("converti en sRGB");
  });

  it("makes the assumption explicit for an unprofiled CMYK source", () => {
    expect(describeNormalization({ ...normalization, source_mode: "CMYK" })).toContain("sans profil couleur");
  });
});

describe("source resampling feedback", () => {
  const resampling: NonNullable<InputAnalysis["resampling"]> = {
    source_pixels: [1600, 1000], working_pixels: [960, 600], reference: "source_alpha_and_literal_paints",
    resampling: "lanczos", adapted: false, detail_area_mm2: 0.01,
    passed: true, topology_preserved: true, unresolved_issues: 0,
  };

  it("keeps older results without resampling metadata silent", () => {
    expect(describeResampling(undefined)).toBeNull();
  });

  it("reports an unchanged source without inventing a reduction audit", () => {
    const summary = describeResampling({ ...resampling, source_pixels: [960, 600], reference: "source_unchanged", resampling: "none" });
    expect(summary).toEqual({ message: "Grille d’analyse : source conservée (960 × 600 px).", needsReview: false });
  });

  it("explains adapted resolution and the measured scope before stitch generation", () => {
    const summary = describeResampling({ ...resampling, adapted: true });
    expect(summary?.message).toContain("1 600 × 1 000 px → 960 × 600 px");
    expect(summary?.message).toContain("résolution ajustée pour préserver les détails");
    expect(summary?.message).toContain("Silhouette et aplats comparés");
    expect(summary?.message).not.toContain("estimés");
    expect(summary?.message).toContain("d’au moins 0,01 mm²");
    expect(summary?.message).toContain("avant le calcul des points");
    expect(summary?.message).not.toContain("brodable");
  });

  it("does not claim colour fidelity when only silhouette was compared", () => {
    const summary = describeResampling({ ...resampling, reference: "source_alpha" });
    expect(summary?.message).toContain("Silhouette comparée");
    expect(summary?.message).not.toContain("aplats");
    expect(summary?.message).not.toContain("couleurs");
  });

  it("does not flag negligible topology changes below the measured detail threshold", () => {
    const summary = describeResampling({ ...resampling, topology_preserved: false });
    expect(summary?.needsReview).toBe(false);
    expect(summary?.message).toContain("d’au moins 0,01 mm²");
    expect(summary?.message).not.toContain("trous préservés");
  });

  it("reports overlapping anomalies as measured differences instead of unique details", () => {
    const summary = describeResampling({ ...resampling, passed: false, topology_preserved: false, unresolved_issues: 3 });
    expect(summary?.needsReview).toBe(true);
    expect(summary?.message).toContain("3 écarts mesurés après réduction");
    expect(summary?.message).not.toContain("3 détails");
    expect(summary?.message).toContain("vérifiez le dessin interprété");
  });

  it("does not approve contradictory success and unresolved anomaly metadata", () => {
    const summary = describeResampling({ ...resampling, unresolved_issues: 1 });
    expect(summary?.needsReview).toBe(true);
    expect(summary?.message).toContain("1 écart mesuré");
    const failed = describeResampling({ ...resampling, passed: false });
    expect(failed?.needsReview).toBe(true);
    expect(failed?.message).toContain("Réduction à vérifier");
  });

  it("flags missing literal paints after interpretation independently of a faithful reduction", () => {
    const summary = describeResampling({ ...resampling, interpreted_palette: ["#000000"], missing_source_paints: ["#ffffff"] });
    expect(summary?.needsReview).toBe(true);
    expect(summary?.message).toContain("aplats de couleur de la source sont absents après interprétation et nettoyage");
    expect(summary?.message).not.toContain("Réduction à vérifier");
    expect(summary?.message).not.toContain("écart");
  });

  it("does not invent a paint-presence audit for unknown or unavailable palette metadata", () => {
    for (const missing_source_paints of [undefined, null, []]) {
      const summary = describeResampling({ ...resampling, missing_source_paints });
      expect(summary?.needsReview).toBe(false);
      expect(summary?.message).not.toContain("absents après interprétation");
      expect(summary?.message).not.toContain("couleurs conservées");
    }
  });

  it("distinguishes measured flat-paint cores from literal source paints", () => {
    const summary = describeResampling({ ...resampling, reference: "source_alpha_and_flat_paint_cores" });
    expect(summary?.needsReview).toBe(false);
    expect(summary?.message).toContain("Silhouette et noyaux d’aplats estimés comparés à la source");
    expect(summary?.message).toContain("d’au moins 0,01 mm²");
    expect(summary?.message).toContain("avant le calcul des points");
    expect(summary?.message).not.toContain("couleurs exactes");
    expect(summary?.message).not.toContain("fidélité totale");
  });

  it("flags an estimated missing paint without calling it an exact source colour or failed reduction", () => {
    const summary = describeResampling({ ...resampling, reference: "source_alpha_and_flat_paint_cores", missing_source_paints: ["#872087"] });
    expect(summary?.needsReview).toBe(true);
    expect(summary?.message).toContain("Des aplats estimés à partir de la source sont absents après interprétation et nettoyage");
    expect(summary?.message).not.toContain("Des aplats de couleur de la source sont absents");
    expect(summary?.message).not.toContain("Réduction à vérifier");
  });

  it("describes supported colour families as estimates, including unresolved paints", () => {
    const report = { ...resampling, reference: "source_alpha_and_paint_families" } as const;
    const summary = describeResampling(report);
    expect(summary?.message).toContain("Silhouette et familles de couleurs estimées comparées à la source");
    expect(summary?.needsReview).toBe(false);
    const missing = describeResampling({ ...report, missing_source_paints: ["#872087"] });
    expect(missing?.needsReview).toBe(true);
    expect(missing?.message).toContain("Des aplats estimés à partir de la source sont absents");
    expect(missing?.message).not.toContain("couleurs exactes");
  });

  it("does not certify colours when a family retry fails despite a successful alpha audit", () => {
    const summary = describeResampling({
      ...resampling, reference: "source_alpha", passed: true,
      paint_family_retry: { adopted: false, baseline_retained: true, unresolved_issues: 2, reason: "ambiguous_paints", source_palette: ["#872087"] },
    });
    expect(summary?.needsReview).toBe(true);
    expect(summary?.message).toContain("Silhouette comparée");
    expect(summary?.message).toContain("familles de couleurs estimées n’ont pas pu être confirmées");
    expect(summary?.message).toContain("interprétation précédente est conservée");
    expect(summary?.message).not.toContain("2 détails");
    expect(summary?.message).not.toContain("Réduction à vérifier");
  });
});
