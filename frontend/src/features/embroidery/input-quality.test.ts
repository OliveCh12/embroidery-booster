import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import { DEFAULT_SETTINGS } from "./settings";
import { inputQualityDetails, inputQualityRetryDelay, inputQualitySettings, inputQualityTitle, retryInputQuality, validInputQualitySettings, type InputQuality } from "./input-quality";

const raster: InputQuality = {
  source_type: "raster", format: "PNG", status: "caution", kind: "flat_artwork",
  source_pixels: [1200, 800], artwork_pixels: [300, 200], working_pixels: [300, 200],
  physical_size_mm: [80, 53.33], pixels_per_mm: 3.75, effective_dpi: 95.25,
  recommended_pixels: [960, 640], recommended_width_mm: 25, detail_sample_mm: 0.267,
  region_count: 3, color_count: 1, issues: ["low_resolution"],
};

describe("source quality feedback", () => {
  it("reports useful cropped pixels and a French physical-size recommendation", () => {
    const details = inputQualityDetails(raster);
    expect(details).toContain("Taille finale : 80 × 53,33 mm.");
    expect(details).toContain("Motif utile : 300 × 200 px · environ 95,25 dpi à cette taille.");
    expect(details.some(detail => detail.includes("960 × 640 px utiles") && detail.includes("sans compter les marges"))).toBe(true);
    expect(details).toContain("Pour atteindre cette résolution avec ce fichier, réduisez la largeur à environ 25 mm.");
    expect(details.some(detail => detail.includes("1 200"))).toBe(false);
  });

  it("warns about genuinely poor resolution without suggesting invented pixels", () => {
    const quality = { ...raster, status: "poor", issues: ["very_low_resolution", "many_shades"] } as const;
    expect(inputQualityTitle({ ...quality, issues: [...quality.issues] })).toContain("trop peu définie");
    expect(inputQualityDetails({ ...quality, issues: [...quality.issues] }).some(detail => detail.includes("Évitez d’agrandir artificiellement"))).toBe(true);
  });

  it("distinguishes numerous shades from unsuitable geometry or sewn quality", () => {
    const quality: InputQuality = { ...raster, status: "caution", issues: ["many_shades", "palette_reduced"] };
    expect(inputQualityTitle(quality)).toBe("Nombreuses nuances à simplifier");
    expect(inputQualityDetails(quality).some(detail => detail.includes("version en aplats"))).toBe(true);
    expect(inputQualityDetails(quality).some(detail => detail.includes("regroupées en couleurs de fil"))).toBe(true);
  });

  it("keeps JPEG information separate from the backend adequacy status", () => {
    const quality: InputQuality = { ...raster, status: "good", format: "JPEG", issues: ["lossy_source"] };
    expect(inputQualityTitle(quality)).toBe("Définition adaptée à la taille demandée");
    expect(inputQualityDetails(quality).some(detail => detail.includes("susceptible d’altérer"))).toBe(true);
  });

  it("omits redundant resolution targets and never suggests enlarging a sufficiently defined input", () => {
    const details = inputQualityDetails({ ...raster, status: "good", pixels_per_mm: 48, effective_dpi: 1219.2, recommended_width_mm: 319, issues: [] });
    expect(details.some(detail => detail.includes("Cible conseillée"))).toBe(false);
    expect(details.some(detail => detail.includes("réduisez la largeur"))).toBe(false);
    expect(inputQualityDetails({ ...raster, pixels_per_mm: 12, recommended_width_mm: 80 }).some(detail => detail.includes("Cible conseillée"))).toBe(false);
  });

  it("does not recommend a physical width below the supported one millimetre minimum", () => {
    const details = inputQualityDetails({ ...raster, status: "poor", recommended_width_mm: 0.25, issues: ["very_low_resolution"] });
    expect(details.some(detail => detail.includes("réduisez la largeur à environ"))).toBe(false);
    expect(details.some(detail => detail.includes("Évitez d’agrandir artificiellement"))).toBe(true);
  });

  it("does not invent raster resolution for a genuine vector source", () => {
    const quality: InputQuality = { ...raster, source_type: "vector", format: "SVG", kind: "vector", status: "good",
      source_pixels: null, artwork_pixels: null, working_pixels: null, pixels_per_mm: null, effective_dpi: null,
      recommended_pixels: null, recommended_width_mm: null, detail_sample_mm: null, issues: [] };
    expect(inputQualityTitle(quality)).toBe("Source vectorielle adaptée");
    expect(inputQualityDetails(quality)).toEqual(["Taille finale : 80 × 53,33 mm."]);
    expect(inputQualityDetails({ ...quality, issues: ["svg_background_retraced"] }).some(detail => detail.includes("rasterisé puis retracé"))).toBe(true);
  });

  it("ignores unknown diagnostic codes and avoids repeated explanations", () => {
    const details = inputQualityDetails({ ...raster, issues: ["low_resolution", "low_resolution", "future_issue"] });
    expect(details.filter(detail => detail.includes("définition est limitée"))).toHaveLength(1);
    expect(details.some(detail => detail.includes("future_issue"))).toBe(false);
  });
});

