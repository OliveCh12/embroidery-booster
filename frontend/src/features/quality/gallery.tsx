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

const methods = { "direct-auto": "Direct automatique", "inkstitch-safe": "Ink/Stitch", "direct-split": "Satin subdivisé", "direct-fill": "Fill manuel" };

export function QualityGallery() {
  const capabilities = useCapabilities();
  const report = useQuery({ queryKey: ["quality"], queryFn: ({ signal }) => apiRequest<QualityReport>("/quality-assets/comparison.json", { signal }), enabled: !!capabilities.data?.quality_report });
  const [selected, setSelected] = useState("");
  const [view, setView] = useState("preview");
  const current = report.data?.results.find(row => row.file === selected) ?? report.data?.results[0];

  if (capabilities.isError || report.isError) return <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Comparaison indisponible</Alert.Title><Alert.Description>{capabilities.error?.message ?? report.error?.message}</Alert.Description></Alert.Content></Alert>;
  if (capabilities.data && !capabilities.data.quality_report) return <Alert><Alert.Indicator /><Alert.Content><Alert.Title>Aucun rapport disponible</Alert.Title><Alert.Description>Les essais comparatifs apparaîtront ici une fois le corpus calculé.</Alert.Description></Alert.Content></Alert>;
  if (!current) return <div className="flex min-h-96 items-center justify-center gap-4 text-muted" role="status"><Spinner />Chargement des essais…</div>;

  return <div className="flex flex-col gap-4">
    <Card className="gap-4">
      <Card.Content className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="w-full sm:max-w-sm"><ChoiceSetting label="Dessin à comparer" value={current.file} onChange={setSelected} options={report.data!.results.map(row => ({ value: row.file, label: row.file.replace("quality/", "") }))} /></div>
        <div className="flex flex-wrap items-center gap-4"><Chip size="sm" variant="soft">{report.data!.results.length} dessins testés</Chip><DownloadLink href="/quality-assets/comparison.json">Mesures · JSON</DownloadLink></div>
      </Card.Content>
    </Card>
    <div className="grid items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-4">
        <Card className="gap-4"><Card.Header><Card.Title>Dessin source</Card.Title></Card.Header><Card.Content className="gap-4"><PreviewFrame src={`/quality-assets/${current.source_preview}`} alt={current.file} /></Card.Content></Card>
        <div className="flex flex-col gap-4 text-xs leading-relaxed text-muted">
          <p>Mêmes dimensions, densité, compensation et sous-couche pour chaque méthode.</p>
          <p>La couverture structurelle tolère {report.data!.measurement.structural_tolerance_mm} mm autour du fil. L’IoU mesure la fidélité de l’empreinte brute.</p>
          <p>Ces métriques ne simulent pas le comportement du tissu ni le rendu d’une broderie cousue.</p>
        </div>
      </aside>
      <Tabs selectedKey={view} onSelectionChange={key => setView(String(key))} variant="secondary" className="gap-4">
        <Tabs.ListContainer><Tabs.List aria-label="Mode de comparaison"><Tabs.Tab id="preview">Points exportés<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="footprint">Empreinte du fil<Tabs.Indicator /></Tabs.Tab></Tabs.List></Tabs.ListContainer>
        {["preview", "footprint"].map(tab => <Tabs.Panel key={tab} id={tab} className="mt-0 p-0"><div className="grid gap-4 xl:grid-cols-2">
          {Object.entries(methods).filter(([key]) => key in current.methods).map(([key, title]) => {
            const method = current.methods[key];
            const metrics = method.metrics;
            return <Card key={key} className="gap-4"><Card.Header><Card.Title>{title}</Card.Title></Card.Header><Card.Content className="gap-4">
              {metrics && method[tab as "preview" | "footprint"] ? <>
                <PreviewFrame src={`/quality-assets/${method[tab as "preview" | "footprint"]}`} alt={`${title} · ${current.file}`} />
                <dl className="grid grid-cols-3 gap-4 text-xs text-muted">
                  {[{ label: "Structure", value: `${formatNumber(metrics.structural_coverage * 100)} %` }, { label: "IoU", value: `${formatNumber(metrics.iou * 100)} %` }, { label: "Coupes", value: metrics.trims }].map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd className="mt-1 text-base font-semibold text-foreground tabular-nums">{metric.value}</dd></div>)}
                </dl>
                <p className="text-xs text-muted">Plus grand manque : {formatNumber(metrics.largest_gap_mm2)} mm² · distance maximale au fil : {formatNumber(metrics.uncovered_max_mm)} mm</p>
                <p className="text-xs text-muted">{formatNumber(metrics.stitches)} points · point maximal {formatNumber(metrics.max_stitch_mm)} mm · {formatNumber(method.seconds ?? 0)} s</p>
              </> : <p className="text-sm text-danger">{method.error ?? "Aucun plan disponible."}</p>}
            </Card.Content></Card>;
          })}
        </div></Tabs.Panel>)}
      </Tabs>
    </div>
  </div>;
}
