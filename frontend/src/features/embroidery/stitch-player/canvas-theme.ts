export type PreviewColorMode = "real" | "contrast";

export function canvasTheme(resolveColor: (expression: string) => string) {
  return {
    textile: resolveColor("var(--surface)"),
    grid: resolveColor("color-mix(in srgb, var(--border) 55%, var(--surface))"),
    hoop: resolveColor("var(--border-secondary)"),
    label: resolveColor("var(--muted)"),
    travel: resolveColor("var(--warning-soft-foreground)"),
    lock: resolveColor("var(--accent-soft-foreground)"),
    start: resolveColor("var(--success-soft-foreground)"),
    needle: resolveColor("var(--danger)"),
    threadOutline: resolveColor("color-mix(in srgb, var(--foreground) 35%, var(--surface))"),
  };
}

export function readCanvasTheme(element: HTMLElement) {
  const probe = document.createElement("span"), swatch = document.createElement("canvas");
  probe.hidden = true;
  swatch.width = swatch.height = 1;
  const context = swatch.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("Le navigateur ne prend pas en charge l’aperçu des points.");
  element.append(probe);
  try {
    return canvasTheme(expression => {
      // Resolve inherited CSS tokens, then normalize CSS Color 4 to canvas sRGB.
      probe.style.color = expression;
      context.fillStyle = getComputedStyle(probe).color;
      context.fillRect(0, 0, 1, 1);
      const rgb = context.getImageData(0, 0, 1, 1).data;
      return `#${Array.from(rgb.slice(0, 3), value => value.toString(16).padStart(2, "0")).join("")}`;
    });
  } finally {
    probe.remove();
  }
}

function luminance(hex: string) {
  const rgb = [1, 3, 5].map(offset => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

export function threadNeedsOutline(thread: string, textile: string) {
  const first = luminance(thread), second = luminance(textile);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05) < 3;
}

export function threadDisplayColor(thread: string, textile: string, mode: PreviewColorMode) {
  if (mode === "real" || !threadNeedsOutline(thread, textile)) return thread;
  const channels = [1, 3, 5].map(offset => parseInt(thread.slice(offset, offset + 2), 16));
  const surface = luminance(textile);
  const whiteContrast = 1.05 / (surface + 0.05), blackContrast = (surface + 0.05) / 0.05;
  const target = whiteContrast > blackContrast ? 255 : 0;
  const blend = (amount: number) => `#${channels.map(channel =>
    Math.round(channel + (target - channel) * amount).toString(16).padStart(2, "0")
  ).join("")}`;
  // Work on display colours only; use the least change that remains readable
  // after 8-bit rounding, preserving already contrasted thread colours exactly.
  let low = 0, high = 1;
  for (let index = 0; index < 20; index++) {
    const middle = (low + high) / 2;
    if (threadNeedsOutline(blend(middle), textile)) low = middle;
    else high = middle;
  }
  return blend(high);
}
