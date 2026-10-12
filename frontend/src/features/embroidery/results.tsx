"use client";

import { Accordion, Alert, Chip, Spinner, Tabs, buttonVariants } from "@heroui/react";
import { Download, FileImage } from "lucide-react";
import type { ReactNode } from "react";
import { formatNumber } from "@/lib/format";
import { FileUpload } from "./file-upload";
import { StitchPlayer } from "./stitch-player/stitch-player";
import type { GenerationResult } from "./types";

export function PreviewFrame({ src, alt, expand = false }: { src: string; alt: string; expand?: boolean }) {
  return <div className={`relative overflow-hidden rounded-xl border border-border bg-white ${expand ? "min-h-64 flex-1 md:min-h-40" : "aspect-[4/3] max-h-[520px]"}`}><img src={src} alt={alt} className="absolute inset-0 size-full object-contain p-4" /></div>;
}
export function DownloadLink({ href, children, primary = false }: { href: string; children: ReactNode; primary?: boolean }) {
  return <a href={href} download className={buttonVariants({ variant: primary ? "primary" : "secondary", size: "sm" })}><Download size={15} />{children}</a>;
}

const parameterLabels: Record<string, string> = { satin_spacing_mm: "Pas satin", fill_spacing_mm: "Pas fill", pull_compensation_mm: "Compensation", underlay: "Sous-couche", max_satin_width_mm: "Largeur satin maximale", max_stitch_mm: "Longueur maximale", running_length_mm: "Point droit", fill_angle_deg: "Angle fill" };
function settingValue(value: number | boolean) { return typeof value === "boolean" ? value ? "activée" : "désactivée" : formatNumber(value); }

