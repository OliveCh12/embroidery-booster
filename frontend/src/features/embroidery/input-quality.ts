"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";
import { ApiError, apiRequest } from "../../lib/api";
import { formatNumber } from "../../lib/format";
import { DEFAULT_SETTINGS, generationForm } from "./settings";
import type { GenerationSettings, InputAnalysis } from "./types";

export interface InputQuality {
  source_type: "vector" | "raster";
  format: string;
  status: "good" | "caution" | "poor";
  kind: "vector" | "flat_artwork" | "many_shades" | "monochrome";
  source_pixels: [number, number] | null;
  artwork_pixels: [number, number] | null;
  working_pixels: [number, number] | null;
  physical_size_mm: [number, number];
  pixels_per_mm: number | null;
  effective_dpi: number | null;
  recommended_pixels: [number, number] | null;
  recommended_width_mm: number | null;
  detail_sample_mm: number | null;
  region_count: number | null;
  color_count: number | null;
  issues: string[];
}

export function inputQualitySettings(settings: GenerationSettings) {
  return {
    machine: settings.machine,
    design_width: settings.design_width,
    hoop_width: settings.hoop_width,
    hoop_height: settings.hoop_height,
    fit_to_hoop: settings.fit_to_hoop,
    raster_threshold: settings.raster_threshold,
    raster_invert: settings.raster_invert,
    background_mode: settings.background_mode,
    raster_cleanup: settings.raster_cleanup,
    preserve_colors: settings.preserve_colors,
    max_colors: settings.max_colors,
  };
}

export function validInputQualitySettings(settings: GenerationSettings) {
  const inRange = (value: number, min: number, max: number) => Number.isFinite(value) && value >= min && value <= max;
  const hoopLimit = settings.machine === "brother-skitch-pp1" ? 100 : 500;
  return (settings.design_width === null || inRange(settings.design_width, 1, 500))
    && inRange(settings.hoop_width, 10, hoopLimit) && inRange(settings.hoop_height, 10, hoopLimit)
    && Number.isInteger(settings.max_colors) && inRange(settings.max_colors, 1, 32)
    && (settings.raster_threshold === null || Number.isInteger(settings.raster_threshold) && inRange(settings.raster_threshold, 0, 255));
}

export function inputQualityTitle(quality: InputQuality) {
  if (quality.status === "poor") return "Source trop peu définie à cette taille";
  if (quality.issues.includes("many_shades")) return "Nombreuses nuances à simplifier";
  if (quality.status === "caution") return "Source à améliorer pour des contours précis";
  return quality.source_type === "vector" ? "Source vectorielle adaptée" : "Définition adaptée à la taille demandée";
}

export function inputQualityDetails(quality: InputQuality): string[] {
  const dimensions = (values: [number, number], unit: string) => `${values.map(value => formatNumber(value)).join(" × ")} ${unit}`;
  const details = [`Taille finale : ${dimensions(quality.physical_size_mm, "mm")}.`];
  if (quality.artwork_pixels) details.push(`Motif utile : ${dimensions(quality.artwork_pixels, "px")}${quality.effective_dpi != null ? ` · environ ${formatNumber(quality.effective_dpi)} dpi à cette taille` : ""}.`);
  if (quality.recommended_pixels && quality.pixels_per_mm != null && quality.pixels_per_mm < 12) details.push(`Cible conseillée pour des contours fins : ${dimensions(quality.recommended_pixels, "px")} utiles (environ 305 dpi), sans compter les marges.`);
  if (quality.recommended_width_mm != null && quality.recommended_width_mm >= 1 && quality.physical_size_mm[0] > quality.recommended_width_mm) details.push(`Pour atteindre cette résolution avec ce fichier, réduisez la largeur à environ ${formatNumber(quality.recommended_width_mm)} mm.`);
  const reasons: Record<string, string> = {
    low_resolution: "La définition est limitée. Préférez une source plus grande ou réduisez la taille du dessin.",
    very_low_resolution: "Les pixels de la source sont trop gros à cette taille pour retrouver des contours fins. Évitez d’agrandir artificiellement le fichier.",
    many_shades: "Les nombreuses nuances compliquent la séparation des fils. Pour un logo, une version en aplats est préférable.",
    lossy_source: "Le JPEG utilise une compression susceptible d’altérer les contours ; privilégiez l’original PNG ou SVG pour un logo.",
    palette_reduced: "Les nuances de l’image ont été regroupées en couleurs de fil.",
    svg_background_retraced: "Le retrait explicite du fond a rasterisé puis retracé le SVG ; vérifiez le dessin interprété.",
  };
  for (const issue of quality.issues) if (reasons[issue]) details.push(reasons[issue]);
  return [...new Set(details)];
}

export function retryInputQuality(failureCount: number, error: unknown) {
  return error instanceof ApiError && error.status === 503 && failureCount < 2;
}

export function inputQualityRetryDelay(failureCount: number) {
  return Math.min(1000, 500 * (failureCount + 1));
}

export function useInputQuality(file: File, settings: GenerationSettings, revision: number) {
  const scope = useId();
  const requested = JSON.stringify(inputQualitySettings(settings));
  // Delay the first upload too: a StrictMode remount must not occupy the analysis worker.
  const [settled, setSettled] = useState<string | null>(null);
  const valid = validInputQualitySettings(settings);
  const changing = requested !== settled;
  useEffect(() => {
    if (requested === settled) return;
    const timer = setTimeout(() => setSettled(requested), 300);
    return () => clearTimeout(timer);
  }, [requested, settled]);
  const query = useQuery<InputQuality, Error>({
    queryKey: ["input-quality", scope, revision, settled],
    enabled: valid && !changing && settled !== null,
    queryFn: async ({ signal }) => {
      const parameters = { ...DEFAULT_SETTINGS, ...JSON.parse(settled ?? requested) } as GenerationSettings;
      const result = await apiRequest<{ success: true; input_analysis: InputAnalysis }>("/api/analyze", {
        method: "POST", body: generationForm(file, parameters), signal,
      });
      if (!result.success || !result.input_analysis?.quality) throw new ApiError("Analyse de source indisponible.", 200);
      return result.input_analysis.quality;
    },
    retry: retryInputQuality,
    retryDelay: inputQualityRetryDelay,
    gcTime: 0,
    staleTime: Infinity,
  });
  return { query, valid, changing };
}
