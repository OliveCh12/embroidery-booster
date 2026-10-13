import type { GenerationResult, VariantId } from "./types";

export const VARIANT_LABELS: Record<VariantId, string> = {
  balanced: "Équilibré",
  satin_preferred: "Priorité satin",
  uniform_fill: "Tatami uniforme",
  uniform_satin: "Satin uniforme",
  running_outline: "Contours · point droit",
};

export function variantResult(result: GenerationResult, id: VariantId | null): GenerationResult {
  const variant = result.variants?.find(item => item.id === id || (id !== null && item.equivalent_strategies?.includes(id)));
  if (!variant) return result;
  return { ...result, direct: variant.direct,
    warnings: [...new Set([...(result.input_warnings ?? []), ...(variant.direct.warnings ?? [])])] };
}

export function variantOptions(result: GenerationResult): { id: VariantId; label: string }[] {
  return result.variants?.flatMap(item => [
    { id: item.id, label: `${VARIANT_LABELS[item.id]}${item.id === result.recommended_variant ? " · recommandé" : ""}` },
    ...(item.equivalent_strategies ?? []).map(id => ({ id, label: `${VARIANT_LABELS[id]} · identique à ${VARIANT_LABELS[item.id]}` })),
  ]) ?? [];
}

export function variantReason(reason: string): string {
  const labels: Record<string, string> = {
    shared_interpretation: "Dessin interprété, fils et réglages de tissu identiques.",
    audit_first: "Les contrôles des points machine priment sur le nombre de points.",
    balanced_default: "Choix équilibré conservé en l’absence d’un gain validé.",
    safe_satin_gain: "Davantage de satin, avec une couverture et des points validés.",
    improved_geometry: "Cette proposition réduit les défauts géométriques mesurés.",
    no_meaningful_gain: "Les alternatives n’apportent pas de gain validé suffisant.",
    uniform_texture: "Même orientation tatami sur les surfaces, pour une texture uniforme.",
    qualified_columns: "Le satin est privilégié sur les colonnes complètes qui passent les contrôles.",
    all_satin: "Couverture entièrement en satin, avec des colonnes contrôlées sur les points machine.",
    outline_only: "Point droit sur les contours : cette proposition ne remplit pas les surfaces.",
    comparison_limited: "Comparaison limitée sur ce dessin très fragmenté ; la proposition équilibrée a été contrôlée.",
    comparison_region_budget: "Dessin très fragmenté : alternatives non calculées pour limiter le coût de génération. Réduisez les couleurs ou les parasites pour comparer.",
    geometry_checks_passed: "Contrôles géométriques validés sur les points machine.",
    needs_review: "Des détails ou points nécessitent encore une vérification.",
  };
  return labels[reason] ?? reason;
}
