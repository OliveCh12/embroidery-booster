export type Fabric = "custom" | "stable" | "stretch" | "textured";
export type Stabilizer = "unspecified" | "cutaway" | "tearaway" | "washaway";
export type ThreadWeight = "30" | "40" | "60";
export type Machine = "generic" | "brother-skitch-pp1";
export type BackgroundMode = "auto" | "keep" | "remove";
export type StitchType = "auto" | "satin" | "fill" | "running";

export interface MachineProfile {
  label: string; hoop_width: number; hoop_height: number; max_colors: number;
  max_satin_width: number; max_area_mm: number | null; stitches_per_minute: number;
}
export interface MaterialPreset {
  stitch_spacing: number; fill_spacing: number; pull_compensation: number; underlay: boolean;
}
export interface Capabilities {
  engine: "direct"; direct: boolean; direct_formats: string[]; accepted_formats: string[];
  quality_report: boolean;
  material_presets: Record<Fabric, Record<ThreadWeight, MaterialPreset>>;
  machine_profiles: Record<Machine, MachineProfile>;
}
export interface GenerationSettings {
  machine: Machine; fabric: Fabric; thread_weight: ThreadWeight; stabilizer: Stabilizer;
  design_width: number | null; hoop_width: number; hoop_height: number; fit_to_hoop: boolean;
  stitch_spacing: number; fill_spacing: number; pull_compensation: number;
  running_length: number; max_stitch: number; max_satin_width: number; underlay: boolean;
  auto_adjust: boolean; auto_fill_angle: boolean; fill_angle: number;
  raster_threshold: number | null; raster_invert: boolean; max_colors: number; preserve_colors: boolean;
  background_mode: BackgroundMode; stitch_type: StitchType; raster_cleanup: boolean;
}
export interface StitchParams {
  satin_spacing_mm: number; fill_spacing_mm: number; pull_compensation_mm: number;
  running_length_mm: number; max_stitch_mm: number; max_satin_width_mm: number;
  hoop_width_mm: number; hoop_height_mm: number; underlay: boolean; auto_adjust: boolean;
  fill_angle_deg: number; auto_fill_angle: boolean; machine: Machine; fabric: Fabric;
  thread_weight: number; stabilizer: Stabilizer;
  stitch_type: StitchType;
}
export interface StitchStats {
  stitches: number; trims: number; jumps: number; color_changes: number;
  width_mm: number; height_mm: number; max_stitch_mm: number; short_stitches: number;
  satin_regions: number; fill_regions: number; running_regions: number;
  structural_coverage: number; largest_gap_mm2: number;
  uncovered_p95_mm: number; omitted_regions: number; unsafe_connections: number;
}
export interface Decision {
  component: number; method: "satin" | "fill" | "running" | "omitted";
  reason: string; width_mm: number; fill_angle_deg: number | null; color?: string;
  split_satin_columns?: number; safe_satin_width_mm?: number;
}
export interface Adjustment { parameter: string; requested: number | boolean; effective: number | boolean; reason: string }
export interface DesignAnalysis {
  category: string; topology_basis: string; boundary_length_mm: number; palette_reduced: boolean; area_mm2: number; color_count: number; region_count: number;
  hole_count: number; fine_region_area_ratio: number; strategy_counts: Record<string, number>;
  quality_status: "needs_review" | "geometric_checks_passed";
  stitch_breakdown?: { entry: number; top: number; underlay: number; travel: number; lock: number };
}
export interface InputAnalysis {
  background?: {
    mode: BackgroundMode | null; applied: boolean | null; reason: string | null;
    background_color: string | null; border_confidence: number | null;
    removed_fraction: number | null; interior_preserved_pixels: number | null;
    model?: "uniform" | "smooth_gradient" | null;
    border_error_rgb?: number | null; edge_refined_pixels?: number | null;
    edge_recovered_pixels?: number | null;
    counters_inferred?: number | null; counter_pixels_removed?: number | null;
    counter_inference?: string | null;
  };
  cleanup?: {
    enabled: boolean | null; changed_pixels: number | null; removed_pixels: number | null;
    regions_before: number | null; regions_after: number | null;
    changed_area_mm2: number | null; reason: string | null;
    palette_source_colors?: number | null; palette_colors?: number | null;
    flat_paints_recovered?: boolean | null; palette_consolidated_pixels?: number | null;
    palette_changed_area_mm2?: number | null; regions_after_palette?: number | null;
    retained_accent_colors?: number | null;
    edge_blend_pixels?: number | null;
  };
}
export interface DirectResult {
  files: { pes: string; dst: string; plan_json: string; preview_svg: string };
  preview: string; stats: StitchStats; decisions: Decision[]; threads: string[];
  params: StitchParams; requested_params: StitchParams; analysis: DesignAnalysis; adjustments: Adjustment[];
}
export interface GenerationResult {
  success: true; job: string; artwork_preview: string; artwork_svg: string;
  artwork_size_mm: [number, number]; converted_from: string | null; warnings: string[];
  logs: string; stats: { total_seconds: number }; direct: DirectResult;
  input_analysis?: InputAnalysis;
}
