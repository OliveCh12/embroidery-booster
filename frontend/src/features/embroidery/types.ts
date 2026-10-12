export type Method = "direct" | "both" | "inkstitch";
export type Fabric = "custom" | "stable" | "stretch" | "textured";
export type Stabilizer = "unspecified" | "cutaway" | "tearaway" | "washaway";
export type ThreadWeight = "30" | "40" | "60";
export type Machine = "generic" | "brother-skitch-pp1";

export interface MachineProfile {
  label: string;
  hoop_width: number;
  hoop_height: number;
  max_colors: number;
  max_satin_width: number;
  max_area_mm: number | null;
}

export interface MaterialPreset {
  stitch_spacing: number;
  fill_spacing: number;
  pull_compensation: number;
  underlay: boolean;
}

export interface Capabilities {
  inkscape: boolean;
  inkstitch: boolean;
  direct: boolean;
  quality_report: boolean;
  material_presets: Record<Fabric, Record<ThreadWeight, MaterialPreset>>;
  machine_profiles: Record<Machine, MachineProfile>;
}

export interface GenerationSettings {
  method: Method;
  machine: Machine;
  max_satin_width: number;
  fabric: Fabric;
  thread_weight: ThreadWeight;
  stabilizer: Stabilizer;
  design_width: number | null;
  hoop_width: number;
  hoop_height: number;
  fit_to_hoop: boolean;
  stitch_spacing: number;
  fill_spacing: number;
  pull_compensation: number;
  running_length: number;
  max_stitch: number;
  underlay: boolean;
  auto_select: boolean;
  auto_fill_angle: boolean;
  fill_angle: number;
  fill_gaps: boolean;
  wide_mode: "fill" | "split";
  export: boolean;
  auto_optimize: boolean;
  spacing: number;
  density: number;
  dpi: number;
  debug: boolean;
  raster_threshold: number | null;
  raster_invert: boolean;
  max_colors: number;
  preserve_colors: boolean;
}

export interface StitchStats {
  stitches: number;
  trims: number;
  width_mm: number;
  height_mm: number;
  max_stitch_mm: number;
  short_stitches: number;
  satin_regions: number;
  fill_regions: number;
  running_regions: number;
  seconds: number;
  structural_coverage: number;
  largest_gap_mm2: number;
  coverage_repairs: number;
}

export interface Decision {
  component: number;
  method: "satin" | "fill" | "running" | "omitted";
  reason: string;
  width_mm: number;
  fill_angle_deg: number | null;
}

export interface GenerationResult {
  success: true;
  job: string;
  method: Method;
  files: Record<string, string>;
  preview: string;
  satin_preview: string | null;
  artwork_preview: string;
  artwork_svg: string;
  artwork_size_mm: [number, number];
  converted_from: string | null;
  warnings: string[];
  logs: string;
  debug_images: Record<string, string>;
  stats: { columns: number; running: number; coverage: number; total_seconds: number; seconds: number };
  native_stats: { stitches: number; trims: number; max_stitch_mm: number } | null;
  direct: {
    files: Record<string, string>;
    preview: string;
    stats: StitchStats;
    decisions: Decision[];
    threads: string[];
    coverage_basis: "quantized_top_layer" | "all_sewn_stitches";
    params: { spacing_mm: number; fill_spacing_mm: number; thread_weight: number; fabric: Fabric; stabilizer: Stabilizer };
  } | null;
}
