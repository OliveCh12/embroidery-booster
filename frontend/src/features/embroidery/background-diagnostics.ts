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
  const message = (background.counters_inferred ?? 0) > 0 ? "Le fond relié au bord a été retiré jusqu’aux contours du logo." : reasons[background.reason ?? ""] ?? (background.applied === true ? "Le fond a été retiré." : background.applied === false ? "Le fond a été conservé." : "Aucune modification du fond n’est indiquée.");
  const metrics: { label: string; value: string }[] = [];
  if (background.model) metrics.push({ label: "Fond estimé", value: background.model === "smooth_gradient" ? "Dégradé doux" : "Uni" });
  if (background.border_confidence != null) metrics.push({ label: "Bord compatible", value: `${formatNumber(background.border_confidence * 100)} %` });
  if (background.border_error_rgb != null) metrics.push({ label: "Écart RGB au bord (p95)", value: formatNumber(background.border_error_rgb) });
  if ((background.edge_refined_pixels ?? 0) > 0) metrics.push({ label: "Pixels de contour affinés", value: formatNumber(background.edge_refined_pixels!) });
  if ((background.edge_recovered_pixels ?? 0) > 0) metrics.push({ label: "Pixels de contour décontaminés", value: formatNumber(background.edge_recovered_pixels!) });
  if ((background.counters_inferred ?? 0) > 0) metrics.push({ label: "Évidements monochromes", value: formatNumber(background.counters_inferred!) });
  const ambiguous = (background.counter_ambiguity?.regions ?? 0) > 0;
  if (ambiguous) metrics.push({ label: "Aplats intérieurs ambigus", value: formatNumber(background.counter_ambiguity!.regions) });
  return { message: message + (background.applied === true && (background.removed_fraction ?? 0) > 0 ? ` ${formatNumber(background.removed_fraction! * 100)} % de l’image retirés.` : "") + ((background.counters_inferred ?? 0) > 0 ? " Les blancs entourés de traits épais ont été interprétés comme des évidements. Désactivez le nettoyage pour les conserver." : "") + (ambiguous ? " Une peinture intérieure de la couleur du fond est conservée : son intention est ambiguë. Si un évidement est souhaité, utilisez un PNG transparent ou un SVG avec une contreforme explicite." : ""), metrics };
}

export function describeBitmapCleanup(cleanup: InputAnalysis["cleanup"]): string[] {
  const messages: string[] = [];
  const fringe = cleanup?.dark_ink_edge_pixels ?? 0, fragments = cleanup?.alpha_fragments_removed ?? 0, pixels = cleanup?.alpha_fragment_pixels ?? 0;
  if (fringe > 0) messages.push(`${formatNumber(fringe)} pixels gris de contour partiellement transparent rattachés au même fil noir. Les gris opaques et accents colorés sont préservés.`);
  if (fragments > 0) messages.push(`${formatNumber(fragments)} fragment${fragments > 1 ? "s" : ""} d’antialiasing trop fin${fragments > 1 ? "s" : ""} retiré${fragments > 1 ? "s" : ""} au bord du même trait (${formatNumber(pixels)} pixel${pixels > 1 ? "s" : ""}). Les détails opaques ou isolés sont préservés.`);
  const refinement = cleanup?.palette_refinement;
  if (refinement && refinement.count > 0) messages.push(`${formatNumber(refinement.count)} couleur${refinement.count > 1 ? "s" : ""} de fil ajustée${refinement.count > 1 ? "s" : ""} à partir des pixels source pour réduire l’écart de couleur.${refinement.masks_unchanged ? " Les contours et les découpes sont conservés." : ""}`);
  return messages;
}

