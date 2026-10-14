import { formatNumber } from "../../lib/format";
import type { Decision } from "./types";

const shapeLabels = new Map<string, string>([
  ["outline", "Forme à contreforme"],
  ["stroke", "Trait allongé"],
  ["round_detail", "Détail arrondi"],
  ["compact", "Forme compacte"],
  ["wide_surface", "Surface large"],
]);

export function describeDecision(decision: Decision): string | null {
  let reason: string | null = null;
  switch (decision.reason) {
    case "complete_regular_column":
      if (decision.method === "satin") reason = "Colonnes satin vérifiées sur les points machine.";
      break;
    case "complete_continuous_columns":
      if (decision.method === "satin") reason = "Satin continu vérifié, avec moins de raccords.";
      break;
    case "complete_split_columns":
      if (decision.method === "satin") reason = "Satin divisé en colonnes vérifiées.";
      break;
    case "complete_directional_columns":
      if (decision.method === "satin") reason = "Satin directionnel vérifié sur les points machine.";
      break;
    case "complete_fidelity_columns":
      if (decision.method === "satin") reason = "Satin retenu après comparaison avec le tatami final.";
      break;
    case "exceeds_safe_satin_width": {
      const limit = decision.shape_profile?.safe_satin_width_mm ?? decision.safe_satin_width_mm;
      if (decision.method === "fill") reason = `Limite de largeur satin dépassée${limit != null && Number.isFinite(limit) && limit > 0 ? ` (${formatNumber(limit)} mm)` : ""}.`;
      break;
    }
    case "incomplete_or_broad_column":
      if (decision.method === "fill") reason = "Rails satin incomplets ou trop larges.";
      break;
    case "satin_top_layer_incomplete":
      if (decision.method === "fill") reason = "Satin non retenu : couverture ou sécurité des points insuffisante.";
      break;
    case "satin_geometry_rejected":
      if (decision.method === "fill") reason = "Satin non retenu : géométrie incompatible avec les points machine.";
      break;
    case "satin_fidelity_regression":
      if (decision.method === "fill") reason = "Tatami conservé : le gain de fidélité du satin n’est pas confirmé.";
      break;
    case "satin_intercolumn_repeats":
      if (decision.method === "fill") reason = "Tatami conservé : le satin concentre davantage les piqûres entre colonnes.";
      break;
    case "coherent_color_fill":
      if (decision.method === "fill") reason = "Tatami harmonisé avec les autres surfaces de cette couleur.";
      break;
    case "equivalent_region_consensus":
      reason = "Stratégie commune aux régions équivalentes.";
      break;
    case "requested_uniform_fill":
      if (decision.method === "fill") reason = "Tatami demandé.";
      break;
    case "below_satin_width":
      if (decision.method === "running") reason = "Détail trop fin pour le satin : point droit retenu.";
      break;
    case "requested_running_contour":
      if (decision.method === "running") reason = "Contours au point droit, sans remplissage de surface.";
      break;
    case "requested_running_centerline":
      if (decision.method === "running") reason = "Point droit sur l’axe de la forme demandé.";
      break;
    case "running_top_layer_incomplete":
      if (decision.method === "fill") reason = "Point droit non retenu : couverture insuffisante.";
      break;
    case "running_geometry_rejected":
      if (decision.method === "fill") reason = "Point droit non retenu : géométrie incompatible avec la machine.";
      break;
    case "below_machine_resolution":
      if (decision.method === "omitted") reason = "Détail sous la résolution utile des points machine.";
      break;
    case "machine_geometry_rejected":
      if (decision.method === "omitted") reason = "Géométrie rejetée sur la grille machine.";
      break;
  }
  const shape = shapeLabels.get(decision.shape_profile?.kind ?? "");
  return [shape, reason].filter(Boolean).join(" · ") || null;
}