function Diagnostics({ result }: { result: GenerationResult }) {
  const { direct } = result, stats = direct.stats;
  return <Accordion>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Qualité et réglages appliqués<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <dl className="grid grid-cols-2 gap-4 text-xs text-muted sm:grid-cols-4">
          {[{ label: "Couverture structurelle", value: `${formatNumber(stats.structural_coverage * 100)} %` }, { label: "Plus grand manque", value: `${formatNumber(stats.largest_gap_mm2)} mm²` }, { label: "Point maximal", value: `${formatNumber(stats.max_stitch_mm)} mm` }, { label: "Temps de génération", value: `${formatNumber(result.stats.total_seconds)} s` }].map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-4 text-sm font-medium text-foreground tabular-nums">{item.value}</dd></div>)}
        </dl>
        <p className="text-xs leading-relaxed text-muted">Mesure sur la couche supérieure des points exportés, avec une tolérance de 0,25 mm autour du fil. Elle décrit la géométrie ; le tissu, le fil et le stabilisateur influencent le résultat cousu.</p>
        <dl className="grid grid-cols-2 gap-4 text-xs text-muted sm:grid-cols-4">
          {[{ label: "Pas satin", value: `${formatNumber(direct.params.satin_spacing_mm)} mm` }, { label: "Pas fill", value: `${formatNumber(direct.params.fill_spacing_mm)} mm` }, { label: "Compensation", value: `${formatNumber(direct.params.pull_compensation_mm)} mm` }, { label: "Sous-couche", value: direct.params.underlay ? "Activée" : "Désactivée" }].map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-4 text-sm font-medium text-foreground">{item.value}</dd></div>)}
        </dl>
        {direct.adjustments.length > 0 && <ul className="flex flex-col gap-4 text-xs text-muted">{direct.adjustments.map(item => <li key={item.parameter}><span className="font-medium text-foreground">{parameterLabels[item.parameter] ?? item.parameter} : {settingValue(item.requested)} → {settingValue(item.effective)}</span><p className="mt-4">{item.reason}</p></li>)}</ul>}
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Types de points par région<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <div className="flex flex-wrap gap-4"><Chip size="sm">{stats.satin_regions} satin</Chip><Chip size="sm">{stats.fill_regions} tatami</Chip><Chip size="sm">{stats.running_regions} point droit</Chip></div>
        <ul className="flex max-h-60 flex-col gap-4 overflow-auto text-xs text-muted">{direct.decisions.map(item => <li key={item.component} title={item.reason}><span className="font-medium text-foreground">Région {item.component}</span> · {item.method === "running" ? "point droit" : item.method === "omitted" ? "détail trop petit" : item.method === "fill" ? "tatami" : "satin"} · {formatNumber(item.width_mm)} mm{item.method === "fill" && item.fill_angle_deg !== null ? ` · ${formatNumber(item.fill_angle_deg)}°` : ""}</li>)}</ul>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Fichiers de travail et diagnostics<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <div className="flex flex-wrap gap-4"><DownloadLink href={result.artwork_svg}>Dessin · SVG</DownloadLink><DownloadLink href={direct.files.preview_svg}>Points · SVG</DownloadLink><DownloadLink href={direct.files.plan_json}>Plan machine · JSON</DownloadLink></div>
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background p-4 text-xs text-muted">{result.logs || "Aucun message de diagnostic."}</pre>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
  </Accordion>;
}

function SourcePreview({ sourcePreview, result }: { sourcePreview: string | null; result?: GenerationResult }) {
  return result || sourcePreview ? <div className="flex min-h-full flex-1 flex-col gap-4"><PreviewFrame expand src={result?.artwork_preview ?? sourcePreview!} alt="Dessin utilisé pour la broderie" /><p className="shrink-0 text-xs text-muted">{result ? "Dessin interprété à sa taille réelle, dans ses couleurs de fil." : "Ajustez le cadre, le tissu et le fil, puis générez la broderie."}</p></div>
    : <div className="flex min-h-64 flex-1 flex-col items-center justify-center gap-4 text-center text-muted"><FileImage size={32} aria-hidden="true" /><p className="text-sm">Le dessin sera visible après génération.</p></div>;
}

export function ResultPane({ file, sourcePreview, result, busy, importError, onSelect, onClear, hoop }: {
  file: File | null; sourcePreview: string | null; result?: GenerationResult; busy: boolean;
  importError: string | null; onSelect: (file: File) => void; onClear: () => void; hoop: [number, number];
}) {
  const hoopChanged = result && (hoop[0] !== result.direct.params.hoop_width_mm || hoop[1] !== result.direct.params.hoop_height_mm);
  return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4" aria-busy={busy}>
    <FileUpload file={file} onSelect={onSelect} onClear={onClear} disabled={busy} error={importError} showHint={!result}
      headerContent={<Chip size="sm" variant="soft" className="hidden shrink-0 @xl:flex">Cadre {hoop.map(value => Number.isFinite(value) ? formatNumber(value) : "—").join(" × ")} mm</Chip>}>
      {busy ? <div className="flex min-h-64 flex-1 flex-col items-center justify-center gap-4 text-center text-muted md:min-h-0" role="status"><Spinner size="lg" /><p>Génération de la broderie…</p><p className="text-xs">Analyse du dessin, placement des points et exports.</p></div>
        : !result ? <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain"><SourcePreview sourcePreview={sourcePreview} /></div>
        : <div className="flex min-h-0 flex-1 flex-col gap-4">
          {hoopChanged && <p className="shrink-0 text-xs text-warning">Le cadre a changé. Régénérez pour appliquer ses dimensions ; l’aperçu montre le fichier actuel.</p>}
          <Tabs key={result.job} defaultSelectedKey="stitches" className="min-h-0 w-full flex-1 gap-4" variant="secondary">
            <Tabs.ListContainer className="shrink-0"><Tabs.List aria-label="Aperçus de la broderie"><Tabs.Tab id="stitches">Simulation<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="source">Dessin<Tabs.Indicator /></Tabs.Tab></Tabs.List></Tabs.ListContainer>
            <Tabs.Panel id="stitches" className="mt-0 flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain p-0"><StitchPlayer url={result.direct.files.plan_json} /></Tabs.Panel>
            <Tabs.Panel id="source" className="mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0"><SourcePreview sourcePreview={sourcePreview} result={result} /></Tabs.Panel>
          </Tabs>
          <div className="flex shrink-0 flex-wrap items-center gap-4"><DownloadLink href={result.direct.files.pes} primary>PES · Brother</DownloadLink><DownloadLink href={result.direct.files.dst}>DST</DownloadLink><span className="ml-auto text-xs text-muted">{formatNumber(result.direct.stats.stitches)} points · {result.direct.threads.length} fils</span></div>
        </div>}
    </FileUpload>
    {!busy && result && <Accordion className="shrink-0 rounded-xl border border-border bg-surface md:max-h-[35%] md:overflow-y-auto md:overscroll-contain"><Accordion.Item>
      <Accordion.Heading><Accordion.Trigger className="min-h-10 py-2"><span className="flex flex-wrap items-center gap-4">Détails et qualité<Chip size="sm" color={result.direct.analysis.quality_status === "needs_review" ? "warning" : "success"} variant="soft">{result.direct.analysis.quality_status === "needs_review" ? "À contrôler" : "Contrôles géométriques validés"}</Chip>{result.warnings.length > 0 && <Chip size="sm" color="warning" variant="soft">{result.warnings.length} remarque{result.warnings.length > 1 ? "s" : ""}</Chip>}</span><Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        {result.warnings.length > 0 && <Alert status="warning"><Alert.Indicator /><Alert.Content><Alert.Title>À contrôler avant de broder</Alert.Title><Alert.Description><ul className="flex flex-col gap-4">{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></Alert.Description></Alert.Content></Alert>}
        <Diagnostics result={result} />
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item></Accordion>}
  </div>;
}
