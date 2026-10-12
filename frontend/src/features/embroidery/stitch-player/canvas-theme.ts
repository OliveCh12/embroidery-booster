export function canvasTheme(dark: boolean) {
  // A neutral midtone keeps both white and black thread visible without recoloring them.
  return dark ? {
    background: "#171c25", textile: "#737f8f", grid: "#85909e", hoop: "#cbd5e1", label: "#d9e1ec",
    underlay: "#e5ebf3", travel: "#ffe7b5", lock: "#f2deff", start: "#095b3c", needle: "#b91c1c",
  } : {
    background: "#f4f6f9", textile: "#8993a1", grid: "#a0a8b4", hoop: "#46536a", label: "#46536a",
    underlay: "#303e52", travel: "#583300", lock: "#481b78", start: "#095b3c", needle: "#b91c1c",
  };
}
