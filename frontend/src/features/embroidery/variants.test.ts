import { describe, expect, it } from "vitest";
import type { DirectResult, GenerationResult } from "./types";
import { variantResult } from "./variants";

describe("variant selection", () => {
  const balanced = { files: { pes: "/balanced.pes", plan_json: "/balanced.json" }, warnings: ["baseline review"] } as DirectResult;
  const satin = { files: { pes: "/satin.pes", plan_json: "/satin.json" }, warnings: ["satin review", "shared input"] } as DirectResult;
  const result = { direct: balanced, job: "current", warnings: ["shared input", "baseline review"], input_warnings: ["shared input"], recommended_variant: "balanced",
    variants: [{ id: "balanced", direct: balanced }, { id: "satin_preferred", direct: satin }] } as GenerationResult;

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
});
