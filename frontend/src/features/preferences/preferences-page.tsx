"use client";

import { Alert, Button } from "@heroui/react";
import { Check, Monitor, RotateCcw, Save, Shirt } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";
import { ChoiceSetting } from "@/features/embroidery/controls";
import { useCapabilities } from "@/features/embroidery/use-capabilities";
import { DEFAULT_PREFERENCES, type AppPreferences } from "./preferences";
import { savePreferences, usePreferences } from "./use-preferences";

export function PreferencesPage() {
  const { preferences, ready } = usePreferences();
  const [draft, setDraft] = useState<AppPreferences | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  const capabilities = useCapabilities();
  const { theme, setTheme } = useTheme();
  const settings = draft ?? preferences;
  const changed = Object.keys(settings).some(key => settings[key as keyof AppPreferences] !== preferences[key as keyof AppPreferences]);

  function update<K extends keyof AppPreferences>(key: K, value: AppPreferences[K]) {
    setDraft({ ...settings, [key]: value });
    setSaved(false);
    setError(false);
  }
  function save(next: AppPreferences) {
    if (savePreferences(next)) { setDraft(null); setError(false); setSaved(true); }
    else { setError(true); setSaved(false); }
  }

  return <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <section className="flex flex-col gap-4 border-b border-border pb-4" aria-labelledby="material-defaults">
        <h2 id="material-defaults" className="flex items-center gap-4 text-sm font-medium"><Shirt size={18} className="text-muted" aria-hidden="true" />Profils par défaut</h2>
        <p className="text-sm text-muted">Repris à l’ouverture de l’atelier, puis ajustables pour chaque dessin. Les profils de tissu utilisent les réglages du moteur.</p>
        {capabilities.isError && <Alert status="warning"><Alert.Indicator /><Alert.Content><Alert.Title>Machine indisponible</Alert.Title><Alert.Description>La liste des machines sera disponible quand le moteur sera connecté.</Alert.Description></Alert.Content></Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <ChoiceSetting label="Machine" value={settings.machine} disabled={!ready || !capabilities.data}
            onChange={value => update("machine", value)} options={Object.entries(capabilities.data?.machine_profiles ?? {}).map(([value, profile]) => ({ value: value as AppPreferences["machine"], label: profile.label }))} />
          <ChoiceSetting label="Profil de tissu" value={settings.fabric} disabled={!ready} onChange={value => update("fabric", value)} options={[
            { value: "custom", label: "À préciser / personnalisé" }, { value: "stable", label: "Coton · stable" }, { value: "stretch", label: "Jersey · extensible" }, { value: "textured", label: "Éponge · texturé" },
          ]} />
          <ChoiceSetting label="Fil" value={settings.thread_weight} disabled={!ready} onChange={value => update("thread_weight", value)} options={[
            { value: "40", label: "40 wt" }, { value: "60", label: "60 wt · fin" }, { value: "30", label: "30 wt · épais" },
          ]} />
          <ChoiceSetting label="Stabilisateur" value={settings.stabilizer} disabled={!ready} onChange={value => update("stabilizer", value)} options={[
            { value: "unspecified", label: "À préciser" }, { value: "cutaway", label: "À découper" }, { value: "tearaway", label: "À déchirer" }, { value: "washaway", label: "Hydrosoluble" },
          ]} />
        </div>
        {error && <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Préférences non enregistrées</Alert.Title><Alert.Description>Le stockage du navigateur n’est pas disponible. Vos réglages restent modifiables dans l’atelier.</Alert.Description></Alert.Content></Alert>}
        <div className="flex flex-wrap items-center gap-4">
          <Button size="sm" variant="primary" isDisabled={!ready || !changed} onPress={() => save(settings)}><Save size={15} aria-hidden="true" />Enregistrer</Button>
          <Button size="sm" variant="ghost" isDisabled={!ready} onPress={() => save(DEFAULT_PREFERENCES)}><RotateCcw size={15} aria-hidden="true" />Réinitialiser</Button>
          <span className="flex items-center gap-2 text-xs text-muted" role="status">{saved && <><Check size={14} aria-hidden="true" />Enregistré dans ce navigateur</>}</span>
        </div>
      </section>
      <section className="flex flex-col gap-4" aria-labelledby="appearance-settings">
        <h2 id="appearance-settings" className="flex items-center gap-4 text-sm font-medium"><Monitor size={18} className="text-muted" aria-hidden="true" />Apparence</h2>
        <div className="max-w-sm"><ChoiceSetting label="Thème" value={ready ? theme ?? "system" : "system"} disabled={!ready} onChange={setTheme} options={[
          { value: "system", label: "Système" }, { value: "light", label: "Clair" }, { value: "dark", label: "Sombre" },
        ]} /></div>
      </section>
    </div>
  </div>;
}
