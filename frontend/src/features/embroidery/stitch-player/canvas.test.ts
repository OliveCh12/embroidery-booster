import { afterEach, describe, expect, it, vi } from "vitest";
import { StitchRenderer } from "./canvas";
import { threadDisplayColor, type PreviewColorMode } from "./canvas-theme";
import { parseStitchPlan, viewport } from "./model";

const theme = vi.hoisted(() => ({
  textile: "#ffffff", grid: "#dddddd", hoop: "#aaaaaa", label: "#777777",
  travel: "#a16000", lock: "#7342b8", start: "#008000", needle: "#ff0000", threadOutline: "#aaaaaa",
}));

vi.mock("./canvas-theme", async importOriginal => ({
  ...await importOriginal<typeof import("./canvas-theme")>(),
  readCanvasTheme: () => theme,
}));

type Node = [kind: "move" | "line", x: number, y: number];
interface Stroke { color: string; width: number; path: Node[] }

function context() {
  const strokes: Stroke[] = [];
  let path: Node[] = [];
  const drawing = {
    strokeStyle: "#000000", lineWidth: 1,
    setTransform() {}, clearRect() {}, fillRect() {}, setLineDash() {}, strokeRect() {}, fillText() {},
    beginPath() { path = []; },
    moveTo(x: number, y: number) { path.push(["move", x, y]); },
    lineTo(x: number, y: number) { path.push(["line", x, y]); },
    stroke() { strokes.push({ color: this.strokeStyle, width: this.lineWidth, path: [...path] }); },
  };
  return { strokes, drawing: drawing as unknown as CanvasRenderingContext2D };
}

const source = {
  schema_version: 3, units: "0.1mm", coordinate_frame: "hoop_center",
  threads: ["#ff1301", "#0e0f95"], hoop: { width_mm: 100, height_mm: 100 },
  command_codes: { stitch: 0, jump: 1, trim: 2, color_change: 5, end: 4, command_mask: 255 },
  commands: [[-10, 0, 1], [-10, 0, 0], [0, 0, 0], [10, 0, 0], [10, 0, 2], [10, 0, 5], [-10, 10, 1], [-10, 10, 0], [0, 10, 0], [10, 10, 0], [10, 10, 4]],
  runs: [{ start: 1, end: 3, kind: "underlay" }, { start: 2, end: 4, kind: "fill" }, { start: 7, end: 9, kind: "underlay" }, { start: 8, end: 10, kind: "fill" }],
};

function render(underlay: boolean, colorMode: PreviewColorMode = "real") {
  const main = context(), overlay = context(), plan = parseStitchPlan(source);
  let pending: FrameRequestCallback | null = null;
  vi.stubGlobal("window", { devicePixelRatio: 1 });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { pending = callback; return 1; });
  vi.stubGlobal("cancelAnimationFrame", () => { pending = null; });
  const canvas = (drawing: CanvasRenderingContext2D) => ({ getContext: () => drawing, dataset: {} }) as unknown as HTMLCanvasElement;
  const renderer = new StitchRenderer(canvas(main.drawing), canvas(overlay.drawing), plan, { underlay, travel: false, colorMode });
  renderer.resize(400, 400);
  main.strokes.length = 0;
  renderer.setCursor(plan.count);
  while (pending) {
    const callback: FrameRequestCallback = pending;
    pending = null;
    callback(0);
  }
  renderer.destroy();
  // An outlined segment is stroked twice; retain its final thread-coloured stroke.
  const segments = new Map<string, { color: string; width: number }>();
  for (const stroke of main.strokes) for (let index = 0; index < stroke.path.length; index += 2) {
    const [, fromX, fromY] = stroke.path[index], [, toX, toY] = stroke.path[index + 1];
    segments.set(`${fromX},${fromY}:${toX},${toY}`, { color: stroke.color, width: stroke.width });
  }
  return { segments, plan };
}

afterEach(() => vi.unstubAllGlobals());

describe("machine thread colours in the stitch canvas", () => {
  it.each(["#ffffff", "#18181b"])("draws red and blue underlay with the active thread on %s", textile => {
    theme.textile = textile;
    const { segments, plan } = render(true);
    const visible = [...segments.values()];
    expect(visible.map(segment => segment.color)).toEqual(["#ff1301", "#ff1301", "#0e0f95", "#0e0f95"]);
    expect(visible.every(segment => segment.width === Math.max(0.65, 0.3 * viewport(400, 400, 100, 100).scale))).toBe(true);
    expect(plan.threads).toEqual(source.threads);
  });

  it("hides only the underlay segments without drawing a connection across a colour change", () => {
    theme.textile = "#ffffff";
    const { segments, plan } = render(false), frame = viewport(400, 400, 100, 100);
    const coordinate = (index: number) => `${frame.centerX + plan.points[index * 2] * frame.scale},${frame.centerY + plan.points[index * 2 + 1] * frame.scale}`;
    expect([...segments.keys()]).toEqual([`${coordinate(2)}:${coordinate(3)}`, `${coordinate(8)}:${coordinate(9)}`]);
    expect([...segments.values()].map(segment => segment.color)).toEqual(source.threads);
  });

  it("applies optional display contrast consistently to underlay and surface without changing threads", () => {
    theme.textile = "#18181b";
    const { segments, plan } = render(true, "contrast");
    const expected = source.threads.map(thread => threadDisplayColor(thread, theme.textile, "contrast"));
    expect([...segments.values()].map(segment => segment.color)).toEqual([expected[0], expected[0], expected[1], expected[1]]);
    expect(expected[1]).not.toBe(source.threads[1]);
    expect(plan.threads).toEqual(source.threads);
  });
});
