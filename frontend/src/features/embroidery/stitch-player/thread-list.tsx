"use client";

import { Button, Chip } from "@heroui/react";
import { Check, Circle, CircleDot } from "lucide-react";
import { useEffect, useRef } from "react";
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
  const list = useRef<HTMLOListElement>(null);
  const activeIndex = steps.findIndex(step => threadStepStatus(step, cursor) === "active");
  useEffect(() => {
    const container = list.current, row = container?.children[activeIndex];
    if (!container || !row) return;
    const visible = container.getBoundingClientRect(), item = row.getBoundingClientRect();
    if (item.top < visible.top) container.scrollTop -= visible.top - item.top;
    else if (item.bottom > visible.bottom) container.scrollTop += item.bottom - visible.bottom;
  }, [activeIndex]);
  return <aside className="order-2 flex max-h-64 min-h-0 flex-col gap-4 p-2 @2xl:order-none @2xl:max-h-none" aria-label="Séquence des fils">
    <div className="flex shrink-0 items-center justify-between gap-4"><span className="text-sm font-medium">Ordre des fils</span><Chip size="sm" variant="soft" aria-label={plan.threadWeight ? `${plan.threadWeight} wt pour tous les fils` : "Titrage du fil non renseigné"}>{plan.threadWeight ? `${plan.threadWeight} wt` : "—"}</Chip></div>
    <ol ref={list} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain" aria-label="Passages de couleur">
      {steps.map(step => {
        const status = threadStepStatus(step, cursor);
        const active = status === "active";
        const statusLabel = active ? "En cours" : status === "completed" ? "Terminé" : "À venir";
        const StatusIcon = active ? CircleDot : status === "completed" ? Check : Circle;
        return <li key={step.index} title={`${step.color} · ${step.firstStitch === null ? "Aucun point cousu" : `Début au point ${formatNumber(step.firstStitch)} · ${sewingTime(step.startMinutes)} de couture`}`}>
          <Button variant={active ? "secondary" : "ghost"} className="h-auto w-full justify-start rounded-lg p-0 text-left" onPress={() => onSeek(step.startCursor)} aria-current={active ? "step" : undefined} aria-label={`Fil ${step.index + 1} · ${step.name} · ${statusLabel}. Aller au début du passage.`}>
            <span className="flex w-full min-w-0 flex-col gap-1 rounded-lg p-2">
              <span className="flex min-w-0 items-center gap-2">
                <span className="size-5 shrink-0 rounded-full border border-foreground/25" style={{ backgroundColor: step.color }} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{step.index + 1}. {step.name}</span>
                <StatusIcon size={14} className={active ? "shrink-0 text-accent" : "shrink-0 text-muted"} aria-label={statusLabel} />
              </span>
              <span className="flex items-center justify-between gap-2 text-xs font-normal text-muted tabular-nums"><span>À {sewingTime(step.startMinutes)}</span><span>{formatNumber(step.stitchCount)} points</span></span>
            </span>
          </Button>
        </li>;
      })}
    </ol>
  </aside>;
}
