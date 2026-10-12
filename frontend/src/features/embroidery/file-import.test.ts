import { describe, expect, it, vi } from "vitest";
import { clipboardFile } from "./file-import";
import { DEFAULT_SETTINGS, generationForm, validateFile } from "./settings";

describe("clipboard import", () => {
  it("adds a PNG filename to a pasted screenshot without changing its bytes or metadata", async () => {
    const screenshot = new File(["image bytes"], "", { type: "image/png", lastModified: 123 });
    const selected = clipboardFile({ items: [{ kind: "file", getAsFile: () => screenshot }], files: [] })!;
    expect(selected.name).toBe("image-collee.png");
    expect(selected.type).toBe("image/png");
    expect(selected.lastModified).toBe(123);
    expect(await selected.text()).toBe(await screenshot.text());
    expect(validateFile(selected)).toBeNull();
    expect(generationForm(selected, DEFAULT_SETTINGS).get("file")).toBe(selected);
  });

  it.each([
    ["image/svg+xml", "svg"], ["image/jpeg", "jpg"], ["image/webp", "webp"],
    ["image/bmp", "bmp"], ["image/gif", "gif"], ["image/tiff", "tiff"],
  ])("recognizes an extensionless %s clipboard image", (type, extension) => {
    const image = new File(["image"], "capture", { type });
    const selected = clipboardFile({ items: [], files: [image] })!;
    expect(selected.name).toBe(`capture.${extension}`);
    expect(validateFile(selected)).toBeNull();
  });

  it("keeps the original filename and imports only the first file", () => {
    const logo = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });
    const second = vi.fn();
    expect(clipboardFile({ items: [
      { kind: "file", getAsFile: () => logo }, { kind: "file", getAsFile: second },
    ], files: [logo] })).toBe(logo);
    expect(second).not.toHaveBeenCalled();
  });

  it("ignores text/HTML clipboard items and skips unreadable file items", () => {
    const image = new File(["image"], "photo.jpg", { type: "image/jpeg" });
    const textItem = vi.fn();
    expect(clipboardFile({ items: [
      { kind: "string", getAsFile: textItem }, { kind: "file", getAsFile: () => null },
      { kind: "file", getAsFile: () => image },
    ], files: [] })).toBe(image);
    expect(textItem).not.toHaveBeenCalled();
  });

  it("falls back to the file list when clipboard items are unavailable", () => {
    const image = new File(["image"], "capture.png", { type: "image/png" });
    expect(clipboardFile({ items: [], files: [image] })).toBe(image);
  });

  it("returns no file for a text-only or empty clipboard", () => {
    expect(clipboardFile({ items: [{ kind: "string", getAsFile: () => null }], files: [] })).toBeNull();
    expect(clipboardFile({ items: [], files: [] })).toBeNull();
  });

  it("keeps unsupported images subject to the existing file validation", () => {
    const unsupported = new File(["image"], "capture.avif", { type: "image/avif" });
    const selected = clipboardFile({ items: [], files: [unsupported] })!;
    expect(validateFile(selected)).not.toBeNull();
  });
});
