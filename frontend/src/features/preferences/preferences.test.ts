import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS } from "../embroidery/settings";
import type { Capabilities, MaterialPreset, ThreadWeight } from "../embroidery/types";
import { applyPreferences, DEFAULT_PREFERENCES, parsePreferences, PREFS_STORAGE_KEY } from "./preferences";

const reference: Record<ThreadWeight, MaterialPreset> = {
  "30": { stitch_spacing: 0.5, fill_spacing: 0.5, pull_compensation: 0.15, underlay: true },
  "40": { stitch_spacing: 0.4, fill_spacing: 0.4, pull_compensation: 0.15, underlay: true },
  "60": { stitch_spacing: 0.3, fill_spacing: 0.3, pull_compensation: 0.15, underlay: true },
};
const capabilities: Capabilities = {
  engine: "direct", direct: true, direct_formats: ["pes", "dst"], accepted_formats: ["svg", "png"], quality_report: true,
  machine_profiles: {
    generic: { label: "Cadre personnalisable", hoop_width: 200, hoop_height: 130, max_colors: 12, max_satin_width: 8, max_area_mm: null, stitches_per_minute: 400 },
    "brother-skitch-pp1": { label: "Brother Skitch PP1", hoop_width: 100, hoop_height: 100, max_colors: 6, max_satin_width: 7, max_area_mm: 100, stitches_per_minute: 400 },
  },
  material_presets: {
    custom: reference, stable: reference, textured: reference,
    stretch: { ...reference, "60": { stitch_spacing: 0.338, fill_spacing: 0.338, pull_compensation: 0.25, underlay: true } },
  },
};

describe("application preferences", () => {
  it("starts from the generation defaults and stores only persistent equipment choices", () => {
    expect(DEFAULT_PREFERENCES).toEqual({ machine: "brother-skitch-pp1", fabric: "custom", thread_weight: "40", stabilizer: "unspecified" });
    expect(DEFAULT_PREFERENCES.machine).toBe(DEFAULT_SETTINGS.machine);
    expect(PREFS_STORAGE_KEY).toBe("embroidery-booster.preferences.v1");
    expect(Object.keys(DEFAULT_PREFERENCES).sort()).toEqual(["fabric", "machine", "stabilizer", "thread_weight"]);
  });

  it.each([null, "", "{", "null", "[]", "true", "42", '"legacy"'])(
    "recovers from missing or corrupted storage %s", raw => {
      expect(parsePreferences(raw)).toEqual(DEFAULT_PREFERENCES);
      expect(parsePreferences(raw)).not.toBe(DEFAULT_PREFERENCES);
    }
  );

  it("round-trips supported equipment and textile choices", () => {
    const preferences = { machine: "generic", fabric: "stretch", thread_weight: "60", stabilizer: "cutaway" } as const;
    expect(parsePreferences(JSON.stringify(preferences))).toEqual(preferences);
  });

  it("replaces unsupported identifiers while retaining valid individual fields", () => {
    expect(parsePreferences(JSON.stringify({ machine: "old-machine", fabric: "stretch", thread_weight: "100", stabilizer: "cutaway" }))).toEqual({
      ...DEFAULT_PREFERENCES, fabric: "stretch", stabilizer: "cutaway",
    });
    expect(parsePreferences(JSON.stringify({ machine: "generic", fabric: "denim", thread_weight: 60, stabilizer: "none" }))).toEqual({
      ...DEFAULT_PREFERENCES, machine: "generic",
    });
  });

  it("discards previous artwork, exports and advanced generation values from old payloads", () => {
    const payload = { ...DEFAULT_PREFERENCES, density_percent: 120, stitch_type: "satin", file: "private-logo.png", exports: ["old.pes"], job: "old-job" };
    expect(parsePreferences(JSON.stringify(payload))).toEqual(DEFAULT_PREFERENCES);
    expect(parsePreferences('{"version":0,"settings":{"machine":"generic"}}')).toEqual(DEFAULT_PREFERENCES);
  });

  it("returns independent preferences without changing the shared defaults", () => {
    const preferences = parsePreferences(null);
    preferences.stabilizer = "washaway";
    expect(DEFAULT_PREFERENCES.stabilizer).toBe("unspecified");
    expect(parsePreferences(null).stabilizer).toBe("unspecified");
  });

  it("applies machine recommendations and material presets to the next atelier", () => {
    const preferences = { machine: "generic", fabric: "stretch", thread_weight: "60", stabilizer: "cutaway" } as const;
    const source = { ...DEFAULT_SETTINGS, design_width: 65, underlay: false, density_percent: 110, stitch_type: "satin" as const };
    const adjusted = applyPreferences(source, preferences, capabilities);
    expect(adjusted).toMatchObject({ ...preferences, hoop_width: 200, hoop_height: 130, max_colors: 12, max_satin_width: 8,
      stitch_spacing: 0.338, fill_spacing: 0.338, pull_compensation: 0.25, underlay: true });
    expect(adjusted.design_width).toBe(65);
    expect(adjusted.density_percent).toBe(110);
    expect(adjusted.stitch_type).toBe("satin");
    expect(source.underlay).toBe(false);
    expect(source.machine).toBe("brother-skitch-pp1");
    expect(preferences).toEqual({ machine: "generic", fabric: "stretch", thread_weight: "60", stabilizer: "cutaway" });
  });

  it("restores the PP1 profile while preserving explicit custom underlay", () => {
    const adjusted = applyPreferences({ ...DEFAULT_SETTINGS, machine: "generic", hoop_width: 200, max_colors: 12, underlay: false }, DEFAULT_PREFERENCES, capabilities);
    expect(adjusted).toMatchObject({ ...DEFAULT_PREFERENCES, hoop_width: 100, hoop_height: 100, max_colors: 6, max_satin_width: 7, stitch_spacing: 0.4, fill_spacing: 0.4, underlay: false });
  });
});