export function describeTraceAudit(tracing: InputAnalysis["tracing"]): string | null {
  if (!tracing) return null;
  const final = tracing.final;
  if (!final.passed || final.changed_pixels !== 0 || !final.topology_preserved) {
    return `Tracé à vérifier${final.changed_pixels > 0 ? ` : ${formatNumber(final.changed_pixels)} pixels diffèrent de l’image interprétée` : ""}.${!final.topology_preserved ? " La structure des trous ou îlots a changé." : ""}`;
  }
  return tracing.fallback
    ? "Simplification du tracé réduite pour conserver les couleurs, trous et îlots de l’image interprétée. Contrôle effectué avant le calcul des points."
    : "Tracé conforme à l’image interprétée sur sa grille de pixels. Contrôle effectué avant le calcul des points.";
}

export function describeNormalization(normalization: InputAnalysis["normalization"]): string | null {
  if (!normalization) return null;
  const messages: string[] = [];
  if (normalization.orientation_applied) messages.push("Orientation de l’image corrigée.");
  if (normalization.icc_status === "converted") messages.push("Profil couleur intégré converti en sRGB.");
  else if (normalization.icc_status === "ignored_invalid") messages.push("Profil couleur invalide ignoré ; couleurs supposées sRGB.");
  else if (normalization.icc_status === "unavailable") messages.push("Conversion du profil couleur indisponible ; couleurs supposées sRGB.");
  else if (normalization.source_mode === "CMYK") messages.push("Image CMYK convertie sans profil couleur ; couleurs supposées sRGB.");
  return messages.length ? messages.join(" ") : null;
}

export function describeResampling(resampling: InputAnalysis["resampling"]) {
  if (!resampling) return null;
  const dimensions = (pixels: [number, number]) => `${pixels.map(formatNumber).join(" × ")} px`;
  const reductionNeedsReview = !resampling.passed || resampling.unresolved_issues > 0;
  const missingPaints = (resampling.missing_source_paints?.length ?? 0) > 0;
  const familyRetryRejected = resampling.paint_family_retry?.adopted === false;
  const messages = [resampling.resampling === "none"
    ? `Grille d’analyse : source conservée (${dimensions(resampling.working_pixels)}).`
    : `Grille d’analyse : ${dimensions(resampling.source_pixels)} → ${dimensions(resampling.working_pixels)}${resampling.adapted ? " · résolution ajustée pour préserver les détails" : ""}.`];
  if (resampling.reference !== "source_unchanged") {
    const scope = resampling.reference === "source_alpha_and_literal_paints" ? "Silhouette et aplats comparés"
      : resampling.reference === "source_alpha_and_flat_paint_cores" ? "Silhouette et noyaux d’aplats estimés comparés"
      : resampling.reference === "source_alpha_and_paint_families" ? "Silhouette et familles de couleurs estimées comparées" : "Silhouette comparée";
    messages.push(`${scope} à la source pour les détails d’au moins ${formatNumber(resampling.detail_area_mm2)} mm². Ce contrôle porte sur l’image, avant le calcul des points.`);
  }
  if (reductionNeedsReview) messages.push(`${resampling.unresolved_issues > 0 ? `${formatNumber(resampling.unresolved_issues)} écart${resampling.unresolved_issues > 1 ? "s" : ""} mesuré${resampling.unresolved_issues > 1 ? "s" : ""} après réduction` : "Réduction à vérifier"} ; vérifiez le dessin interprété.`);
  if (missingPaints) messages.push(["source_alpha_and_flat_paint_cores", "source_alpha_and_paint_families"].includes(resampling.reference)
    ? "Des aplats estimés à partir de la source sont absents après interprétation et nettoyage ; vérifiez le dessin interprété."
    : "Des aplats de couleur de la source sont absents après interprétation et nettoyage ; vérifiez le dessin interprété.");
  if (familyRetryRejected) messages.push("Les familles de couleurs estimées n’ont pas pu être confirmées ; l’interprétation précédente est conservée. Vérifiez la palette et les petits accents.");
  return { message: messages.join(" "), needsReview: reductionNeedsReview || missingPaints || familyRetryRejected };
}
