"use client";

import { Accordion, Button, Card, Form, Separator, Spinner } from "@heroui/react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ChoiceSetting, NumberSetting, ToggleSetting } from "./controls";
import { applyMachineProfile, applyMaterialPreset, BACKGROUND_MODE_OPTIONS, STITCH_TYPE_OPTIONS } from "./settings";
import type { Capabilities, GenerationSettings } from "./types";

function AdvancedSection({ title, children }: { title: string; children: ReactNode }) {
  return <Accordion.Item>
    <Accordion.Heading><Accordion.Trigger>{title}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
    <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">{children}</Accordion.Body></Accordion.Panel>
  </Accordion.Item>;
}

export function SettingsForm({ settings: s, onChange, capabilities, busy, canGenerate, onSubmit }: {
  settings: GenerationSettings; onChange: (settings: GenerationSettings) => void;
  capabilities?: Capabilities; busy: boolean; canGenerate: boolean; onSubmit: () => void;
}) {
  const settingsId = useId();
  const [expanded, setExpanded] = useState(false);
  function update<K extends keyof GenerationSettings>(key: K, value: GenerationSettings[K]) { onChange({ ...s, [key]: value }); }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (canGenerate) onSubmit(); }
  const hoopLimit = capabilities?.machine_profiles?.[s.machine]?.max_area_mm ?? 500;
  const manualDisabled = busy || s.auto_adjust;
  return <Form onSubmit={submit} onInvalid={() => setExpanded(true)} className="flex min-h-0 w-full flex-1 flex-col gap-4">
    <div className="flex min-h-0 flex-col gap-4 md:flex-1 md:overflow-y-auto md:overscroll-contain" aria-label="Réglages de la broderie">
      <Button variant="secondary" fullWidth className="shrink-0 justify-between md:hidden" aria-expanded={expanded} aria-controls={settingsId} onPress={() => setExpanded(value => !value)}>
        Réglages de broderie<ChevronDown size={16} className={expanded ? "rotate-180" : undefined} />
      </Button>
      <Card id={settingsId} className={`w-full shrink-0 gap-4 md:flex ${expanded ? "flex" : "hidden"}`}>
        <Card.Header><Card.Title>Préparation</Card.Title></Card.Header>
        <Card.Content className="gap-4">
          <ChoiceSetting label="Machine" value={s.machine} disabled={busy || !capabilities?.machine_profiles}
            onChange={value => { if (capabilities) onChange(applyMachineProfile(s, value, capabilities)); }}
            options={Object.entries(capabilities?.machine_profiles ?? {}).map(([value, profile]) => ({ value: value as GenerationSettings["machine"], label: profile.label }))} />
          <NumberSetting label="Largeur du dessin (mm)" value={s.design_width} onChange={value => update("design_width", value)} min={1} max={500} step={0.1} optional disabled={busy} />
          <fieldset className="flex flex-col gap-4">
            <legend className="mb-4 text-sm">Cadre (mm)</legend>
            <div className="grid grid-cols-2 gap-4">
              <NumberSetting label="Largeur" value={s.hoop_width} onChange={value => update("hoop_width", value ?? NaN)} min={10} max={hoopLimit} disabled={busy} />
              <NumberSetting label="Hauteur" value={s.hoop_height} onChange={value => update("hoop_height", value ?? NaN)} min={10} max={hoopLimit} disabled={busy} />
            </div>
          </fieldset>
          <ToggleSetting label="Adapter au cadre" value={s.fit_to_hoop} onChange={value => update("fit_to_hoop", value)} disabled={busy} />
          {s.machine === "brother-skitch-pp1" && <p className="text-xs leading-relaxed text-muted">Cadre maximal de 100 × 100 mm. Importez le PES dans Artspira ; les changements de couleur se font manuellement.</p>}
          <Separator />
          <ChoiceSetting label="Tissu" value={s.fabric} disabled={busy || !capabilities}
            onChange={value => onChange(applyMaterialPreset(s, value, s.thread_weight, capabilities))} options={[
              { value: "custom", label: "À préciser / personnalisé" }, { value: "stable", label: "Coton · stable" }, { value: "stretch", label: "Jersey · extensible" }, { value: "textured", label: "Éponge · texturé" },
            ]} />
          <div className="grid grid-cols-2 gap-4">
            <ChoiceSetting label="Fil" value={s.thread_weight} disabled={busy || !capabilities} onChange={value => onChange(applyMaterialPreset(s, s.fabric, value, capabilities))} options={[
              { value: "40", label: "40 wt" }, { value: "60", label: "60 wt · fin" }, { value: "30", label: "30 wt · épais" },
            ]} />
            <ChoiceSetting label="Stabilisateur" value={s.stabilizer} disabled={busy} onChange={value => update("stabilizer", value)} options={[
              { value: "unspecified", label: "À préciser" }, { value: "cutaway", label: "À découper" }, { value: "tearaway", label: "À déchirer" }, { value: "washaway", label: "Hydrosoluble" },
            ]} />
          </div>
          <ChoiceSetting label="Type de points" value={s.stitch_type} onChange={value => update("stitch_type", value)} disabled={busy} options={STITCH_TYPE_OPTIONS} />
          {s.stitch_type === "satin" && <p className="text-xs leading-relaxed text-muted">Le satin forcé est refusé si la forme ne permet pas un satin régulier dans les limites de la machine. Choisissez Auto ou Tatami pour les zones larges ou complexes.</p>}
          {s.stitch_type === "running" && <p className="text-xs leading-relaxed text-muted">Le point droit suit les lignes fines ; il ne couvre pas une surface comme le satin ou le tatami.</p>}
          <ToggleSetting label="Ajustement automatique" value={s.auto_adjust} onChange={value => update("auto_adjust", value)} disabled={busy} />
          <p className="text-xs leading-relaxed text-muted">Le dessin et le tissu guident densité, compensation et sous-couche. Les réglages appliqués sont indiqués après génération. Désactivez l’ajustement pour régler les points manuellement.</p>
          <Accordion className="w-full">
            <AdvancedSection title="Points et sous-couche">
              <div className="grid grid-cols-2 gap-4">
                <NumberSetting label="Pas satin (mm)" value={s.stitch_spacing} onChange={value => update("stitch_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={manualDisabled} />
                <NumberSetting label="Pas fill (mm)" value={s.fill_spacing} onChange={value => update("fill_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={manualDisabled} />
                <NumberSetting label="Compensation (mm)" value={s.pull_compensation} onChange={value => update("pull_compensation", value ?? NaN)} min={0} max={0.5} step={0.05} disabled={manualDisabled} />
                <NumberSetting label="Point maximal (mm)" value={s.max_stitch} onChange={value => update("max_stitch", value ?? NaN)} min={2} max={12} step={0.5} disabled={manualDisabled} />
              </div>
              <ToggleSetting label="Sous-couche" value={s.underlay} onChange={value => update("underlay", value)} disabled={manualDisabled} />
              <NumberSetting label="Largeur satin maximale (mm)" value={s.max_satin_width} onChange={value => update("max_satin_width", value ?? NaN)} min={2} max={12} step={0.5} disabled={manualDisabled} />
              <NumberSetting label="Point droit (mm)" value={s.running_length} onChange={value => update("running_length", value ?? NaN)} min={0.5} max={5} step={0.1} disabled={manualDisabled} />
              <ToggleSetting label="Angle fill automatique" value={s.auto_fill_angle} onChange={value => update("auto_fill_angle", value)} disabled={busy} />
              {!s.auto_fill_angle && <NumberSetting label="Angle fill (°)" value={s.fill_angle} onChange={value => update("fill_angle", value ?? NaN)} min={-180} max={180} step={5} disabled={busy} />}
            </AdvancedSection>
            <AdvancedSection title="Interprétation de l’image">
              <ChoiceSetting label="Fond du dessin" value={s.background_mode} onChange={value => update("background_mode", value)} disabled={busy} options={BACKGROUND_MODE_OPTIONS} />
              <ToggleSetting label="Réduire les parasites" value={s.raster_cleanup} onChange={value => update("raster_cleanup", value)} disabled={busy} />
              <ToggleSetting label="Conserver les couleurs" value={s.preserve_colors} onChange={value => update("preserve_colors", value)} disabled={busy} />
              {s.preserve_colors && <NumberSetting label="Couleurs maximum" value={s.max_colors} onChange={value => update("max_colors", value ?? NaN)} min={1} max={32} disabled={busy} />}
              <NumberSetting label="Seuil noir / blanc" value={s.raster_threshold} onChange={value => update("raster_threshold", value)} min={0} max={255} optional disabled={busy} />
              <ToggleSetting label="Inverser clair / foncé" value={s.raster_invert} onChange={value => update("raster_invert", value)} disabled={busy} />
              <p className="text-xs leading-relaxed text-muted">Auto retire un fond uniforme reconnu. Conserver garde les aplats de fond ; Supprimer demande leur retrait. Un seuil manuel produit une silhouette monochrome. Vérifiez le dessin interprété.</p>
            </AdvancedSection>
          </Accordion>
        </Card.Content>
      </Card>
    </div>
    <Button type="submit" fullWidth className="shrink-0" isDisabled={!canGenerate || busy}>{busy ? <Spinner size="sm" color="current" /> : <ArrowRight size={17} />}{busy ? "Génération en cours…" : "Générer ma broderie"}</Button>
  </Form>;
}
