import { describe, expect, it } from "vitest";
import { describeDecision } from "./decision-diagnostics";
import type { Decision } from "./types";

const decision: Decision = { component: 1, method: "satin", reason: "complete_regular_column", width_mm: 2, fill_angle_deg: null };
const profile: NonNullable<Decision["shape_profile"]> = { kind: "outline", narrow: true, safe_satin_width_mm: 7, hole_count: 1, area_width_ratio: 8 };

describe("region decision feedback", () => {
  it("keeps older decisions readable without inventing a shape or rail algorithm", () => {
    const context = describeDecision(decision);
    expect(context).toBe("Colonnes satin vérifiées sur les points machine.");
    expect(context).not.toContain("MAT");
    expect(context).not.toContain("rendu cousu");
  });

  it.each([
    ["outline", "Forme à contreforme"], ["stroke", "Trait allongé"], ["round_detail", "Détail arrondi"],
    ["compact", "Forme compacte"], ["wide_surface", "Surface large"],
  ] as const)("uses the declared geometry label for %s without inferring the accepted strategy", (kind, label) => {
    const context = describeDecision({ ...decision, method: "fill", reason: "requested_uniform_fill", shape_profile: { ...profile, kind } });
    expect(context).toBe(`${label} · Tatami demandé.`);
    expect(context).not.toContain("satin vérifié");
  });

  it("describes a qualified directional satin separately from ordinary columns", () => {
    expect(describeDecision({ ...decision, reason: "complete_directional_columns" })).toContain("Satin directionnel vérifié sur les points machine");
    expect(describeDecision({ ...decision, reason: "complete_split_columns" })).toContain("divisé en colonnes vérifiées");
  });

  it("reports the actual satin width limit rather than hardcoding a machine recommendation", () => {
    expect(describeDecision({ ...decision, method: "fill", reason: "exceeds_safe_satin_width", shape_profile: { ...profile, safe_satin_width_mm: 6.8 } })).toContain("(6,8 mm)");
    expect(describeDecision({ ...decision, method: "fill", reason: "exceeds_safe_satin_width", safe_satin_width_mm: 7.5 })).toContain("(7,5 mm)");
    for (const safe_satin_width_mm of [undefined, NaN, Infinity, -1]) {
      expect(describeDecision({ ...decision, method: "fill", reason: "exceeds_safe_satin_width", safe_satin_width_mm })).toBe("Limite de largeur satin dépassée.");
    }
  });

  it("distinguishes rejected machine coverage from rejected rail geometry", () => {
    const incomplete = describeDecision({ ...decision, method: "fill", reason: "satin_top_layer_incomplete" });
    expect(incomplete).toContain("Satin non retenu");
    expect(incomplete).toContain("couverture ou sécurité");
    expect(incomplete).not.toContain("vérifié");
    expect(describeDecision({ ...decision, method: "fill", reason: "satin_geometry_rejected" })).toContain("géométrie incompatible");
    expect(describeDecision({ ...decision, method: "fill", reason: "incomplete_or_broad_column" })).toContain("Rails satin incomplets ou trop larges");
  });

  it("distinguishes colour texture harmonization from counterpart consensus", () => {
    expect(describeDecision({ ...decision, method: "fill", reason: "coherent_color_fill" })).toContain("autres surfaces de cette couleur");
    expect(describeDecision({ ...decision, method: "fill", reason: "equivalent_region_consensus" })).toBe("Stratégie commune aux régions équivalentes.");
  });

  it("explains a fidelity refusal without claiming that the satin was unsafe", () => {
    expect(describeDecision({ ...decision, method: "fill", reason: "satin_fidelity_regression" })).toBe("Tatami conservé : le gain de fidélité du satin n’est pas confirmé.");
    expect(describeDecision({ ...decision, method: "satin", reason: "satin_fidelity_regression" })).toBeNull();
  });

  it("does not describe requested running outlines as solid coverage", () => {
    expect(describeDecision({ ...decision, method: "running", reason: "requested_running_contour" })).toContain("sans remplissage de surface");
    expect(describeDecision({ ...decision, method: "running", reason: "below_satin_width" })).toContain("trop fin pour le satin");
    expect(describeDecision({ ...decision, method: "fill", reason: "running_top_layer_incomplete" })).toContain("Point droit non retenu");
  });

  it("distinguishes an omitted small detail from an invalid machine geometry", () => {
    expect(describeDecision({ ...decision, method: "omitted", reason: "below_machine_resolution" })).toContain("résolution utile");
    const geometry = describeDecision({ ...decision, method: "omitted", reason: "machine_geometry_rejected" });
    expect(geometry).toContain("Géométrie rejetée");
    expect(geometry).not.toContain("petit");
  });

  it("does not approve a contradictory accepted-strategy reason", () => {
    expect(describeDecision({ ...decision, method: "fill", reason: "complete_directional_columns" })).toBeNull();
    expect(describeDecision({ ...decision, method: "satin", reason: "coherent_color_fill" })).toBeNull();
  });

  it("keeps unknown reasons and future fields quiet", () => {
    const future = { ...decision, reason: "future_geometry_rule", future_field: true };
    expect(describeDecision(future)).toBeNull();
    expect(describeDecision({ ...future, shape_profile: profile })).toBe("Forme à contreforme");
    for (const kind of ["future_shape", "constructor", "__proto__"]) {
      expect(describeDecision({ ...future, shape_profile: { ...profile, kind } } as Decision)).toBeNull();
    }
  });
});
