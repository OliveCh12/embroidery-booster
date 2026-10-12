import { describe, expect, it } from "vitest";
import { advancePlayback, eventLabel, parseStitchPlan, pointAt, viewport } from "./model";

const example = {
  schema_version: 3, units: "0.1mm", coordinate_frame: "hoop_center", threads: ["#ffffff", "#ce1126"],
  origin_mm: [40, 40], hoop: { width_mm: 100, height_mm: 80 },
  command_codes: { stitch: 0, jump: 1, trim: 2, color_change: 5, end: 4, command_mask: 255 },
  machine: { stitches_per_minute: 400 },
  commands: [[-100, -50, 1], [-100, -50, 0], [0, -50, 0], [0, -50, 2], [0, -50, 5], [10, 20, 1], [10, 20, 0], [50, 20, 0], [50, 20, 4]],
  underlay_runs: [{ start: 1, end: 3 }],
};

describe("physical stitch plan", () => {
  it("reads machine-centered tenths of millimeters without adding artwork origin", () => {
    const plan = parseStitchPlan(example);
    expect(pointAt(plan, 1)).toEqual([-10, -5]);
    expect(pointAt(plan, 0)).toBeNull();
    expect(plan.bounds).toEqual([-10, -5, 5, 2]);
    expect(plan.hoop).toEqual({ width: 100, height: 80 });
    expect(plan.stitchesPerMinute).toBe(400);
    expect(Array.from(plan.underlay)).toEqual([0, 0, 1, 0, 0, 0, 0, 0, 0]);
  });

  it("preserves color changes, jumps, trims and exact needle cycle counts", () => {
    const plan = parseStitchPlan(example);
    expect(Array.from(plan.stitches)).toEqual([0, 0, 1, 2, 2, 2, 2, 3, 4, 4]);
    expect(Array.from(plan.colors)).toEqual([0, 0, 0, 0, 1, 1, 1, 1, 1]);
    expect(eventLabel(plan, 1)).toContain("levée");
    expect(eventLabel(plan, 4)).toBe("Coupe du fil");
    expect(eventLabel(plan, 5)).toBe("Changement de fil");
    expect(eventLabel(plan, 9)).toBe("Broderie terminée");
    expect(advancePlayback(plan, 0, 2, true)).toEqual({ cursor: 5, pausedForColor: true });
    expect(advancePlayback(plan, 5, 2, true)).toEqual({ cursor: 9, pausedForColor: false });
    expect(advancePlayback(plan, 0, 4, false).cursor).toBe(9);
  });

  it("fits a rectangular physical hoop isotropically and centers machine origin", () => {
    const frame = viewport(800, 500, 100, 80);
    expect(frame.scale).toBeCloseTo(5.55);
    expect(frame.centerX).toBe(400);
    expect(frame.centerY).toBe(250);
    expect(frame.left + 50 * frame.scale).toBeCloseTo(frame.centerX);
    expect(frame.top + 40 * frame.scale).toBeCloseTo(frame.centerY);
  });

  it("masks machine metadata bits without changing base commands", () => {
    expect(parseStitchPlan({ ...example, commands: example.commands.map(row => [row[0], row[1], row[2] | 0x10000]) }).codes[4]).toBe(5);
  });

  it("rejects incompatible versions, malformed coordinates and invalid palette changes", () => {
    expect(() => parseStitchPlan({ ...example, schema_version: 2 })).toThrow("incompatible");
    expect(() => parseStitchPlan({ ...example, coordinate_frame: "artwork" })).toThrow("incompatible");
    expect(() => parseStitchPlan({ ...example, commands: [[NaN, 0, 0]] })).toThrow("Coordonnées");
    expect(() => parseStitchPlan({ ...example, commands: [[0, 0, 3]] })).toThrow("commande");
    expect(() => parseStitchPlan({ ...example, threads: ["#ffffff"] })).toThrow("palette");
    expect(() => parseStitchPlan({ ...example, hoop: { width_mm: 0, height_mm: 100 } })).toThrow("cadre");
    expect(() => parseStitchPlan({ ...example, underlay_runs: [{ start: 5, end: 100 }] })).toThrow("sous-couche");
  });
});
