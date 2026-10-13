import { describe, expect, it } from "vitest";
import { describeBackground, describeBitmapCleanup, describeNormalization, describeTraceAudit } from "./background-diagnostics";
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
