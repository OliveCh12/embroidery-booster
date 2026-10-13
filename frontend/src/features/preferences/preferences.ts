import { applyMachineProfile, applyMaterialPreset, DEFAULT_SETTINGS } from "../embroidery/settings";
import type { Capabilities, Fabric, GenerationSettings, Machine, Stabilizer, ThreadWeight } from "../embroidery/types";

export type AppPreferences = Pick<GenerationSettings, "machine" | "fabric" | "thread_weight" | "stabilizer">;

export const PREFS_STORAGE_KEY = "embroidery-booster.preferences.v1";
export const DEFAULT_PREFERENCES: AppPreferences = {
  machine: DEFAULT_SETTINGS.machine,
  fabric: DEFAULT_SETTINGS.fabric,
  thread_weight: DEFAULT_SETTINGS.thread_weight,
  stabilizer: DEFAULT_SETTINGS.stabilizer,
};

const machines: readonly Machine[] = ["generic", "brother-skitch-pp1"];
const fabrics: readonly Fabric[] = ["custom", "stable", "stretch", "textured"];
const weights: readonly ThreadWeight[] = ["30", "40", "60"];
const stabilizers: readonly Stabilizer[] = ["unspecified", "cutaway", "tearaway", "washaway"];

function choice<T extends string>(value: unknown, values: readonly T[], fallback: T): T {
  return values.find(option => option === value) ?? fallback;
}

export function parsePreferences(raw: string | null): AppPreferences {
  let value: unknown;
  try { value = JSON.parse(raw ?? "null"); }
  catch { return { ...DEFAULT_PREFERENCES }; }
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ...DEFAULT_PREFERENCES };
  const source = value as Record<string, unknown>;
  return {
    machine: choice(source.machine, machines, DEFAULT_PREFERENCES.machine),
    fabric: choice(source.fabric, fabrics, DEFAULT_PREFERENCES.fabric),
    thread_weight: choice(source.thread_weight, weights, DEFAULT_PREFERENCES.thread_weight),
    stabilizer: choice(source.stabilizer, stabilizers, DEFAULT_PREFERENCES.stabilizer),
  };
}

export function applyPreferences(settings: GenerationSettings, preferences: AppPreferences, capabilities: Capabilities): GenerationSettings {
  const machine = applyMachineProfile(settings, preferences.machine, capabilities);
  const material = applyMaterialPreset(machine, preferences.fabric, preferences.thread_weight, capabilities);
  return { ...material, stabilizer: preferences.stabilizer };
}
