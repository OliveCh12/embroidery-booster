import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, applyMachineProfile, applyMaterialPreset, generationForm, validateFile } from "./settings";
import type { Capabilities } from "./types";

describe("Python generation contract", () => {
  const file = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });

  it("serializes false booleans explicitly and omits automatic optional sizes", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, underlay: false, auto_adjust: false });
    expect(form.get("file")).toBe(file);
    expect(form.get("auto_adjust")).toBe("false");
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

  it("preserves color separation and the bounded palette in the request", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, max_colors: 8 });
    expect(form.get("preserve_colors")).toBe("true");
    expect(form.get("max_colors")).toBe("8");
  });

  it("sends an explicit monochrome override", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, preserve_colors: false });
    expect(form.get("preserve_colors")).toBe("false");
  });

  it("sends automatic background and stitch strategy by default", () => {
    const form = generationForm(file, DEFAULT_SETTINGS);
    expect(form.get("background_mode")).toBe("auto");
    expect(form.get("stitch_type")).toBe("auto");
    expect(form.get("raster_cleanup")).toBe("true");
  });

  it("preserves explicit background and stitch choices independently of automatic density", () => {
    const form = generationForm(file, { ...DEFAULT_SETTINGS, background_mode: "keep", stitch_type: "satin", auto_adjust: true, raster_cleanup: false });
    expect(form.get("background_mode")).toBe("keep");
    expect(form.get("stitch_type")).toBe("satin");
    expect(form.get("auto_adjust")).toBe("true");
    expect(form.get("raster_cleanup")).toBe("false");
    expect(generationForm(file, { ...DEFAULT_SETTINGS, background_mode: "remove", stitch_type: "fill" }).get("stitch_type")).toBe("fill");
    expect(generationForm(file, { ...DEFAULT_SETTINGS, stitch_type: "running" }).get("stitch_type")).toBe("running");
  });

  it("uses server machine recommendations without changing material or density", () => {
    const capabilities = { machine_profiles: { "brother-skitch-pp1": { hoop_width: 100, hoop_height: 100, max_colors: 6, max_satin_width: 7 } } } as Capabilities;
    const source = { ...DEFAULT_SETTINGS, hoop_width: 200, fabric: "stretch" as const, stabilizer: "cutaway" as const, stitch_spacing: 0.5 };
    const adjusted = applyMachineProfile(source, "brother-skitch-pp1", capabilities);
    expect(adjusted.hoop_width).toBe(100);
    expect(adjusted.max_colors).toBe(6);
    expect(adjusted.max_satin_width).toBe(7);
    expect(adjusted.stitch_spacing).toBe(0.5);
    expect(adjusted.fabric).toBe("stretch");
    expect(adjusted.stabilizer).toBe("cutaway");
    expect(source.hoop_width).toBe(200);
    const form = generationForm(file, adjusted);
    expect(form.get("machine")).toBe("brother-skitch-pp1");
    expect(form.get("max_satin_width")).toBe("7");
  });

  it("only sends direct settings without obsolete engine or guide options", () => {
    const form = generationForm(file, DEFAULT_SETTINGS);
    expect(form.get("auto_adjust")).toBe("true");
    for (const key of ["method", "export", "auto_select", "fill_gaps", "wide_mode", "spacing", "density", "debug"]) expect(form.has(key)).toBe(false);
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
    expect(validateFile({ name: "logo.pdf", size: 100 })).toContain("SVG");
  });
});
