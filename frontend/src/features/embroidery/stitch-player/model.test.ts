import { describe, expect, it } from "vitest";
import { advancePlayback, buildThreadSequence, describeThreadColor, eventLabel, parseStitchPlan, pointAt, threadStepStatus, viewport } from "./model";

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
    expect(Array.from(plan.phases)).toEqual([0, 0, 1, 0, 0, 0, 0, 0, 0]);
    expect(eventLabel(plan, 3)).toBe("Sous-couche");
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

  it("builds thread passages from machine color changes with exact stitch ranges and sewing times", () => {
    const plan = parseStitchPlan(example);
    const sequence = buildThreadSequence(plan);
    expect(sequence).toEqual([
      { index: 0, color: "#FFFFFF", name: "Blanc", startCursor: 0, endCursor: 4, stitchCount: 2, firstStitch: 1, lastStitch: 2, startMinutes: 0, endMinutes: 0.005, durationMinutes: 0.005 },
      { index: 1, color: "#CE1126", name: "Rouge", startCursor: 5, endCursor: 9, stitchCount: 2, firstStitch: 3, lastStitch: 4, startMinutes: 0.005, endMinutes: 0.01, durationMinutes: 0.005 },
    ]);
    expect(sequence.map(step => threadStepStatus(step, 0))).toEqual(["active", "pending"]);
    expect(sequence.map(step => threadStepStatus(step, 5))).toEqual(["completed", "active"]);
    expect(sequence.map(step => threadStepStatus(step, plan.count))).toEqual(["completed", "completed"]);
    expect(advancePlayback(plan, sequence[1].startCursor, 1, true)).toEqual({ cursor: 7, pausedForColor: false });
    expect(buildThreadSequence(parseStitchPlan({ ...example, machine: { stitches_per_minute: 800 } }))[1].startMinutes).toBe(0.0025);
  });

  it("pauses at each change at an exact stitch budget, including consecutive color commands", () => {
    const plan = parseStitchPlan({ ...example, threads: ["#ffffff", "#ce1126", "#ffffff"], commands: [
      [0, 0, 1], [0, 0, 0], [0, 0, 2], [0, 0, 5], [0, 0, 2], [0, 0, 5], [10, 0, 1], [20, 0, 0], [20, 0, 4],
    ], underlay_runs: [] });
    const first = advancePlayback(plan, 0, 1, true);
    expect(first).toEqual({ cursor: 4, pausedForColor: true });
    const second = advancePlayback(plan, first.cursor, 1, true);
    expect(second).toEqual({ cursor: 6, pausedForColor: true });
    expect(advancePlayback(plan, second.cursor, 1, true)).toEqual({ cursor: 9, pausedForColor: false });
    expect(advancePlayback(plan, 0, 1, false)).toEqual({ cursor: 7, pausedForColor: false });
    expect(advancePlayback(plan, 0, 2, false)).toEqual({ cursor: 9, pausedForColor: false });
    expect(advancePlayback(plan, plan.count, 1, true)).toEqual({ cursor: plan.count, pausedForColor: false });
    const sequence = buildThreadSequence(plan);
    expect(sequence.map(step => step.stitchCount)).toEqual([1, 0, 1]);
    expect(sequence[1]).toMatchObject({ startCursor: 4, endCursor: 5, firstStitch: null, lastStitch: null });
    expect(sequence[2]).toMatchObject({ index: 2, color: "#FFFFFF", firstStitch: 2, lastStitch: 2 });
  });

  it("lists only machine thread passages, including a single-color plan", () => {
    const plan = parseStitchPlan({ ...example, commands: [[0, 0, 1], [0, 0, 0], [10, 0, 0], [10, 0, 4]], underlay_runs: [] });
    expect(buildThreadSequence(plan)).toHaveLength(1);
    expect(buildThreadSequence(plan)[0]).toMatchObject({ startCursor: 0, endCursor: plan.count, stitchCount: 2, firstStitch: 1, lastStitch: 2 });
    expect(advancePlayback(plan, 0, 2, true)).toEqual({ cursor: plan.count, pausedForColor: false });
  });

  it("reads a global thread weight without inventing it for older plans", () => {
    expect(parseStitchPlan(example).threadWeight).toBeNull();
    for (const thread_weight of [30, 40, 60] as const) expect(parseStitchPlan({ ...example, params: { thread_weight } }).threadWeight).toBe(thread_weight);
    for (const thread_weight of [20, "40", false, null]) expect(parseStitchPlan({ ...example, params: { thread_weight } }).threadWeight).toBeNull();
    expect(parseStitchPlan({ ...example, params: null }).threadWeight).toBeNull();
  });

  it("describes RGB colors in French without assigning a manufacturer reference", () => {
    const colors = {
      "#000000": "Noir", "#ffffff": "Blanc", "#808080": "Gris", "#f2f2f2": "Gris clair",
      "#ce1126": "Rouge", "#001f72": "Bleu foncé", "#0000ff": "Bleu", "#00ff00": "Vert",
      "#ffff00": "Jaune", "#ff8000": "Orange", "#00ffff": "Turquoise", "#8000ff": "Violet",
      "#ff80bf": "Rose", "#996633": "Marron", "#ffeecc": "Beige",
    };
    for (const [hex, name] of Object.entries(colors)) {
      expect(describeThreadColor(hex)).toBe(name);
      expect(describeThreadColor(hex.toUpperCase())).toBe(name);
    }
    expect(describeThreadColor("blue")).toBe("Couleur inconnue");
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
    expect(() => parseStitchPlan({ ...example, underlay_runs: [{ start: 5, end: 100 }] })).toThrow("phase");
  });

  it("separates coverage, sewn travel and locks without reclassifying their context nodes", () => {
    const plan = parseStitchPlan({ ...example, runs: [{ start: 0, end: 2, kind: "lock" }, { start: 1, end: 3, kind: "underlay" }, { start: 5, end: 7, kind: "travel" }, { start: 6, end: 8, kind: "fill" }] });
    expect(Array.from(plan.phases)).toEqual([0, 3, 1, 0, 0, 0, 2, 0, 0]);
    expect(eventLabel(plan, 2)).toBe("Ancrage du fil");
    expect(eventLabel(plan, 7)).toBe("Liaison cousue");
    expect(eventLabel(plan, 8)).toBe("Point cousu");
  });
});
