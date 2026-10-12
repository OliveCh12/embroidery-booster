"use client";

import { Accordion, Alert, Card, Chip, Spinner, Tabs, buttonVariants } from "@heroui/react";
import { Download, FileImage, ScanLine } from "lucide-react";
import type { ReactNode } from "react";
import { formatNumber } from "@/lib/format";
import type { GenerationResult } from "./types";

export function PreviewFrame({ src, alt, expand = false }: { src: string; alt: string; expand?: boolean }) {
  return <div className={`relative flex w-full items-center justify-center overflow-hidden rounded-xl border border-border bg-white ${expand ? "min-h-64 flex-1 md:min-h-40" : "aspect-[4/3] max-h-[520px]"}`}>
    <img src={src} alt={alt} className="absolute inset-0 size-full object-contain p-4" />
  </div>;
}

export function DownloadLink({ href, children, primary = false }: { href: string; children: ReactNode; primary?: boolean }) {
  return <a href={href} download className={buttonVariants({ variant: primary ? "primary" : "secondary", size: "sm" })}>
    <Download size={14} />{children}
  </a>;
}

function Metrics({ values }: { values: { label: string; value: string | number }[] }) {
  return <dl className="grid grid-cols-2 gap-4 @2xl:grid-cols-4">
    {values.map(item => <div key={item.label} className="min-w-0"><dt className="text-xs text-muted">{item.label}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{item.value}</dd></div>)}
  </dl>;
}

function StitchResult({ result, engine, compare = false }: { result: GenerationResult; engine: "direct" | "inkstitch"; compare?: boolean }) {
  const direct = engine === "direct" ? result.direct : null;
  const files = direct?.files ?? result.files;
  const native = result.native_stats;
  return <section className="@container flex min-h-full min-w-0 flex-1 flex-col gap-4" aria-label={direct ? "Points directs" : "Résultat Ink/Stitch"}>
    {compare && <div className="flex shrink-0 items-center justify-between gap-4"><h3 className="text-sm font-medium">{direct ? "Points directs" : "Ink/Stitch"}</h3>
      <Chip size="sm" variant="soft">{direct ? "PES / DST" : result.satin_preview ? "Points natifs" : "Rails éditables"}</Chip>
    </div>}
    <PreviewFrame expand src={direct?.preview ?? result.satin_preview ?? result.preview} alt={direct ? "Points machine directs" : result.satin_preview ? "Points calculés par Ink/Stitch" : "Rails satin pour Ink/Stitch"} />
    {direct?.threads?.length ? <div className="flex shrink-0 flex-wrap items-center gap-4" aria-label="Ordre des fils">
      {direct.threads.map((color, index) => <span key={color} className="flex items-center gap-2 text-xs text-muted"><span className="size-3 rounded-full border border-default" style={{ backgroundColor: color }} />{index + 1} · {color}</span>)}
    </div> : null}
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap gap-4">
        {Object.entries(files).filter(([, href]) => /(?:\.(?:pes|dst|zip)|_satin\.svg)$/.test(href)).map(([label, href]) => (
          <DownloadLink key={href} href={href} primary={/\.(pes|zip)$/.test(href)}>
            {href.endsWith(".pes") ? "PES · Brother" : href.endsWith(".dst") ? "DST" : href.endsWith(".zip") ? "PES + DST" : label}
          </DownloadLink>
        ))}
      </div>
      <p className="text-xs text-muted tabular-nums">{direct
        ? `${formatNumber(direct.stats.stitches)} points · couverture structurelle ${formatNumber(direct.stats.structural_coverage * 100)} % (±0,25 mm)`
        : native ? `${formatNumber(native.stitches)} points` : `${result.stats.columns} colonnes`}</p>
    </div>
  </section>;
}

