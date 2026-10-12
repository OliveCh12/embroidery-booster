export const STITCH_PHASE = { top: 0, underlay: 1, travel: 2, lock: 3 } as const;

export interface StitchPlan {
  count: number;
  points: Float32Array;
  codes: Uint8Array;
  colors: Uint8Array;
  stitches: Uint32Array;
  phases: Uint8Array;
  threads: string[];
  hoop: { width: number; height: number };
  bounds: [number, number, number, number];
  command: { stitch: number; jump: number; trim: number; color_change: number; end: number; mask: number };
  colorChanges: number[];
  stitchesPerMinute: number;
  threadWeight: 30 | 40 | 60 | null;
}

export interface ThreadSequenceStep {
  index: number;
  color: string;
  name: string;
  startCursor: number;
  endCursor: number;
  stitchCount: number;
  firstStitch: number | null;
  lastStitch: number | null;
  startMinutes: number;
  endMinutes: number;
  durationMinutes: number;
}

export type ThreadStepStatus = "pending" | "active" | "completed";

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Plan de points invalide.");
  return value as Record<string, unknown>;
}

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }

export function parseStitchPlan(value: unknown): StitchPlan {
  const source = record(value);
  if (source.schema_version !== 3 || source.units !== "0.1mm" || source.coordinate_frame !== "hoop_center") throw new Error("Ce plan de points est incompatible. Régénérez la broderie.");
  const commands = source.commands;
  if (!Array.isArray(commands) || !commands.length || commands.length > 1_000_000) throw new Error("Le plan est vide ou dépasse la limite de lecture.");
  if (!Array.isArray(source.threads) || !source.threads.length || source.threads.length > 32 || !source.threads.every(color => typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color))) throw new Error("Palette de fils invalide.");
  const hoop = record(source.hoop);
  if (!finite(hoop.width_mm) || !finite(hoop.height_mm) || hoop.width_mm < 10 || hoop.height_mm < 10 || hoop.width_mm > 500 || hoop.height_mm > 500) throw new Error("Dimensions du cadre invalides.");
  const constants = record(source.command_codes);
  const command = {} as StitchPlan["command"];
  for (const key of ["stitch", "jump", "trim", "color_change", "end", "mask"] as const) {
    const code = constants[key === "mask" ? "command_mask" : key];
    if (!Number.isInteger(code) || (code as number) < 0 || (code as number) > 255) throw new Error("Commandes machine invalides.");
    command[key] = code as number;
  }
  const count = commands.length;
  const validCodes = new Set([command.stitch, command.jump, command.trim, command.color_change, command.end]);
  const points = new Float32Array(count * 2);
  const codes = new Uint8Array(count);
  const colors = new Uint8Array(count);
  const stitches = new Uint32Array(count + 1);
  const phases = new Uint8Array(count);
  const colorChanges: number[] = [];
  let color = 0;
  const bounds: StitchPlan["bounds"] = [Infinity, Infinity, -Infinity, -Infinity];
  for (let index = 0; index < count; index++) {
    const item = commands[index];
    if (!Array.isArray(item) || item.length !== 3 || !item.every(Number.isInteger) || Math.abs(item[0]) > 100_000 || Math.abs(item[1]) > 100_000 || item[2] < 0) throw new Error("Coordonnées de points invalides.");
    const code = item[2] & command.mask;
    if (!validCodes.has(code)) throw new Error("Le plan contient une commande non prise en charge.");
    codes[index] = code;
    points[index * 2] = item[0] / 10;
    points[index * 2 + 1] = item[1] / 10;
    if (code === command.color_change) { color++; colorChanges.push(index); }
    if (color >= source.threads.length) throw new Error("Le changement de fil ne correspond pas à la palette.");
    colors[index] = color;
    stitches[index + 1] = stitches[index] + (code === command.stitch ? 1 : 0);
    if (code === command.stitch) {
      bounds[0] = Math.min(bounds[0], item[0] / 10); bounds[1] = Math.min(bounds[1], item[1] / 10);
      bounds[2] = Math.max(bounds[2], item[0] / 10); bounds[3] = Math.max(bounds[3], item[1] / 10);
    }
  }
  if (!stitches[count]) throw new Error("Ce plan ne contient aucun point cousu.");
  const runs = Array.isArray(source.runs) ? source.runs : Array.isArray(source.underlay_runs) ? source.underlay_runs.map(run => ({ ...record(run), kind: "underlay" })) : [];
  for (const value of runs) {
    const run = record(value);
    if (!Number.isInteger(run.start) || !Number.isInteger(run.end) || (run.start as number) < 0 || (run.end as number) > count || (run.end as number) < (run.start as number)) throw new Error("Plage de phase invalide.");
    const phase = run.kind === "underlay" ? STITCH_PHASE.underlay : run.kind === "travel" ? STITCH_PHASE.travel : run.kind === "lock" ? STITCH_PHASE.lock : STITCH_PHASE.top;
    // A run includes its preceding context node; only following segments belong to the phase.
    phases.fill(phase, (run.start as number) + 1, run.end as number);
  }
  const machine = source.machine ? record(source.machine) : {};
  const stitchesPerMinute = finite(machine.stitches_per_minute) && machine.stitches_per_minute > 0 ? machine.stitches_per_minute : 400;
  const params = source.params && typeof source.params === "object" && !Array.isArray(source.params) ? source.params as Record<string, unknown> : {};
  const weight = params.thread_weight;
  const threadWeight = weight === 30 || weight === 40 || weight === 60 ? weight : null;
  return { count, points, codes, colors, stitches, phases, threads: source.threads, hoop: { width: hoop.width_mm, height: hoop.height_mm }, bounds, command, colorChanges, stitchesPerMinute, threadWeight };
}

