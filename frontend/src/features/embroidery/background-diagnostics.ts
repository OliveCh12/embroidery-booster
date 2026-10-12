import { formatNumber } from "../../lib/format";
import type { InputAnalysis } from "./types";

const reasons: Record<string, string> = {
  kept_by_request: "Fond conservé selon votre choix.",
  existing_transparency: "La transparence de l’image définit le contour conservé.",
  transparent_perimeter: "Le bord de l’image est déjà transparent.",
  ambiguous_perimeter: "Le fond au bord est ambigu : il a été conservé pour préserver le dessin.",
  no_distinct_foreground: "Aucun premier plan distinct du dégradé n’a été détecté : l’image est conservée.",
  border_connected_background: "Le fond uni relié au bord a été retiré jusqu’aux contours du dessin ; les aplats intérieurs sont préservés.",
  smooth_border_background: "Le fond dégradé estimé depuis le bord a été retiré jusqu’aux contours du dessin ; les aplats intérieurs sont préservés.",
  no_border_connected_background: "Aucun fond relié au bord à retirer.",
  explicit_vector_paint: "Les couleurs et transparences explicites du SVG sont conservées.",
  manual_threshold_or_inversion: "Le seuil ou l’inversion manuels déterminent la silhouette.",
};

export function describeBackground(background: NonNullable<InputAnalysis["background"]>) {
  const message = reasons[background.reason ?? ""] ?? (background.applied === true ? "Le fond a été retiré." : background.applied === false ? "Le fond a été conservé." : "Aucune modification du fond n’est indiquée.");
  const metrics: { label: string; value: string }[] = [];
  if (background.model) metrics.push({ label: "Fond estimé", value: background.model === "smooth_gradient" ? "Dégradé doux" : "Uni" });
  if (background.border_confidence != null) metrics.push({ label: "Bord compatible", value: `${formatNumber(background.border_confidence * 100)} %` });
  if (background.border_error_rgb != null) metrics.push({ label: "Écart RGB au bord (p95)", value: formatNumber(background.border_error_rgb) });
  if ((background.edge_refined_pixels ?? 0) > 0) metrics.push({ label: "Pixels de contour affinés", value: formatNumber(background.edge_refined_pixels!) });
  if ((background.edge_recovered_pixels ?? 0) > 0) metrics.push({ label: "Pixels de contour décontaminés", value: formatNumber(background.edge_recovered_pixels!) });
  return { message: message + (background.applied === true && (background.removed_fraction ?? 0) > 0 ? ` ${formatNumber(background.removed_fraction! * 100)} % de l’image retirés.` : ""), metrics };
}