describe("source quality request scope", () => {
  it("reacts to interpretation and final size, independently of sewing density", () => {
    const baseline = inputQualitySettings(DEFAULT_SETTINGS);
    expect(inputQualitySettings({ ...DEFAULT_SETTINGS, density_percent: 120, stitch_type: "satin", fill_angle: 90, underlay: false })).toEqual(baseline);
    expect(inputQualitySettings({ ...DEFAULT_SETTINGS, design_width: 60 })).not.toEqual(baseline);
    expect(inputQualitySettings({ ...DEFAULT_SETTINGS, background_mode: "keep" })).not.toEqual(baseline);
    expect(inputQualitySettings({ ...DEFAULT_SETTINGS, max_colors: 2 })).not.toEqual(baseline);
    expect(inputQualitySettings({ ...DEFAULT_SETTINGS, raster_cleanup: false })).not.toEqual(baseline);
  });

  it("does not upload partial, out-of-range or invalid image settings", () => {
    expect(validInputQualitySettings(DEFAULT_SETTINGS)).toBe(true);
    for (const settings of [
      { ...DEFAULT_SETTINGS, design_width: NaN }, { ...DEFAULT_SETTINGS, hoop_width: 101 },
      { ...DEFAULT_SETTINGS, max_colors: 0 }, { ...DEFAULT_SETTINGS, max_colors: 1.5 },
      { ...DEFAULT_SETTINGS, raster_threshold: NaN }, { ...DEFAULT_SETTINGS, raster_threshold: -1 },
    ]) expect(validInputQualitySettings(settings)).toBe(false);
    expect(validInputQualitySettings({ ...DEFAULT_SETTINGS, machine: "generic", hoop_width: 200, raster_threshold: 0 })).toBe(true);
  });
});

describe("temporary source-analysis congestion", () => {
  it("retries only two temporary 503 failures, with bounded delays", () => {
    const busy = new ApiError("Une analyse est déjà en cours.", 503);
    expect(retryInputQuality(0, busy)).toBe(true);
    expect(retryInputQuality(1, busy)).toBe(true);
    expect(retryInputQuality(2, busy)).toBe(false);
    expect(inputQualityRetryDelay(0)).toBe(500);
    expect(inputQualityRetryDelay(1)).toBe(1000);
  });

  it("does not retry invalid inputs, server failures, network loss or aborted requests", () => {
    for (const status of [0, 400, 404, 413, 422, 500]) {
      expect(retryInputQuality(0, new ApiError("Analyse impossible.", status))).toBe(false);
    }
    expect(retryInputQuality(0, new Error("Network failure"))).toBe(false);
    expect(retryInputQuality(0, new DOMException("Aborted", "AbortError"))).toBe(false);
  });

  it("recovers after the previous worker finishes without surfacing an unavailable result", async () => {
    vi.useFakeTimers();
    const client = new QueryClient();
    try {
      const queryFn = vi.fn().mockRejectedValueOnce(new ApiError("Worker busy", 503)).mockResolvedValue(raster);
      const result = client.fetchQuery({ queryKey: ["analysis-retry"], queryFn, retry: retryInputQuality, retryDelay: inputQualityRetryDelay });
      await vi.advanceTimersByTimeAsync(499);
      expect(queryFn).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(await result).toBe(raster);
      expect(queryFn).toHaveBeenCalledTimes(2);
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });

  it("stops at three total requests when the worker remains occupied", async () => {
    vi.useFakeTimers();
    const client = new QueryClient();
    try {
      const busy = new ApiError("Worker busy", 503);
      const queryFn = vi.fn().mockRejectedValue(busy);
      const result = client.fetchQuery({ queryKey: ["analysis-retry-limit"], queryFn, retry: retryInputQuality, retryDelay: inputQualityRetryDelay });
      const failure = expect(result).rejects.toBe(busy);
      await vi.advanceTimersByTimeAsync(1500);
      await failure;
      expect(queryFn).toHaveBeenCalledTimes(3);
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });
});
