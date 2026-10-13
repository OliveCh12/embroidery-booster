"use client";

import { Accordion, Button, Form, Spinner } from "@heroui/react";
import { ArrowRight, ChevronDown, Frame, Layers3, ScanLine, Shirt, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { ChoiceSetting, NumberSetting, ToggleSetting } from "./controls";
import { applyMachineProfile, applyMaterialPreset, BACKGROUND_MODE_LABELS, BACKGROUND_MODE_OPTIONS, STITCH_TYPE_LABELS, STITCH_TYPE_OPTIONS } from "./settings";
import type { Capabilities, GenerationSettings } from "./types";

function SettingsSection({ id, title, summary, icon: Icon, children }: {
  id: string; title: string; summary: string; icon: LucideIcon; children: ReactNode;
}) {
  return <Accordion.Item id={id} data-settings-section={id}>
    <Accordion.Heading>
      <Accordion.Trigger className="gap-4 py-3">
        <Icon size={18} className="shrink-0 text-muted" aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span>{title}</span>
          <span className="truncate text-xs font-normal text-muted">{summary}</span>
        </span>
        <Accordion.Indicator />
      </Accordion.Trigger>
    </Accordion.Heading>
    <Accordion.Panel>
      <Accordion.Body className="flex flex-col gap-4 text-foreground">{children}</Accordion.Body>
    </Accordion.Panel>
  </Accordion.Item>;
}

export function SettingsForm({ settings: s, onChange, capabilities, busy, canGenerate, onSubmit }: {
  settings: GenerationSettings; onChange: (settings: GenerationSettings) => void;
  capabilities?: Capabilities; busy: boolean; canGenerate: boolean; onSubmit: () => void;
}) {
  const settingsId = useId();
  const [expanded, setExpanded] = useState(false);
  const [openSections, setOpenSections] = useState(new Set(["design", "materials"]));
  function update<K extends keyof GenerationSettings>(key: K, value: GenerationSettings[K]) { onChange({ ...s, [key]: value }); }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (canGenerate) onSubmit(); }
  function revealInvalid(event: FormEvent<HTMLDivElement>) {
    const section = (event.target as HTMLElement).closest<HTMLElement>("[data-settings-section]")?.dataset.settingsSection;
    flushSync(() => {
      setExpanded(true);
      if (section) setOpenSections(current => new Set([...current, section]));
    });
  }
  const hoopLimit = capabilities?.machine_profiles?.[s.machine]?.max_area_mm ?? 500;
  const manualDisabled = busy || s.auto_adjust;
  const fabricLabel = { custom: "Tissu à préciser", stable: "Coton", stretch: "Jersey", textured: "Éponge" }[s.fabric];
  const hoopSummary = Number.isFinite(s.hoop_width) && Number.isFinite(s.hoop_height) ? `${s.hoop_width} × ${s.hoop_height} mm` : "Cadre à préciser";
  return <div onInvalidCapture={revealInvalid} className="flex min-h-0 w-full flex-1 flex-col">
    <Form onSubmit={submit} className="flex min-h-0 w-full flex-1 flex-col gap-4">
    <div className="flex min-h-0 flex-col gap-4 md:flex-1 md:overflow-y-auto md:overscroll-contain" aria-label="Réglages de la broderie">
      <Button variant="secondary" fullWidth className="shrink-0 justify-between md:hidden" aria-expanded={expanded} aria-controls={settingsId} onPress={() => setExpanded(value => !value)}>
        Réglages de broderie<ChevronDown size={16} className={expanded ? "rotate-180" : undefined} />
      </Button>
      <Accordion id={settingsId} variant="surface" allowsMultipleExpanded expandedKeys={openSections}
        onExpandedChange={keys => setOpenSections(new Set(Array.from(keys, String)))}
        className={`w-full shrink-0 md:block ${expanded ? "block" : "hidden"}`}>
        <SettingsSection id="design" title="Dessin et cadre" summary={hoopSummary} icon={Frame}>
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
          {s.machine === "brother-skitch-pp1" && <p className="text-xs leading-relaxed text-muted">Cadre maximal de 100 × 100 mm. Import dans Artspira ; changements de fil manuels.</p>}
        </SettingsSection>
        <SettingsSection id="materials" title="Tissu et fils" summary={`${fabricLabel} · ${s.thread_weight} wt`} icon={Shirt}>
          <ChoiceSetting label="Tissu" value={s.fabric} disabled={busy || !capabilities}
            onChange={value => onChange(applyMaterialPreset(s, value, s.thread_weight, capabilities))} options={[
              { value: "custom", label: "À préciser / personnalisé" }, { value: "stable", label: "Coton · stable" }, { value: "stretch", label: "Jersey · extensible" }, { value: "textured", label: "Éponge · texturé" },
            ]} />
          <ChoiceSetting label="Fil" value={s.thread_weight} disabled={busy || !capabilities} onChange={value => onChange(applyMaterialPreset(s, s.fabric, value, capabilities))} options={[
            { value: "40", label: "40 wt" }, { value: "60", label: "60 wt · fin" }, { value: "30", label: "30 wt · épais" },
          ]} />
          <ChoiceSetting label="Stabilisateur" value={s.stabilizer} disabled={busy} onChange={value => update("stabilizer", value)} options={[
            { value: "unspecified", label: "À préciser" }, { value: "cutaway", label: "À découper" }, { value: "tearaway", label: "À déchirer" }, { value: "washaway", label: "Hydrosoluble" },
          ]} />
        </SettingsSection>
        <SettingsSection id="strategy" title="Stratégie de broderie" summary={`${STITCH_TYPE_LABELS[s.stitch_type]} · Réglages ${s.auto_adjust ? "automatiques" : "manuels"}`} icon={Layers3}>
          <ChoiceSetting label="Type de points" value={s.stitch_type} onChange={value => update("stitch_type", value)} disabled={busy} options={STITCH_TYPE_OPTIONS} />
          {s.stitch_type === "auto" && capabilities?.automatic_variants && <>
            <ToggleSetting label="Comparer les stratégies" value={s.compare_strategies} onChange={value => update("compare_strategies", value)} disabled={busy} />
            <p className="text-xs leading-relaxed text-muted">Le moteur teste les stratégies équilibrée, priorité satin, satin uniforme, tatami uniforme et contours. Les rendus identiques sont regroupés.</p>
          </>}
          {s.stitch_type === "satin" && <p className="text-xs leading-relaxed text-muted">Les colonnes larges sont divisées en satins adjacents. Les jonctions qui échouent aux contrôles restent refusées ; Auto peut choisir le tatami.</p>}
          {s.stitch_type === "running" && <p className="text-xs leading-relaxed text-muted">Le point droit suit les lignes fines ; il ne couvre pas une surface comme le satin ou le tatami.</p>}
          <ToggleSetting label="Ajustement automatique" value={s.auto_adjust} onChange={value => update("auto_adjust", value)} disabled={busy} />
          <p className="text-xs leading-relaxed text-muted">Densité, compensation et sous-couche adaptées au dessin et au tissu. Désactivez l’ajustement pour utiliser les réglages avancés.</p>
          <NumberSetting label="Densité de surface (%)" value={s.density_percent} onChange={value => update("density_percent", value ?? NaN)} min={80} max={120} disabled={busy || !s.auto_adjust} />
          <p className="text-xs leading-relaxed text-muted">100 % reprend la densité du tissu. Augmenter rapproche les rangs, sans ajouter de couches ni de relief 3D. En mode manuel, les pas avancés déterminent la densité.</p>
        </SettingsSection>
        <SettingsSection id="interpretation" title="Interprétation de l’image" summary={`Fond : ${BACKGROUND_MODE_LABELS[s.background_mode]} · ${s.preserve_colors ? `${s.max_colors} couleurs max.` : "Monochrome"}`} icon={ScanLine}>
          <ChoiceSetting label="Fond du dessin" value={s.background_mode} onChange={value => update("background_mode", value)} disabled={busy} options={BACKGROUND_MODE_OPTIONS} />
          <ToggleSetting label="Réduire les parasites" value={s.raster_cleanup} onChange={value => update("raster_cleanup", value)} disabled={busy} />
          <ToggleSetting label="Conserver les couleurs" value={s.preserve_colors} onChange={value => update("preserve_colors", value)} disabled={busy} />
          {s.preserve_colors && <NumberSetting label="Couleurs maximum" value={s.max_colors} onChange={value => update("max_colors", value ?? NaN)} min={1} max={32} disabled={busy} />}
          <NumberSetting label="Seuil noir / blanc" value={s.raster_threshold} onChange={value => update("raster_threshold", value)} min={0} max={255} optional disabled={busy} />
          <ToggleSetting label="Inverser clair / foncé" value={s.raster_invert} onChange={value => update("raster_invert", value)} disabled={busy} />
          <p className="text-xs leading-relaxed text-muted">Auto estime le fond depuis les bords et conserve les badges blancs. Conserver désactive le retrait. Un seuil manuel produit une silhouette monochrome.</p>
          <p className="text-xs leading-relaxed text-muted">Un fond photographique ou un dessin qui touche les bords peut nécessiter une image déjà détourée. Vérifiez l’onglet Dessin après génération.</p>
        </SettingsSection>
        <SettingsSection id="advanced" title="Réglages avancés" summary={s.auto_adjust ? "Points ajustés par le moteur" : "Densité, compensation et sous-couche"} icon={SlidersHorizontal}>
          {s.auto_adjust && <p className="text-xs leading-relaxed text-muted">Pour modifier les points, désactivez l’ajustement automatique dans Stratégie de broderie.</p>}
          <div className="grid grid-cols-2 gap-4">
            <NumberSetting label="Pas satin (mm)" value={s.stitch_spacing} onChange={value => update("stitch_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={manualDisabled} />
            <NumberSetting label="Pas tatami (mm)" value={s.fill_spacing} onChange={value => update("fill_spacing", value ?? NaN)} min={0.2} max={1.2} step={0.001} disabled={manualDisabled} />
            <NumberSetting label="Compensation (mm)" value={s.pull_compensation} onChange={value => update("pull_compensation", value ?? NaN)} min={0} max={0.5} step={0.05} disabled={manualDisabled} />
            <NumberSetting label="Point maximal (mm)" value={s.max_stitch} onChange={value => update("max_stitch", value ?? NaN)} min={2} max={12} step={0.5} disabled={manualDisabled} />
          </div>
          <ToggleSetting label="Sous-couche" value={s.underlay} onChange={value => update("underlay", value)} disabled={manualDisabled} />
          <NumberSetting label="Largeur satin maximale (mm)" value={s.max_satin_width} onChange={value => update("max_satin_width", value ?? NaN)} min={2} max={12} step={0.5} disabled={manualDisabled} />
          <NumberSetting label="Point droit (mm)" value={s.running_length} onChange={value => update("running_length", value ?? NaN)} min={0.5} max={5} step={0.1} disabled={manualDisabled} />
          <ToggleSetting label="Angle tatami automatique" value={s.auto_fill_angle} onChange={value => update("auto_fill_angle", value)} disabled={busy} />
          {!s.auto_fill_angle && <NumberSetting label="Angle tatami (°)" value={s.fill_angle} onChange={value => update("fill_angle", value ?? NaN)} min={-180} max={180} step={5} disabled={busy} />}
        </SettingsSection>
      </Accordion>
    </div>
    <Button type="submit" fullWidth className="shrink-0" isDisabled={!canGenerate || busy}>{busy ? <Spinner size="sm" color="current" /> : <ArrowRight size={17} />}{busy ? "Génération en cours…" : "Générer ma broderie"}</Button>
    </Form>
  </div>;
}