export function describeThreadColor(hex: string): string {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return "Couleur inconnue";
  const rgb = [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const [red, green, blue] = rgb;
  const maximum = Math.max(...rgb), minimum = Math.min(...rgb), chroma = maximum - minimum;
  if (chroma <= Math.max(12 / 255, maximum * 0.08)) {
    if (maximum < 28 / 255) return "Noir";
    if (maximum < 95 / 255) return "Gris foncé";
    if (maximum < 185 / 255) return "Gris";
    return minimum >= 245 / 255 ? "Blanc" : "Gris clair";
  }
  const saturation = chroma / maximum;
  const sector = maximum === red ? (green - blue) / chroma : maximum === green ? (blue - red) / chroma + 2 : (red - green) / chroma + 4;
  const hue = ((sector * 60) + 360) % 360;
  if (hue >= 15 && hue < 70 && maximum < 0.68) return "Marron";
  if (hue >= 15 && hue < 70 && saturation < 0.35) return "Beige";
  const name = hue < 15 || hue >= 345 ? "Rouge" : hue < 45 ? "Orange" : hue < 70 ? "Jaune" : hue < 165 ? "Vert" : hue < 200 ? "Turquoise" : hue < 255 ? "Bleu" : hue < 290 ? "Violet" : "Rose";
  return maximum < 0.55 ? `${name} foncé` : saturation < 0.4 ? `${name} clair` : name;
}

export function buildThreadSequence(plan: StitchPlan): ThreadSequenceStep[] {
  return Array.from({ length: plan.colorChanges.length + 1 }, (_, index) => {
    // Cursor boundaries exclude COLOR_CHANGE itself; selecting a passage resumes with its new thread.
    const startCursor = index === 0 ? 0 : plan.colorChanges[index - 1] + 1;
    const endCursor = plan.colorChanges[index] ?? plan.count;
    const before = plan.stitches[startCursor], after = plan.stitches[endCursor];
    const stitchCount = after - before;
    return {
      index, color: plan.threads[index].toUpperCase(), name: describeThreadColor(plan.threads[index]),
      startCursor, endCursor, stitchCount,
      firstStitch: stitchCount ? before + 1 : null, lastStitch: stitchCount ? after : null,
      startMinutes: before / plan.stitchesPerMinute, endMinutes: after / plan.stitchesPerMinute,
      durationMinutes: stitchCount / plan.stitchesPerMinute,
    };
  });
}

export function threadStepStatus(step: ThreadSequenceStep, cursor: number): ThreadStepStatus {
  return cursor >= step.endCursor ? "completed" : cursor >= step.startCursor ? "active" : "pending";
}

export function viewport(width: number, height: number, hoopWidth: number, hoopHeight: number) {
  const scale = Math.min(Math.max(1, width - 72) / hoopWidth, Math.max(1, height - 56) / hoopHeight);
  return { scale, centerX: width / 2, centerY: height / 2, left: (width - hoopWidth * scale) / 2, top: (height - hoopHeight * scale) / 2 };
}

export function pointAt(plan: StitchPlan, cursor: number): [number, number] | null {
  const index = Math.min(plan.count, Math.max(0, Math.floor(cursor))) - 1;
  return index < 0 ? null : [plan.points[index * 2], plan.points[index * 2 + 1]];
}

export function advancePlayback(plan: StitchPlan, cursor: number, stitchBudget: number, pauseAtColorChange: boolean) {
  const target = plan.stitches[cursor] + stitchBudget;
  let low = cursor, high = plan.count;
  while (low < high) { const middle = (low + high + 1) >>> 1; if (plan.stitches[middle] <= target) low = middle; else high = middle - 1; }
  if (pauseAtColorChange) {
    const change = plan.colorChanges.find(index => index >= cursor && index < low);
    if (change !== undefined) return { cursor: change + 1, pausedForColor: true };
  }
  return { cursor: low, pausedForColor: false };
}

export function eventLabel(plan: StitchPlan, cursor: number) {
  if (!cursor) return "Départ";
  const code = plan.codes[Math.min(plan.count, cursor) - 1];
  if (code === plan.command.jump) return "Déplacement · aiguille levée";
  if (code === plan.command.trim) return "Coupe du fil";
  if (code === plan.command.color_change) return "Changement de fil";
  if (code === plan.command.end) return "Broderie terminée";
  const phase = plan.phases[cursor - 1];
  if (phase === STITCH_PHASE.underlay) return "Sous-couche";
  if (phase === STITCH_PHASE.travel) return "Liaison cousue";
  if (phase === STITCH_PHASE.lock) return "Ancrage du fil";
  return "Point cousu";
}
