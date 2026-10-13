import { describe, expect, it } from "vitest";
import { describeBackground, describeBitmapCleanup } from "./background-diagnostics";
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
