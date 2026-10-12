import { describe, expect, it } from "vitest";
import { canvasTheme } from "./canvas-theme";

function luminance(hex: string) {
  const rgb = [1, 3, 5].map(offset => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

function contrast(first: string, second: string) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

describe("stitch canvas theme", () => {
  it.each([false, true])("keeps white and black thread visible in dark=%s", dark => {
    const colors = canvasTheme(dark);
    expect(contrast("#ffffff", colors.textile)).toBeGreaterThanOrEqual(3);
    expect(contrast("#000000", colors.textile)).toBeGreaterThanOrEqual(3);
    expect(contrast(colors.label, colors.background)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.hoop, colors.textile)).toBeGreaterThanOrEqual(2);
  });

  it.each([false, true])("distinguishes optional technical paths from the textile in dark=%s", dark => {
    const colors = canvasTheme(dark);
    for (const kind of ["travel", "underlay", "lock"] as const) {
      expect(contrast(colors[kind], colors.textile)).toBeGreaterThanOrEqual(3);
    }
    expect(contrast(colors.grid, colors.textile)).toBeLessThan(2);
  });
});
