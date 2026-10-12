export interface QualityMetrics {
  coverage: number; structural_coverage: number; iou: number; trims: number;
  stitches: number; uncovered_p95_mm: number; max_stitch_mm: number;
  largest_gap_mm2: number; uncovered_max_mm: number;
}

export interface QualityMethod {
  metrics?: QualityMetrics;
  top_metrics?: QualityMetrics;
  threads?: string[];
  error?: string;
  seconds?: number;
  preview?: string;
  footprint?: string;
}

export interface QualityReport {
  measurement: { thread_mm: number; structural_tolerance_mm: number; inkstitch_version: string | null };
  results: { file: string; source_preview: string; methods: Record<string, QualityMethod> }[];
}
