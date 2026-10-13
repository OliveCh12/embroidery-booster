import { describe, expect, it } from "vitest";
import type { DirectResult, GenerationResult } from "./types";
import { VARIANT_LABELS, variantOptions, variantReason, variantResult } from "./variants";

describe("variant selection", () => {
  const balanced = { files: { pes: "/balanced.pes", plan_json: "/balanced.json" }, warnings: ["baseline review"] } as DirectResult;
  const satin = { files: { pes: "/satin.pes", plan_json: "/satin.json" }, warnings: ["satin review", "shared input"] } as DirectResult;
  const result = { direct: balanced, job: "current", warnings: ["shared input", "baseline review"], input_warnings: ["shared input"], recommended_variant: "balanced",
    variants: [{ id: "balanced", direct: balanced, equivalent_strategies: ["uniform_satin"] }, { id: "satin_preferred", direct: satin, equivalent_strategies: [] }] } as GenerationResult;

  it("switches both machine download and playback, retaining only relevant warnings", () => {
    const selected = variantResult(result, "satin_preferred");
    expect(selected.direct.files.pes).toBe("/satin.pes");
    expect(selected.direct.files.plan_json).toBe("/satin.json");
    expect(selected.warnings).toEqual(["shared input", "satin review"]);
    expect(selected.recommended_variant).toBe("balanced");
    expect(result.direct.files.pes).toBe("/balanced.pes");
  });

  it("keeps the server recommendation for absent, deduplicated or stale selections", () => {
    expect(variantResult(result, "uniform_fill")).toBe(result);
    expect(variantResult(result, null)).toBe(result);
    const oldResult = { ...result, variants: undefined };
    expect(variantResult(oldResult, "satin_preferred")).toBe(oldResult);
  });

  it("offers deduplicated satin with an explicit identical-result label and the same files", () => {
    expect(variantOptions(result)).toEqual([
      { id: "balanced", label: "Équilibré · recommandé" },
      { id: "uniform_satin", label: "Satin uniforme · identique à Équilibré" },
      { id: "satin_preferred", label: "Priorité satin" },
    ]);
    const selected = variantResult(result, "uniform_satin");
    expect(selected.direct).toBe(balanced);
    expect(selected.direct.files.pes).toBe("/balanced.pes");
    expect(selected.direct.files.plan_json).toBe("/balanced.json");
    expect(selected.recommended_variant).toBe("balanced");
  });

  it("keeps old results readable and explains all-satin versus contour proposals", () => {
    expect(variantOptions({ ...result, variants: undefined })).toEqual([]);
    expect(VARIANT_LABELS.uniform_satin).toBe("Satin uniforme");
    expect(VARIANT_LABELS.running_outline).toContain("point droit");
    expect(variantReason("all_satin")).toContain("entièrement en satin");
    expect(variantReason("outline_only")).toContain("ne remplit pas les surfaces");
    expect(variantReason("future_rule")).toBe("future_rule");
  });
});
