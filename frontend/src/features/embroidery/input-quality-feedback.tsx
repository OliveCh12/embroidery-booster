"use client";

import { Accordion, Spinner } from "@heroui/react";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { GenerationSettings } from "./types";
import { inputQualityDetails, inputQualityTitle, useInputQuality, type InputQuality } from "./input-quality";

export function InputQualitySummary({ quality }: { quality: InputQuality }) {
  const details = inputQualityDetails(quality);
  const Icon = quality.status === "good" ? CircleCheck : quality.status === "poor" ? TriangleAlert : Info;
  return <Accordion className="shrink-0" aria-label="Qualité de la source">
    <Accordion.Item>
      <Accordion.Heading><Accordion.Trigger className="gap-2 py-1 text-xs font-normal">
        <Icon size={14} className={quality.status === "good" ? "text-muted" : "text-warning"} aria-hidden="true" />
        <span className="min-w-0 flex-1 text-left">{inputQualityTitle(quality)}</span><Accordion.Indicator />
      </Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body className="flex flex-col gap-2 py-2 text-xs leading-relaxed text-muted">
        {details.map(detail => <p key={detail}>{detail}</p>)}
        <p>Cette analyse évalue la source, pas le résultat cousu.</p>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item>
  </Accordion>;
}

export function InputQualityFeedback({ file, settings, revision }: {
  file: File; settings: GenerationSettings; revision: number;
}) {
  const { query, valid, changing } = useInputQuality(file, settings, revision);
  if (!valid) return <p className="shrink-0 text-xs text-muted">Renseignez une taille et des paramètres d’image valides pour analyser la source.</p>;
  if (changing || query.isPending) return <p className="flex shrink-0 items-center gap-2 text-xs text-muted" role="status"><Spinner size="sm" />Analyse de la source…</p>;
  if (query.isError) return <p className="shrink-0 text-xs text-muted" title={query.error.message}>Analyse de la source indisponible ; vous pouvez générer la broderie.</p>;
  return query.data ? <InputQualitySummary quality={query.data} /> : null;
}