function StitchDetails({ result, engine }: { result: GenerationResult; engine: "direct" | "inkstitch" }) {
  const direct = engine === "direct" ? result.direct : null;
  const native = result.native_stats;
  return <div className="@container flex flex-col gap-4">
    <Metrics values={direct ? [
      { label: "Points", value: formatNumber(direct.stats.stitches) }, { label: "Coupes", value: direct.stats.trims },
      { label: "Point maximal", value: `${formatNumber(direct.stats.max_stitch_mm)} mm` }, { label: "Calcul + exports", value: `${formatNumber(direct.stats.seconds)} s` },
      { label: "Couverture structurelle", value: `${formatNumber(direct.stats.structural_coverage * 100)} %` }, { label: "Plus grand manque", value: `${formatNumber(direct.stats.largest_gap_mm2)} mm²` },
    ] : native ? [
      { label: "Points", value: formatNumber(native.stitches) }, { label: "Coupes", value: native.trims },
      { label: "Point maximal", value: `${formatNumber(native.max_stitch_mm)} mm` }, { label: "Colonnes", value: result.stats.columns },
    ] : [
      { label: "Colonnes", value: result.stats.columns }, { label: "Point droit", value: result.stats.running },
      { label: "Surface des rails", value: `${result.stats.coverage} %` }, { label: "Préparation", value: `${formatNumber(result.stats.seconds)} s` },
    ]} />
    <p className="text-xs leading-relaxed text-muted">{direct
      ? `${formatNumber(direct.stats.width_mm)} × ${formatNumber(direct.stats.height_mm)} mm · couleurs des fils · sous-couche grise · sauts en pointillés. Couverture géométrique mesurée sur ${direct.coverage_basis === "quantized_top_layer" ? "la couche supérieure" : "tous les points cousus"}, avec une tolérance de 0,25 mm autour du fil.`
      : result.satin_preview ? "Aperçu des points réellement calculés par le moteur Ink/Stitch." : "La géométrie est prête à éditer ; les points seront calculés dans Ink/Stitch."}</p>
  </div>;
}

function Diagnostics({ result }: { result: GenerationResult }) {
  return <Accordion>
    {(["direct", "inkstitch"] as const).filter(engine => engine === "direct" ? result.direct : result.method !== "direct").map(engine => <Accordion.Item key={engine}>
      <Accordion.Heading><Accordion.Trigger>Mesures · {engine === "direct" ? "points directs" : "Ink/Stitch"}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="pb-4"><StitchDetails result={result} engine={engine} /></Accordion.Body></Accordion.Panel>
    </Accordion.Item>)}
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Fichiers de travail<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-wrap gap-4 pb-4">
        <DownloadLink href={result.artwork_svg}>Dessin interprété · SVG</DownloadLink>
        {Object.entries({ ...result.files, ...result.direct?.files }).map(([name, href]) => <DownloadLink key={href} href={href}>{name}</DownloadLink>)}
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
    {result.direct && <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Choix des points par région<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="pb-4">
        <div className="mb-4 flex flex-wrap gap-4">
          <Chip size="sm">{result.direct.stats.satin_regions} satin</Chip><Chip size="sm">{result.direct.stats.fill_regions} fill</Chip><Chip size="sm">{result.direct.stats.running_regions} point droit</Chip>
        </div>
        <ul className="max-h-60 space-y-2 overflow-auto text-sm text-muted">
          {result.direct.decisions.map(item => <li key={item.component}>Région {item.component} · {item.method === "running" ? "point droit" : item.method} · {formatNumber(item.width_mm)} mm{item.method === "fill" && item.fill_angle_deg !== null ? ` · ${item.fill_angle_deg}°` : ""}</li>)}
        </ul>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>}
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger>Diagnostics du traitement<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background p-3 text-xs text-muted">{result.logs || "Aucun message de diagnostic."}</pre>
        <div className="grid gap-4 sm:grid-cols-2">{Object.entries(result.debug_images).map(([name, src]) => <figure key={name}><img src={src} alt={name} className="w-full rounded-lg" /><figcaption className="mt-1 text-xs text-muted">{name}</figcaption></figure>)}</div>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
  </Accordion>;
}

