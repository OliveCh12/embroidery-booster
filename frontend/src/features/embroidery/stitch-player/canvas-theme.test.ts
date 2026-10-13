import { describe, expect, it } from "vitest";
import { canvasTheme, threadNeedsOutline } from "./canvas-theme";

describe("stitch canvas theme", () => {
  it.each([
    { background: "#f5f5f5", textile: "#ffffff", foreground: "#18181b" },
    { background: "#080808", textile: "#18181b", foreground: "#fafafa" },
  ])("uses the applied HeroUI palette instead of a separate canvas theme", colors => {
    const tokens: Record<string, string> = {
      "var(--background)": colors.background,
      "var(--surface)": colors.textile,
      "var(--border-secondary)": colors.foreground,
      "var(--muted)": colors.foreground,
    };
    const resolved = canvasTheme(expression => tokens[expression] ?? "#abcdef");
    expect(resolved.background).toBe(colors.background);
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
});
