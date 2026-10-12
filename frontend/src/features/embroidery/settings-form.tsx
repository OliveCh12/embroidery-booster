"use client";

import { Accordion, Button, Card, Form, Separator, Spinner } from "@heroui/react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ChoiceSetting, NumberSetting, ToggleSetting } from "./controls";
import { applyMachineProfile, applyMaterialPreset } from "./settings";
import type { Capabilities, GenerationSettings } from "./types";

function AdvancedSection({ title, children }: { title: string; children: ReactNode }) {
  return <Accordion.Item>
    <Accordion.Heading><Accordion.Trigger>{title}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
    <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">{children}</Accordion.Body></Accordion.Panel>
  </Accordion.Item>;
}

export function SettingsForm({ settings: s, onChange, capabilities, busy, canGenerate, onSubmit, children }: {
  settings: GenerationSettings; onChange: (settings: GenerationSettings) => void;
  capabilities?: Capabilities; busy: boolean; canGenerate: boolean; onSubmit: () => void; children: ReactNode;
}) {
  const settingsId = useId();
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  function update<K extends keyof GenerationSettings>(key: K, value: GenerationSettings[K]) {
    onChange({ ...s, [key]: value });
  }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (canGenerate) onSubmit(); }
  const direct = s.method !== "inkstitch";
  const hoopLimit = capabilities?.machine_profiles?.[s.machine]?.max_area_mm ?? 500;
  return (
    <Form onSubmit={submit} onInvalid={() => setSettingsExpanded(true)} className="flex min-h-0 w-full flex-1 flex-col gap-4">
      <div className="flex min-h-0 flex-col gap-4 md:flex-1 md:overflow-y-auto md:overscroll-contain" aria-label="Réglages de la broderie">
        {children}
        <Button variant="secondary" fullWidth className="shrink-0 justify-between md:hidden" aria-expanded={settingsExpanded} aria-controls={settingsId} onPress={() => setSettingsExpanded(value => !value)}>
          Réglages de broderie<ChevronDown size={16} className={settingsExpanded ? "rotate-180" : undefined} />
        </Button>
        <Card id={settingsId} className={`w-full shrink-0 gap-4 md:flex ${settingsExpanded ? "flex" : "hidden"}`}>
          <Card.Header><Card.Title>Broderie</Card.Title></Card.Header>
          <Card.Content className="gap-4">
            <ChoiceSetting label="Méthode" value={s.method} disabled={busy} onChange={value => update("method", value)} options={[
              { value: "direct", label: "Automatique · recommandé" }, { value: "both", label: "Comparer les deux moteurs" }, { value: "inkstitch", label: "Colonnes Ink/Stitch" },
            ]} />
            <Separator />
            <p className="text-xs font-medium text-muted">Dimensions et cadre</p>
            <ChoiceSetting label="Machine" value={s.machine} disabled={busy || !capabilities?.machine_profiles}
              onChange={value => { if (capabilities) onChange(applyMachineProfile(s, value, capabilities)); }}
              options={Object.entries(capabilities?.machine_profiles ?? {}).map(([value, profile]) => ({ value: value as GenerationSettings["machine"], label: profile.label }))} />
            <NumberSetting label="Largeur du dessin (mm)" value={s.design_width} onChange={value => update("design_width", value)} min={1} max={500} step={0.1} optional disabled={busy} />
            <fieldset className="space-y-2">
              <legend className="text-sm">Cadre (mm)</legend>
              <div className="grid grid-cols-2 gap-4">
                <NumberSetting label="Largeur" value={s.hoop_width} onChange={value => update("hoop_width", value ?? NaN)} min={10} max={hoopLimit} disabled={busy} />
                <NumberSetting label="Hauteur" value={s.hoop_height} onChange={value => update("hoop_height", value ?? NaN)} min={10} max={hoopLimit} disabled={busy} />
              </div>
            </fieldset>
            <ToggleSetting label="Adapter au cadre" value={s.fit_to_hoop} onChange={value => update("fit_to_hoop", value)} disabled={busy} />
            {s.machine === "brother-skitch-pp1" && <p className="text-xs leading-relaxed text-muted">Importez le PES dans Artspira et activez la coupe des fils de saut sur la machine. Le profil propose 6 couleurs et des satins jusqu’à 7 mm ; ces réglages restent modifiables.</p>}
            <Separator />
            <p className="text-xs font-medium text-muted">Tissu et fil</p>
            <ChoiceSetting label="Tissu" value={s.fabric} disabled={busy || !capabilities}
              onChange={value => onChange(applyMaterialPreset(s, value, s.thread_weight, capabilities))} options={[
                { value: "custom", label: "À préciser / manuel" }, { value: "stable", label: "Coton · stable" }, { value: "stretch", label: "Jersey · extensible" }, { value: "textured", label: "Éponge · texturé" },
              ]} />
            <div className="grid grid-cols-2 gap-4">
              <ChoiceSetting label="Fil" value={s.thread_weight} disabled={busy || !capabilities}
                onChange={value => onChange(applyMaterialPreset(s, s.fabric, value, capabilities))} options={[
                  { value: "40", label: "40 wt" }, { value: "60", label: "60 wt · fin" }, { value: "30", label: "30 wt · épais" },
                ]} />
              <ChoiceSetting label="Stabilisateur" value={s.stabilizer} disabled={busy} onChange={value => update("stabilizer", value)} options={[
                { value: "unspecified", label: "À préciser" }, { value: "cutaway", label: "À découper" }, { value: "tearaway", label: "À déchirer" }, { value: "washaway", label: "Hydrosoluble" },
              ]} />
            </div>
            <p className="text-xs leading-relaxed text-muted">Le tissu ajuste densité, compensation et sous-couche. Pour le jersey, prévoyez un support à découper ; sur l’éponge, une couche hydrosoluble en surface aide à retenir les points. Validez sur une chute du tissu.</p>
            {direct && <ToggleSetting label="Choisir les types de points" value={s.auto_select} onChange={value => update("auto_select", value)} disabled={busy} />}
            <Accordion className="w-full">
              <AdvancedSection title="Points et sous-couche">
                <div className="grid grid-cols-2 gap-4">
                  <NumberSetting label="Pas satin (mm)" value={s.stitch_spacing} onChange={value => update("stitch_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={busy} />
                  {direct && <NumberSetting label="Pas fill (mm)" value={s.fill_spacing} onChange={value => update("fill_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={busy} />}
                  <NumberSetting label="Compensation (mm)" value={s.pull_compensation} onChange={value => update("pull_compensation", value ?? NaN)} min={0} max={0.5} step={0.05} disabled={busy} />
                  <NumberSetting label="Point maximal (mm)" value={s.max_stitch} onChange={value => update("max_stitch", value ?? NaN)} min={2} max={12} step={0.5} disabled={busy} />
                </div>
                <ToggleSetting label="Sous-couche" value={s.underlay} onChange={value => update("underlay", value)} disabled={busy} />
                {direct && <>
                <NumberSetting label="Largeur satin maximale (mm)" value={s.max_satin_width} onChange={value => update("max_satin_width", value ?? NaN)} min={2} max={12} step={0.5} disabled={busy} />
                <NumberSetting label="Point droit (mm)" value={s.running_length} onChange={value => update("running_length", value ?? NaN)} min={0.5} max={5} step={0.1} disabled={busy} />
                <ToggleSetting label="Angle fill automatique" value={s.auto_fill_angle} onChange={value => update("auto_fill_angle", value)} disabled={busy} />
                {!s.auto_fill_angle && <NumberSetting label="Angle fill (°)" value={s.fill_angle} onChange={value => update("fill_angle", value ?? NaN)} min={-180} max={180} step={5} disabled={busy} />}
                {!s.auto_select && <ToggleSetting label="Compléter les zones larges" value={s.fill_gaps} onChange={value => update("fill_gaps", value)} disabled={busy} />}
                {!s.auto_select && <ChoiceSetting label="Zones larges" value={s.wide_mode} disabled={busy} onChange={value => update("wide_mode", value)} options={[{ value: "fill", label: "Fill tatami" }, { value: "split", label: "Satin subdivisé" }]} />}
                </>}
              </AdvancedSection>
              <AdvancedSection title="Interprétation de l’image">
                {direct && s.auto_select && <>
                  <ToggleSetting label="Conserver les couleurs" value={s.preserve_colors} onChange={value => update("preserve_colors", value)} disabled={busy} />
                  {s.preserve_colors && <NumberSetting label="Couleurs maximum" value={s.max_colors} onChange={value => update("max_colors", value ?? NaN)} min={1} max={32} disabled={busy} />}
                </>}
                <NumberSetting label="Seuil noir / blanc" value={s.raster_threshold} onChange={value => update("raster_threshold", value)} min={0} max={255} optional disabled={busy} />
                <ToggleSetting label="Inverser clair / foncé" value={s.raster_invert} onChange={value => update("raster_invert", value)} disabled={busy} />
                <p className="text-xs text-muted">Le moteur automatique conserve les couleurs visibles. Pour une image, il retire le fond uniforme ; un seuil manuel produit une silhouette monochrome. Vérifiez le dessin interprété.</p>
              </AdvancedSection>
              <AdvancedSection title="Guides et diagnostics">
                <ToggleSetting label="Affiner les courbes" value={s.auto_optimize} onChange={value => update("auto_optimize", value)} disabled={busy} />
                <div className="grid grid-cols-2 gap-4">
                  <NumberSetting label="Rungs (mm)" value={s.spacing} onChange={value => update("spacing", value ?? NaN)} min={0.1} max={50} step={0.1} disabled={busy} />
                  <NumberSetting label="Densité des guides" value={s.density} onChange={value => update("density", value ?? NaN)} min={0.1} max={10} step={0.1} disabled={busy} />
                </div>
                <NumberSetting label="Résolution (DPI)" value={s.dpi} onChange={value => update("dpi", value ?? NaN)} min={36} max={2400} disabled={busy} />
                <ToggleSetting label="Images de diagnostic" value={s.debug} onChange={value => update("debug", value)} disabled={busy} />
                <p className="text-xs text-muted">Les guides règlent la géométrie, pas la densité des points machine.</p>
              </AdvancedSection>
            </Accordion>
            {!direct || s.method === "both" ? <>
              <ToggleSetting label="Calcul natif Ink/Stitch" value={s.export} onChange={value => update("export", value)} disabled={busy || !capabilities?.inkstitch} />
              {!capabilities?.inkstitch && <p className="text-xs text-muted">Les SVG éditables restent disponibles. Le calcul natif nécessite Ink/Stitch installé.</p>}
            </> : null}
          </Card.Content>
        </Card>
      </div>
      <div className="shrink-0">
        <Button type="submit" fullWidth isDisabled={!canGenerate || busy}>
          {busy ? <Spinner size="sm" color="current" /> : <ArrowRight size={17} />}
          {busy ? "Génération en cours…" : s.method === "both" ? "Générer et comparer" : s.method === "inkstitch" ? "Générer les colonnes" : "Générer ma broderie"}
        </Button>
      </div>
    </Form>
  );
}
