import { describe, expect, it } from "vitest";
import { canvasTheme, threadDisplayColor, threadNeedsOutline } from "./canvas-theme";

describe("stitch canvas theme", () => {
  it.each([
    { textile: "#ffffff", foreground: "#18181b" },
    { textile: "#18181b", foreground: "#fafafa" },
  ])("uses the applied HeroUI palette instead of a separate canvas theme", colors => {
    const tokens: Record<string, string> = {
      "var(--surface)": colors.textile,
      "var(--border-secondary)": colors.foreground,
      "var(--muted)": colors.foreground,
    };
    const resolved = canvasTheme(expression => tokens[expression] ?? "#abcdef");
    expect(resolved.textile).toBe(colors.textile);
    expect(resolved.hoop).toBe(colors.foreground);
    expect(resolved.label).toBe(colors.foreground);
    expect(Object.values(resolved).every(color => /^#[\da-f]{6}$/i.test(color))).toBe(true);
  });

  it("adds a restrained outline only where the original thread needs contrast", () => {
    expect(threadNeedsOutline("#ffffff", "#ffffff")).toBe(true);
    expect(threadNeedsOutline("#000000", "#18181b")).toBe(true);
    expect(threadNeedsOutline("#ffffff", "#18181b")).toBe(false);
    expect(threadNeedsOutline("#000000", "#ffffff")).toBe(false);
    expect(threadNeedsOutline("#ffec00", "#ffffff")).toBe(true);
    expect(threadNeedsOutline("#a1001a", "#ffffff")).toBe(false);
  });

  it("resolves technical paths and contrast from the same CSS theme", () => {
    const requested: string[] = [];
    canvasTheme(expression => { requested.push(expression); return "#abcdef"; });
    expect(requested).toContain("var(--warning-soft-foreground)");
    expect(requested).toContain("var(--accent-soft-foreground)");
    expect(requested).toContain("var(--success-soft-foreground)");
    expect(requested).toContain("var(--danger)");
    expect(requested).toContain("color-mix(in srgb, var(--foreground) 35%, var(--surface))");
  });

  it.each(["#000000", "#ffffff", "#ffec00", "#a1001a", "#176d9c"])(
    "keeps the exact thread colour %s in real mode across both themes", thread => {
      expect(threadDisplayColor(thread, "#ffffff", "real")).toBe(thread);
      expect(threadDisplayColor(thread, "#18181b", "real")).toBe(thread);
    }
  );

  it.each([
    ["#000000", "#18181b"],
    ["#ffffff", "#ffffff"],
    ["#ffec00", "#ffffff"],
  ])("makes low-contrast thread %s readable on textile %s", (thread, textile) => {
    const display = threadDisplayColor(thread, textile, "contrast");
    expect(display).not.toBe(thread);
    expect(threadNeedsOutline(display, textile)).toBe(false);
    expect(display).not.toBe(textile === "#ffffff" ? "#000000" : "#ffffff");
  });

  it.each([
    ["#ffffff", "#ffffff", "#949494", "#959595"],
    ["#000000", "#18181b", "#656565", "#646464"],
  ])("changes neutral thread %s by the minimum readable amount", (thread, textile, display, closer) => {
    expect(threadDisplayColor(thread, textile, "contrast")).toBe(display);
    expect(threadNeedsOutline(closer, textile)).toBe(true);
  });

  it.each([
    ["#000000", "#ffffff"],
    ["#ffffff", "#18181b"],
    ["#a1001a", "#ffffff"],
    ["#176d9c", "#18181b"],
  ])("leaves sufficiently contrasted thread %s unchanged", (thread, textile) => {
    expect(threadDisplayColor(thread, textile, "contrast")).toBe(thread);
  });

  it("keeps original thread colours immutable when creating a display palette", () => {
    const threads = Object.freeze(["#000000", "#ffffff", "#ffec00", "#a1001a"]);
    const original = [...threads];
    const display = threads.map(thread => threadDisplayColor(thread, "#ffffff", "contrast"));
    expect(threads).toEqual(original);
    expect(display).not.toBe(threads);
    expect(display[0]).toBe(original[0]);
    expect(display[1]).not.toBe(original[1]);
  });
});
