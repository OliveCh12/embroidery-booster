"use client";

import { Button, Popover } from "@heroui/react";
import { Check, ChevronDown, Circle, CircleDot, ListOrdered } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { formatNumber } from "@/lib/format";
import { threadStepStatus, type StitchPlan, type ThreadSequenceStep } from "./model";

export function sewingTime(minutes: number) {
  const seconds = Math.max(0, Math.round(minutes * 60));
  const hours = Math.floor(seconds / 3600);
  const remainder = Math.floor(seconds / 60) % 60;
  return `${hours ? `${hours}:` : ""}${String(hours ? remainder : Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function ThreadList({ plan, steps, cursor, onSeek }: {
  plan: StitchPlan; steps: ThreadSequenceStep[]; cursor: number; onSeek: (cursor: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const list = useRef<HTMLOListElement>(null);
  const activeIndex = steps.findIndex(step => threadStepStatus(step, cursor) === "active");
  useEffect(() => {
    const container = list.current, row = container?.children[activeIndex];
    if (!open || !container || !row) return;
    const visible = container.getBoundingClientRect(), item = row.getBoundingClientRect();
    if (item.top < visible.top) container.scrollTop -= visible.top - item.top;
    else if (item.bottom > visible.bottom) container.scrollTop += item.bottom - visible.bottom;
  }, [activeIndex, open]);
  return <Popover isOpen={open} onOpenChange={setOpen}>
    <Button size="sm" variant="ghost" aria-label="Ordre des fils" className="min-w-0 max-w-[55%] shrink gap-2 px-2" aria-description={`Couleurs réelles : ${steps.map(step => step.name).join(", ")}. Choisissez un fil pour rejoindre son début de couture.`}>
      <ListOrdered size={15} aria-hidden="true" />
      {steps.length === 1 && <span className="size-3 shrink-0 rounded-full border border-foreground/30" style={{ backgroundColor: steps[0].color }} aria-hidden="true" />}
      <span className="truncate">{steps.length === 1 ? `Fil · ${steps[0].name}` : `Fils · ${steps.length}`}</span><ChevronDown size={12} aria-hidden="true" />
    </Button>
    <Popover.Content placement="bottom start">
      <Popover.Dialog className="flex w-52 max-w-[calc(100vw-2rem)] flex-col gap-2 p-2">
        <div className="flex shrink-0 items-center justify-between gap-4 px-2">
          <Popover.Heading className="text-xs font-medium">Ordre des fils</Popover.Heading>
          <span className="text-[11px] text-muted" title={plan.threadWeight ? `${plan.threadWeight} wt pour tous les fils` : "Titrage du fil non renseigné"}>{plan.threadWeight ? `${plan.threadWeight} wt` : "—"}</span>
        </div>
        <ol ref={list} className="flex max-h-[min(20rem,45dvh)] min-h-0 flex-col gap-1 overflow-y-auto overscroll-contain" aria-label="Passages de couleur">
          {steps.map(step => {
            const status = threadStepStatus(step, cursor);
            const active = status === "active";
            const statusLabel = active ? "En cours" : status === "completed" ? "Terminé" : "À venir";
            const StatusIcon = active ? CircleDot : status === "completed" ? Check : Circle;
            return <li key={step.index} title={`${step.color} · ${step.firstStitch === null ? "Aucun point cousu" : `Début au point ${formatNumber(step.firstStitch)} · ${sewingTime(step.startMinutes)} de couture`}`}>
              <Button variant={active ? "secondary" : "ghost"} className="h-auto min-h-11 w-full justify-start rounded-lg p-0 text-left" onPress={() => { onSeek(step.startCursor); setOpen(false); }} aria-current={active ? "step" : undefined} aria-label={`Fil ${step.index + 1} · ${step.name} · ${statusLabel}. ${formatNumber(step.stitchCount)} points, début à ${sewingTime(step.startMinutes)}. Aller au début du passage.`}>
                <span className="flex w-full min-w-0 flex-col gap-0.5 rounded-lg px-2 py-1">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="size-3.5 shrink-0 rounded-full border border-foreground/25" style={{ backgroundColor: step.color }} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate text-xs font-medium leading-4">{step.index + 1}. {step.name}</span>
                    <StatusIcon size={12} className={active ? "shrink-0 text-accent" : "shrink-0 text-muted"} aria-hidden="true" />
                  </span>
                  <span className="flex items-center justify-between gap-2 text-[11px] font-normal leading-3 text-muted tabular-nums"><span>{sewingTime(step.startMinutes)}</span><span>{formatNumber(step.stitchCount)} pts</span></span>
                </span>
              </Button>
            </li>;
          })}
        </ol>
        <p className="px-2 text-[11px] text-muted">Couleurs réelles des fils, même en mode Contraste.</p>
      </Popover.Dialog>
    </Popover.Content>
  </Popover>;
}
