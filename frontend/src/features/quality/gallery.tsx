"use client";

import { Alert, Card, Chip, Spinner, Tabs } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChoiceSetting } from "@/features/embroidery/controls";
import { DownloadLink, PreviewFrame } from "@/features/embroidery/results";
import { useCapabilities } from "@/features/embroidery/use-capabilities";
import { apiRequest } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { QualityReport } from "./types";

export function QualityGallery() {
  const capabilities = useCapabilities();
  const report = useQuery({ queryKey: ["quality"], queryFn: async ({ signal }) => {
    const data = await apiRequest<QualityReport>("/quality-assets/comparison.json", { signal });
    if (data.schema_version !== 3 || data.engine !== "direct" || !Array.isArray(data.results)) throw new Error("Le rapport qualité doit être recalculé avec le moteur actuel.");
    return data;
  }, enabled: !!capabilities.data?.quality_report });
  const [selected, setSelected] = useState("");
  const [view, setView] = useState("preview");
  const current = report.data?.results.find(row => row.file === selected) ?? report.data?.results[0];

  if (capabilities.isError || report.isError) return <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Contrôle qualité indisponible</Alert.Title><Alert.Description>{capabilities.error?.message ?? report.error?.message}</Alert.Description></Alert.Content></Alert>;
  if (capabilities.data && !capabilities.data.quality_report || report.data && !report.data.results.length) return <Alert><Alert.Indicator /><Alert.Content><Alert.Title>Aucun rapport disponible</Alert.Title><Alert.Description>Les modèles de référence apparaîtront ici une fois le corpus qualité calculé.</Alert.Description></Alert.Content></Alert>;
  if (!current) return <div className="flex min-h-96 items-center justify-center gap-4 text-muted" role="status"><Spinner />Chargement des essais…</div>;

  const metrics = current.metrics;
  return <div className="flex min-h-0 flex-1 flex-col gap-4 md:overflow-y-auto md:overscroll-contain">
    <Card className="shrink-0 gap-4"><Card.Content className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="w-full sm:max-w-sm"><ChoiceSetting label="Modèle de référence" value={current.file} onChange={setSelected} options={report.data!.results.map(row => ({ value: row.file, label: row.file.replace("quality/", "") }))} /></div>
      <div className="flex flex-wrap items-center gap-4"><Chip size="sm" variant="soft">{report.data!.results.length} dessins testés</Chip><DownloadLink href="/quality-assets/comparison.json">Mesures · JSON</DownloadLink></div>
    </Card.Content></Card>
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-4">
        <Card className="gap-4"><Card.Header><Card.Title>Dessin source</Card.Title></Card.Header><Card.Content className="gap-4"><PreviewFrame src={`/quality-assets/${current.source_preview}`} alt={current.file} /></Card.Content></Card>
        <Card className="gap-4"><Card.Content className="gap-4 text-xs leading-relaxed text-muted">
          <p>Largeur de référence : {report.data!.measurement.design_width_mm} mm. La grille d’audit mesure les points réellement exportés.</p>
          <p>Couverture structurelle : tolérance de {report.data!.measurement.structural_tolerance_mm} mm autour d’un fil de {report.data!.measurement.thread_mm} mm. L’IoU mesure la fidélité de l’empreinte brute.</p>
          <p>La couche supérieure est mesurée séparément des sous-couches et déplacements. Validez le résultat sur le tissu choisi.</p>
          {current.threads && <div className="flex flex-wrap gap-4" aria-label="Ordre des fils">{current.threads.map((color, index) => <Chip key={`${color}-${index}`} size="sm" variant="soft"><span className="size-3 rounded-full border border-black/20" style={{ backgroundColor: color }} />{index + 1}</Chip>)}</div>}
        </Card.Content></Card>
      </aside>
      <Card className="min-h-0 gap-4"><Card.Content className="flex min-h-0 flex-1 flex-col gap-4">
        <Tabs selectedKey={view} onSelectionChange={key => setView(String(key))} variant="secondary" className="min-h-0 flex-1 gap-4">
          <Tabs.ListContainer className="shrink-0"><Tabs.List aria-label="Contrôle du rendu"><Tabs.Tab id="preview">Points exportés<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="footprint">Empreinte du fil<Tabs.Indicator /></Tabs.Tab></Tabs.List></Tabs.ListContainer>
          {(["preview", "footprint"] as const).map(tab => <Tabs.Panel key={tab} id={tab} className="mt-0 flex min-h-0 flex-1 flex-col p-0">{current[tab] ? <PreviewFrame src={`/quality-assets/${current[tab]}`} alt={`${tab === "preview" ? "Points" : "Empreinte"} · ${current.file}`} expand /> : <p className="text-sm text-danger">{current.error ?? "Aucun plan disponible."}</p>}</Tabs.Panel>)}
        </Tabs>
        {metrics && <>
          <dl className="grid shrink-0 grid-cols-2 gap-4 text-xs text-muted sm:grid-cols-4">
            {[{ label: "Couverture structurelle", value: `${formatNumber(metrics.structural_coverage * 100)} %` }, { label: "Fidélité · IoU", value: `${formatNumber(metrics.iou * 100)} %` }, { label: "Points", value: formatNumber(metrics.stitches) }, { label: "Coupes", value: formatNumber(metrics.trims) }].map(item => <div key={item.label}><dt>{item.label}</dt><dd className="mt-4 text-base font-semibold text-foreground tabular-nums">{item.value}</dd></div>)}
          </dl>
          <p className="shrink-0 text-xs text-muted">Plus grand manque : {formatNumber(metrics.largest_gap_mm2)} mm² · distance maximale au fil : {formatNumber(metrics.uncovered_max_mm)} mm · {formatNumber(current.seconds ?? 0)} s de génération</p>
          {current.stats && <div className="flex shrink-0 flex-wrap gap-4"><Chip size="sm" variant="soft">{current.stats.satin_regions} satin</Chip><Chip size="sm" variant="soft">{current.stats.fill_regions} tatami</Chip><Chip size="sm" variant="soft">{current.stats.running_regions} point droit</Chip></div>}
        </>}
      </Card.Content></Card>
    </div>
  </div>;
}
