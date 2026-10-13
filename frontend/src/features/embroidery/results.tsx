"use client";

import { Accordion, Button, Chip, Drawer, Label, ListBox, Select, Spinner, Tabs, buttonVariants } from "@heroui/react";
import { Download, FileImage, PanelRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { formatNumber } from "@/lib/format";
import { describeBackground, describeBitmapCleanup } from "./background-diagnostics";
import { FileUpload } from "./file-upload";
import { InputQualitySummary } from "./input-quality-feedback";
import { BACKGROUND_MODE_LABELS, STITCH_TYPE_LABELS } from "./settings";
import { StitchPlayer } from "./stitch-player/stitch-player";
import type { GenerationResult, VariantId } from "./types";
import { VARIANT_LABELS, variantOptions, variantReason, variantResult } from "./variants";

export function PreviewFrame({ src, alt, expand = false }: { src: string; alt: string; expand?: boolean }) {
  return <div className={`relative overflow-hidden bg-white ${expand ? "min-h-64 flex-1 md:min-h-40" : "aspect-[4/3] max-h-[520px]"}`}><img src={src} alt={alt} className="absolute inset-0 size-full object-contain" /></div>;
}
export function DownloadLink({ href, children, primary = false }: { href: string; children: ReactNode; primary?: boolean }) {
  return <a href={href} download className={buttonVariants({ variant: primary ? "primary" : "secondary", size: "sm" })}><Download size={15} />{children}</a>;
}

const parameterLabels: Record<string, string> = { satin_spacing_mm: "Pas satin", fill_spacing_mm: "Pas tatami", pull_compensation_mm: "Compensation", underlay: "Sous-couche", max_satin_width_mm: "Largeur satin maximale", max_stitch_mm: "Longueur maximale", running_length_mm: "Point droit", fill_angle_deg: "Angle tatami", density_percent: "Densité de surface (%)" };
function settingValue(value: number | boolean) { return typeof value === "boolean" ? value ? "activée" : "désactivée" : formatNumber(value); }
function InputDiagnostics({ result }: { result: GenerationResult }) {
  const background = result.input_analysis?.background, cleanup = result.input_analysis?.cleanup;
  const description = background ? describeBackground(background) : null;
  return <div className="flex flex-col gap-4 text-xs text-muted">
    {result.input_analysis?.quality && <InputQualitySummary quality={result.input_analysis.quality} />}
    <dl className="grid grid-cols-2 gap-4">
      <div><dt>Type de points</dt><dd className="mt-1 font-medium text-foreground">{STITCH_TYPE_LABELS[result.direct.params.stitch_type ?? "auto"]}</dd></div>
      {background && <><div><dt>Fond demandé</dt><dd className="mt-1 font-medium text-foreground">{background.mode ? BACKGROUND_MODE_LABELS[background.mode] : "—"}</dd></div><div><dt>Fond interprété</dt><dd className="mt-1 font-medium text-foreground">{background.applied === true ? "Retiré" : background.applied === false ? "Conservé" : "—"}</dd></div></>}
      {cleanup && <div><dt>Réduction des parasites</dt><dd className="mt-1 font-medium text-foreground">{cleanup.reason === "vector_artwork_preserved" ? "SVG préservé" : cleanup.reason === "single_colour_silhouette" ? "Silhouette monochrome" : cleanup.enabled === true ? "Activée" : cleanup.enabled === false ? "Désactivée" : "—"}</dd></div>}
    </dl>
    {description && <p>{description.message}</p>}
    {!!description?.metrics.length && <dl className="grid grid-cols-2 gap-4">{description.metrics.map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-1 font-medium text-foreground tabular-nums">{item.value}</dd></div>)}</dl>}
    {(cleanup?.palette_consolidated_pixels ?? 0) > 0 && <p>Nuances liées à la compression consolidées : {cleanup?.palette_source_colors != null && cleanup.palette_colors != null ? `${formatNumber(cleanup.palette_source_colors)} nuances d’image → ${formatNumber(cleanup.palette_colors)} couleurs de fil. ` : ""}{cleanup?.regions_before != null && cleanup.regions_after_palette != null ? `${formatNumber(cleanup.regions_before)} → ${formatNumber(cleanup.regions_after_palette)} îlots de couleur. ` : ""}{cleanup?.palette_changed_area_mm2 != null ? `${formatNumber(cleanup.palette_changed_area_mm2)} mm² de nuances ajustées. ` : ""}{(cleanup?.retained_accent_colors ?? 0) > 0 ? `${formatNumber(cleanup!.retained_accent_colors!)} couleur${cleanup!.retained_accent_colors! > 1 ? "s" : ""} de détail préservée${cleanup!.retained_accent_colors! > 1 ? "s" : ""}. ` : ""}Les zones transparentes sont conservées.</p>}
    {(cleanup?.changed_pixels ?? 0) > 0 && <p>Nettoyage : {(cleanup?.regions_after_palette ?? cleanup?.regions_before) != null && cleanup?.regions_after != null ? `${formatNumber((cleanup.regions_after_palette ?? cleanup.regions_before)!)} → ${formatNumber(cleanup.regions_after)} îlots de couleur · ` : ""}{cleanup?.changed_area_mm2 != null ? `${formatNumber(cleanup.changed_area_mm2)} mm² modifiés.` : ""}{(cleanup?.removed_pixels ?? 0) > 0 ? " Des parasites isolés trop fins pour être cousus ont été retirés." : " Les transparences du dessin sont conservées."}</p>}
    {describeBitmapCleanup(cleanup).map(message => <p key={message}>{message}</p>)}
  </div>;
}

function Diagnostics({ result }: { result: GenerationResult }) {
  const { direct } = result, stats = direct.stats;
  return <Accordion>
    {!!result.variants?.length && <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Propositions automatiques<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4 text-xs text-muted">
        <p>Le même dessin, les mêmes fils et les mêmes réglages de tissu sont utilisés. La recommandation privilégie les contrôles de couverture et de sécurité ; elle ne prédit pas le rendu cousu.</p>
        {result.variants.map(item => <div key={item.id} className="flex flex-col gap-1">
          <p className="font-medium text-foreground">{VARIANT_LABELS[item.id]}{item.id === result.recommended_variant ? " · recommandé" : ""}{item.direct.analysis.quality_status === "needs_review" && <span className="font-normal text-warning"> · à vérifier</span>}</p>
          <p>{item.quality.purpose === "outline" ? "Contours uniquement" : `${formatNumber(item.direct.stats.structural_coverage * 100)} % de couverture`} · {formatNumber(item.direct.stats.stitches)} points · {item.direct.stats.satin_regions} satin · {item.direct.stats.fill_regions} tatami · {item.direct.stats.running_regions} point droit</p>
          {item.direct.stats.omitted_regions > 0 && <p className="text-warning">{formatNumber(item.direct.stats.omitted_regions)} détail{item.direct.stats.omitted_regions > 1 ? "s" : ""} non cousu{item.direct.stats.omitted_regions > 1 ? "s" : ""}.</p>}
          {item.reasons.filter(reason => !["shared_interpretation", "audit_first"].includes(reason) && !(reason === "balanced_default" && item.reasons.includes("no_meaningful_gain"))).map(reason => <p key={reason}>{variantReason(reason)}</p>)}
          {item.equivalent_strategies.length > 0 && <p>Résultat identique : {item.equivalent_strategies.map(id => VARIANT_LABELS[id]).join(", ")}.</p>}
        </div>)}
        {result.skipped_variants?.map(item => <p key={item.id}>{VARIANT_LABELS[item.id]} non retenu : {variantReason(item.reason)}</p>)}
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>}
    {result.warnings.length > 0 && <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>{result.warnings.length} remarque{result.warnings.length > 1 ? "s" : ""} avant de broder<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="pb-4"><ul className="flex flex-col gap-4 text-xs leading-relaxed text-muted">{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></Accordion.Body></Accordion.Panel>
    </Accordion.Item>}
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Qualité et réglages<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <dl className="grid grid-cols-2 gap-4 text-xs text-muted">
          {[{ label: "Couverture structurelle", value: `${formatNumber(stats.structural_coverage * 100)} %` }, { label: "Plus grand manque", value: `${formatNumber(stats.largest_gap_mm2)} mm²` }, { label: "Point maximal", value: `${formatNumber(stats.max_stitch_mm)} mm` }, { label: "Temps de génération", value: `${formatNumber(result.stats.total_seconds)} s` }].map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-1 text-sm font-medium text-foreground tabular-nums">{item.value}</dd></div>)}
        </dl>
        <p className="text-xs leading-relaxed text-muted">Mesure sur la couche supérieure des points exportés, avec une tolérance de 0,25 mm autour du fil. Elle décrit la géométrie ; le tissu, le fil et le stabilisateur influencent le résultat cousu.</p>
        <dl className="grid grid-cols-2 gap-4 text-xs text-muted">
          {[{ label: "Pas satin", value: `${formatNumber(direct.params.satin_spacing_mm)} mm` }, { label: "Pas tatami", value: `${formatNumber(direct.params.fill_spacing_mm)} mm` }, { label: "Compensation", value: `${formatNumber(direct.params.pull_compensation_mm)} mm` }, { label: "Sous-couche", value: direct.params.underlay ? "Activée" : "Désactivée" }, ...(direct.params.auto_adjust && direct.params.density_percent != null ? [{ label: "Densité de surface", value: `${formatNumber(direct.params.density_percent)} %` }] : [])].map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-1 text-sm font-medium text-foreground">{item.value}</dd></div>)}
        </dl>
        {direct.adjustments.length > 0 && <ul className="flex flex-col gap-4 text-xs text-muted">{direct.adjustments.map(item => <li key={item.parameter}><span className="font-medium text-foreground">{parameterLabels[item.parameter] ?? item.parameter} : {settingValue(item.requested)} → {settingValue(item.effective)}</span><p className="mt-1">{item.reason}</p></li>)}</ul>}
        {direct.analysis.stitch_breakdown && <dl className="grid grid-cols-2 gap-4 text-xs text-muted">{([{ key: "top", label: "Couverture" }, { key: "underlay", label: "Sous-couche" }, { key: "travel", label: "Liaisons cousues" }, { key: "lock", label: "Ancrages" }, { key: "entry", label: "Prises de fil" }] as const).map(item => <div key={item.key}><dt>{item.label}</dt><dd className="mt-1 font-medium text-foreground tabular-nums">{formatNumber(direct.analysis.stitch_breakdown![item.key])}</dd></div>)}</dl>}
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Interprétation du dessin<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="pb-4"><InputDiagnostics result={result} /></Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Points par région<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <div className="flex flex-wrap gap-4"><Chip size="sm">{stats.satin_regions} satin</Chip><Chip size="sm">{stats.fill_regions} tatami</Chip><Chip size="sm">{stats.running_regions} point droit</Chip></div>
        <ul className="flex max-h-60 flex-col gap-4 overflow-auto text-xs text-muted">{direct.decisions.map(item => <li key={item.component} title={item.reason}><span className="font-medium text-foreground">Région {item.component}</span> · {item.method === "running" ? "point droit" : item.method === "omitted" ? item.reason === "machine_geometry_rejected" ? "géométrie à contrôler" : "détail trop petit" : item.method === "fill" ? "tatami" : (item.split_satin_columns ?? 0) > 1 ? "satin divisé" : "satin"} · {formatNumber(item.width_mm)} mm{(item.split_satin_columns ?? 0) > 1 ? ` · ${item.split_satin_columns} colonnes` : ""}{item.method === "fill" && item.fill_angle_deg !== null ? ` · ${formatNumber(item.fill_angle_deg)}°` : ""}</li>)}</ul>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Fichiers et journal<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <div className="flex flex-wrap gap-4"><DownloadLink href={result.artwork_svg}>Dessin · SVG</DownloadLink><DownloadLink href={direct.files.preview_svg}>Points · SVG</DownloadLink><DownloadLink href={direct.files.plan_json}>Plan machine · JSON</DownloadLink></div>
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background p-4 text-xs text-muted">{result.logs || "Aucun message de diagnostic."}</pre>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
  </Accordion>;
}

function ActivityPanel({ result }: { result: GenerationResult }) {
  const needsReview = result.direct.analysis.quality_status === "needs_review" || result.warnings.length > 0;
  return <div className="flex" onClick={event => event.stopPropagation()} onPaste={event => event.stopPropagation()}
    onDrop={event => { event.preventDefault(); event.stopPropagation(); }} onDragEnter={event => event.stopPropagation()}
    onDragOver={event => { event.preventDefault(); event.stopPropagation(); }} onDragLeave={event => event.stopPropagation()}>
    <Drawer>
      <Button variant="ghost" size="sm" aria-label="Détails" className="w-9 gap-1 px-0 @sm:w-auto @sm:gap-2 @sm:px-3" aria-description={needsReview ? "Des remarques sont à consulter avant de broder." : undefined}>
        <PanelRight size={15} aria-hidden="true" /><span className="hidden @sm:inline">Détails</span>{needsReview && <span className="size-1.5 rounded-full bg-warning" aria-hidden="true" />}
      </Button>
      <Drawer.Backdrop variant="opaque">
        <Drawer.Content placement="right">
          <Drawer.Dialog className="w-[360px] max-w-full gap-4 p-4">
            <Drawer.CloseTrigger aria-label="Fermer les détails" />
            <Drawer.Header className="shrink-0 pr-8"><Drawer.Heading>Détails de la broderie</Drawer.Heading></Drawer.Header>
            <Drawer.Body className="flex flex-col gap-4">
              <p className={`text-xs ${result.direct.analysis.quality_status === "needs_review" ? "text-warning" : "text-muted"}`}>{result.direct.analysis.quality_status === "needs_review" ? "Contrôles géométriques à vérifier" : "Contrôles géométriques validés"}</p>
              <Diagnostics result={result} />
            </Drawer.Body>
          </Drawer.Dialog>
        </Drawer.Content>
      </Drawer.Backdrop>
    </Drawer>
  </div>;
}

function SourcePreview({ sourcePreview, result }: { sourcePreview: string | null; result?: GenerationResult }) {
  return result || sourcePreview ? <div className="flex min-h-full flex-1 flex-col gap-4"><PreviewFrame expand src={result?.artwork_preview ?? sourcePreview!} alt="Dessin utilisé pour la broderie" /><p className="shrink-0 text-xs text-muted">{result ? "Dessin interprété à sa taille réelle, dans ses couleurs de fil." : "Ajustez le cadre, le tissu et le fil, puis générez la broderie."}</p></div>
    : <div className="flex min-h-64 flex-1 flex-col items-center justify-center gap-4 text-center text-muted"><FileImage size={32} aria-hidden="true" /><p className="text-sm">Le dessin sera visible après génération.</p></div>;
}

export function ResultPane({ file, sourcePreview, result, busy, importError, onSelect, onClear, hoop, inputFeedback }: {
  file: File | null; sourcePreview: string | null; result?: GenerationResult; busy: boolean;
  importError: string | null; onSelect: (file: File) => void; onClear: () => void; hoop: [number, number]; inputFeedback?: ReactNode;
}) {
  const [selection, setSelection] = useState<{ job: string; id: VariantId } | null>(null);
  const selectedId = result && selection?.job === result.job ? selection.id : result?.recommended_variant ?? null;
  const selected = result ? variantResult(result, selectedId) : undefined;
  const options = selected ? variantOptions(selected) : [];
  const hoopChanged = selected && (hoop[0] !== selected.direct.params.hoop_width_mm || hoop[1] !== selected.direct.params.hoop_height_mm);
  return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4" aria-busy={busy}>
    <FileUpload file={file} onSelect={onSelect} onClear={onClear} disabled={busy} error={importError} showHint={!result} feedback={inputFeedback}
      headerContent={<div className="flex shrink-0 items-center gap-4"><Chip size="sm" variant="soft" className="hidden shrink-0 @xl:flex">Cadre {hoop.map(value => Number.isFinite(value) ? formatNumber(value) : "—").join(" × ")} mm</Chip>{!busy && selected && <ActivityPanel key={selected.direct.files.plan_json} result={selected} />}</div>}>
      {busy ? <div className="flex min-h-64 flex-1 flex-col items-center justify-center gap-4 text-center text-muted md:min-h-0" role="status"><Spinner size="lg" /><p>Génération de la broderie…</p><p className="text-xs">Analyse du dessin, placement des points et exports.</p></div>
        : !selected ? <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain"><SourcePreview sourcePreview={sourcePreview} /></div>
        : <div className="flex min-h-0 flex-1 flex-col gap-4">
          {hoopChanged && <p className="shrink-0 text-xs text-warning">Le cadre a changé. Régénérez pour appliquer ses dimensions ; l’aperçu montre le fichier actuel.</p>}
          <Tabs key={selected.job} defaultSelectedKey="stitches" className="min-h-0 w-full flex-1 gap-4" variant="secondary">
            <div className="flex shrink-0 flex-wrap items-center gap-4">
              <Tabs.ListContainer className="shrink-0"><Tabs.List aria-label="Aperçus de la broderie"><Tabs.Tab id="stitches">Simulation<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="source">Dessin<Tabs.Indicator /></Tabs.Tab></Tabs.List></Tabs.ListContainer>
              {options.length > 1 && <Select aria-label="Variante de broderie" value={selectedId} variant="secondary" className="ml-auto w-60 max-w-full" onChange={id => { if (typeof id === "string") setSelection({ job: selected.job, id: id as VariantId }); }}>
                <Select.Trigger className="min-h-8 py-1"><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox aria-label="Variante de broderie">{options.map(item => <ListBox.Item key={item.id} id={item.id} textValue={item.label}><Label>{item.label}</Label><ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
              </Select>}
            </div>
            <Tabs.Panel id="stitches" className="mt-0 flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain p-0"><StitchPlayer url={selected.direct.files.plan_json} /></Tabs.Panel>
            <Tabs.Panel id="source" className="mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0"><SourcePreview sourcePreview={sourcePreview} result={selected} /></Tabs.Panel>
          </Tabs>
          <div className="flex shrink-0 flex-wrap items-center gap-4 border-t border-border pt-4"><DownloadLink href={selected.direct.files.pes} primary>PES · Brother</DownloadLink><DownloadLink href={selected.direct.files.dst}>DST</DownloadLink><span className="ml-auto text-xs text-muted">{formatNumber(selected.direct.stats.stitches)} points · {selected.direct.threads.length} fil{selected.direct.threads.length > 1 ? "s" : ""}</span></div>
        </div>}
    </FileUpload>
  </div>;
}
