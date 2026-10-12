import type { Adjustment, Decision, DesignAnalysis, StitchStats } from "../embroidery/types";

export interface QualityMetrics {
  coverage: number; structural_coverage: number; iou: number; trims: number;
  stitches: number; uncovered_p95_mm: number; max_stitch_mm: number;
  largest_gap_mm2: number; uncovered_max_mm: number;
}
export interface QualityResult {
  file: string; source_preview: string; preview?: string; footprint?: string; seconds?: number;
  metrics?: QualityMetrics; stats?: StitchStats; decisions?: Decision[]; threads?: string[];
  analysis?: DesignAnalysis; adjustments?: Adjustment[]; error?: string;
}
export interface QualityReport {
  schema_version: 3; engine: "direct";
  measurement: { thread_mm: number; structural_tolerance_mm: number; design_width_mm: number };
  results: QualityResult[];
}
