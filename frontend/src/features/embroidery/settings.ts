import type { Capabilities, Fabric, GenerationSettings, Machine, ThreadWeight } from "./types";

export const DEFAULT_SETTINGS: GenerationSettings = {
  method: "direct", fabric: "custom", thread_weight: "40", stabilizer: "unspecified",
  design_width: null, hoop_width: 100, hoop_height: 100, fit_to_hoop: true,
  stitch_spacing: 0.4, fill_spacing: 0.4, pull_compensation: 0.15,
  running_length: 2.5, max_stitch: 8, underlay: true,
  auto_select: true, auto_fill_angle: true, fill_angle: 45, fill_gaps: true,
  wide_mode: "fill", export: false, auto_optimize: true, spacing: 3,
  density: 1, dpi: 150, debug: false, raster_threshold: null, raster_invert: false,
  max_colors: 12,
  preserve_colors: true,
  machine: "generic",
  max_satin_width: 8,
};

export function applyMachineProfile(settings: GenerationSettings, machine: Machine, capabilities: Capabilities): GenerationSettings {
  const profile = capabilities.machine_profiles[machine];
  return { ...settings, machine, hoop_width: profile.hoop_width, hoop_height: profile.hoop_height,
    max_colors: profile.max_colors, max_satin_width: profile.max_satin_width };
}

export function applyMaterialPreset(settings: GenerationSettings, fabric: Fabric, weight: ThreadWeight, capabilities?: Capabilities): GenerationSettings {
  const preset = capabilities?.material_presets[fabric][weight];
  return { ...settings, fabric, thread_weight: weight, ...preset,
    underlay: fabric === "custom" ? settings.underlay : (preset?.underlay ?? settings.underlay) };
}

export function generationForm(file: File, settings: GenerationSettings): FormData {
  const data = new FormData();
  data.set("file", file);
  for (const [key, value] of Object.entries(settings)) {
    if (value !== null) data.set(key, String(value));
  }
  if (settings.method === "direct") data.set("export", "false");
  return data;
}

export function validateFile(file: Pick<File, "name" | "size">): string | null {
  if (file.size > 10 * 1024 * 1024) return "Le fichier dépasse la limite de 10 Mio.";
  if (!/\.(svg|png|jpe?g|webp|bmp|gif|tiff?|pdf|eps|ps|ai)$/i.test(file.name))
    return "Choisissez un SVG ou une image PNG, JPEG, WebP, TIFF, GIF ou BMP.";
  if (!file.size) return "Ce fichier est vide.";
  return null;
}