export function ResultPane({ file, sourcePreview, result, busy }: {
  file: File | null; sourcePreview: string | null; result?: GenerationResult; busy: boolean;
}) {
  const defaultTab = result?.method === "both" ? "compare" : result?.direct ? "direct" : result ? "inkstitch" : "source";
  return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4" aria-busy={busy}>
    <Card className="min-h-[480px] flex-1 gap-4 md:min-h-0">
      <Card.Header className="shrink-0 flex-row items-center justify-between gap-4">
        <Card.Title className="min-w-0 truncate">{file?.name ?? "Aperçu"}</Card.Title>
        {result && <Chip size="sm" variant="soft" className="shrink-0">{result.artwork_size_mm.map(formatNumber).join(" × ")} mm</Chip>}
      </Card.Header>
      <Card.Content className="flex min-h-0 flex-1 flex-col gap-4">
        {busy ? <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 text-center text-muted" role="status"><Spinner size="lg" /><p>Génération de la broderie…</p><p className="text-xs">Analyse du dessin, placement des points et exports.</p></div> : <Tabs key={result?.job ?? file?.name ?? "empty"} defaultSelectedKey={defaultTab} className="min-h-0 w-full flex-1 gap-4" variant="secondary">
          <Tabs.ListContainer className="shrink-0"><Tabs.List aria-label="Aperçus de la broderie">
            <Tabs.Tab id="source">Dessin<Tabs.Indicator /></Tabs.Tab>
            {result?.direct && <Tabs.Tab id="direct">Points directs<Tabs.Indicator /></Tabs.Tab>}
            {result && result.method !== "direct" && <Tabs.Tab id="inkstitch">Ink/Stitch<Tabs.Indicator /></Tabs.Tab>}
            {result?.method === "both" && <Tabs.Tab id="compare">Comparer<Tabs.Indicator /></Tabs.Tab>}
          </Tabs.List></Tabs.ListContainer>
          <Tabs.Panel id="source" className="mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0">
            {result || sourcePreview ? <div className="flex min-h-full flex-col gap-4">
              <PreviewFrame expand src={result?.artwork_preview ?? sourcePreview!} alt="Dessin utilisé pour la broderie" />
              <p className="text-xs text-muted">{result ? "Silhouette interprétée à sa taille réelle. Les proportions sont conservées." : "Dessin source. La silhouette interprétée sera disponible après génération."}</p>
              {result && <DownloadLink href={result.artwork_svg}>Dessin interprété · SVG</DownloadLink>}
            </div> : <div className="flex min-h-full flex-col items-center justify-center gap-4 text-center text-muted">
              {file ? <FileImage size={32} /> : <ScanLine size={32} />}
              <p className="text-sm">{file ? "Le dessin sera visible après conversion." : "Importez un dessin pour commencer."}</p>
              {!file && <p className="max-w-xs text-xs leading-relaxed">L’atelier choisit satin, fill ou point droit pour chaque région de votre motif.</p>}
            </div>}
          </Tabs.Panel>
          {result?.direct && <Tabs.Panel id="direct" className="mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0"><StitchResult result={result} engine="direct" /></Tabs.Panel>}
          {result && result.method !== "direct" && <Tabs.Panel id="inkstitch" className="mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0"><StitchResult result={result} engine="inkstitch" /></Tabs.Panel>}
          {result?.method === "both" && <Tabs.Panel id="compare" className="@container mt-0 min-h-0 flex-1 overflow-y-auto overscroll-contain p-0"><div className="grid min-h-full gap-4 @3xl:grid-cols-2"><StitchResult result={result} engine="direct" compare /><StitchResult result={result} engine="inkstitch" compare /></div></Tabs.Panel>}
        </Tabs>}
      </Card.Content>
    </Card>
    {!busy && result && <Card className="shrink-0 gap-4 md:max-h-[40%] md:overflow-y-auto md:overscroll-contain"><Card.Content className="gap-4">
      <Accordion>
        <Accordion.Item>
          <Accordion.Heading><Accordion.Trigger><span className="flex flex-wrap items-center gap-4">Détails et fichiers{result.warnings.length > 0 && <Chip size="sm" color="warning" variant="soft">{result.warnings.length} à contrôler</Chip>}</span><Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
          <Accordion.Panel><Accordion.Body className="flex flex-col gap-4 pb-4">
            {result.warnings.length > 0 && <Alert status="warning"><Alert.Indicator /><Alert.Content><Alert.Title>À contrôler avant de broder</Alert.Title><Alert.Description><ul className="space-y-1">{result.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></Alert.Description></Alert.Content></Alert>}
            <Diagnostics result={result} />
          </Accordion.Body></Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Card.Content></Card>}
  </div>;
}
