import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, applyMaterialPreset, generationForm, validateFile } from "./settings";
import type { Capabilities } from "./types";

describe("Python generation contract", () => {
  const file = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });

  it("serializes false booleans explicitly and omits automatic optional sizes", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, underlay: false, debug: false });
    expect(form.get("file")).toBe(file);
    expect(form.get("method")).toBe("direct");
    expect(form.get("underlay")).toBe("false");
    expect(form.get("fit_to_hoop")).toBe("true");
    expect(form.has("design_width")).toBe(false);
    expect(form.has("raster_threshold")).toBe(false);
  });

  it("preserves a zero manual threshold and explicit physical sizing", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, raster_threshold: 0, design_width: 65 });
    expect(form.get("raster_threshold")).toBe("0");
    expect(form.get("design_width")).toBe("65");
  });

  it("only requests native export when using the editable path", () => {
    expect(generationForm(file, { ...DEFAULT_SETTINGS, export: true }).get("export")).toBe("false");
    expect(generationForm(file, { ...DEFAULT_SETTINGS, method: "both", export: true }).get("export")).toBe("true");
  });

  it("uses server presets while preserving unrelated settings and manual custom underlay", () => {
    const capabilities = { material_presets: { stretch: { "60": { stitch_spacing: 0.333, fill_spacing: 0.444, pull_compensation: 0.22, underlay: true } }, custom: { "40": { stitch_spacing: 0.4, fill_spacing: 0.4, pull_compensation: 0.15, underlay: true } } } } as Capabilities;
    const source = { ...DEFAULT_SETTINGS, design_width: 70, underlay: false, stabilizer: "cutaway" as const };
    const adjusted = applyMaterialPreset(source, "stretch", "60", capabilities);
    expect(adjusted.stitch_spacing).toBe(0.333);
    expect(adjusted.fill_spacing).toBe(0.444);
    expect(adjusted.underlay).toBe(true);
    expect(adjusted.design_width).toBe(70);
    expect(adjusted.stabilizer).toBe("cutaway");
    expect(source.underlay).toBe(false);
    expect(applyMaterialPreset(source, "custom", "40", capabilities).underlay).toBe(false);
  });

  it("blocks oversized, empty or unsupported files before upload", () => {
    expect(validateFile({ name: "photo.JPG", size: 1024 })).toBeNull();
    expect(validateFile({ name: "photo.TIFF", size: 1024 })).toBeNull();
    expect(validateFile({ name: "logo.svg", size: 0 })).toContain("vide");
    expect(validateFile({ name: "logo.svg", size: 10 * 1024 * 1024 + 1 })).toContain("10 Mio");
    expect(validateFile({ name: "logo.exe", size: 100 })).toContain("SVG");
  });
});
