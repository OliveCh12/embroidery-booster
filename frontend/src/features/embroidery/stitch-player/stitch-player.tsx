"use client";

import { Alert, Button, Label, ListBox, Popover, Select, Slider, Spinner } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { Pause, Play, RotateCcw, SkipForward, SlidersHorizontal, StepForward } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { ToggleSetting } from "../controls";
import { StitchCanvas } from "./canvas";
import { advancePlayback, buildThreadSequence, eventLabel, parseStitchPlan, type StitchPlan } from "./model";
import { sewingTime, ThreadList } from "./thread-list";

function Timeline({ plan }: { plan: StitchPlan }) {
  const [cursor, setCursor] = useState(plan.count);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("60");
  const [underlay, setUnderlay] = useState(true);
  const [travel, setTravel] = useState(false);
  const [pauseAtColor, setPauseAtColor] = useState(true);
  const [waitingForThread, setWaitingForThread] = useState(false);
  const position = useRef(plan.count);
  const threads = useMemo(() => buildThreadSequence(plan), [plan]);
  const total = plan.stitches[plan.count], sewn = plan.stitches[cursor];
  const activeThread = cursor ? plan.colors[cursor - 1] : 0;

  function seek(next: number) { position.current = next; setCursor(next); setPlaying(false); setWaitingForThread(false); }
  function play(byThread: boolean) {
    if (position.current === plan.count) { position.current = 0; setCursor(0); }
    setPauseAtColor(byThread);
    setWaitingForThread(false);
    setPlaying(true);
  }

  useEffect(() => {
    if (!playing) return;
    let frame = 0, previous = 0, credit = 0;
    function tick(time: number) {
      if (!previous) previous = time;
      credit += Math.min(time - previous, 100) * plan.stitchesPerMinute / 60_000 * Number(speed);
      previous = time;
      const budget = Math.floor(credit);
      const start = position.current;
      const next = advancePlayback(plan, start, budget, pauseAtColor);
      credit -= plan.stitches[next.cursor] - plan.stitches[start];
      position.current = next.cursor;
      if (next.cursor !== start) setCursor(next.cursor);
      if (next.cursor === plan.count || next.pausedForColor) { setPlaying(false); setWaitingForThread(next.pausedForColor); return; }
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, pauseAtColor, plan]);

  return <div className="flex min-h-full min-w-0 flex-1 flex-col gap-4 md:h-full">
    <div className="grid min-h-0 flex-1 gap-4 @2xl:grid-cols-[220px_minmax(0,1fr)]">
      <ThreadList plan={plan} steps={threads} cursor={cursor} onSeek={seek} />
      <div className="order-1 flex min-h-0 min-w-0 flex-col gap-4 @2xl:order-none">
        <StitchCanvas plan={plan} cursor={cursor} underlay={underlay} travel={travel} />
        <div className={`flex shrink-0 flex-wrap items-center justify-between gap-4 rounded-lg px-4 py-2 text-xs ${waitingForThread ? "bg-warning-soft text-warning-soft-foreground" : "bg-background text-muted"}`}>
          <span role="status" aria-live="polite">{waitingForThread ? `Installez le fil ${activeThread + 1} · ${threads[activeThread].name}, puis reprenez la lecture.` : `${eventLabel(plan, cursor)} · fil ${activeThread + 1}/${threads.length}`}</span>
          <span className="tabular-nums">{formatNumber(sewn)} / {formatNumber(total)} points · {formatNumber(sewn / total * 100)} %</span>
        </div>
      </div>
    </div>
    <div className="flex shrink-0 flex-wrap items-center gap-4">
      <div className="flex flex-wrap items-center gap-4" aria-label="Modes de lecture">
        <Button size="sm" variant={pauseAtColor ? "secondary" : "primary"} onPress={() => play(false)} aria-pressed={!pauseAtColor}><Play size={16} />Tout lire</Button>
        <Button size="sm" variant={pauseAtColor ? "primary" : "secondary"} onPress={() => play(true)} aria-pressed={pauseAtColor}><Play size={16} />{waitingForThread ? "Reprendre par fil" : "Lire par fil"}</Button>
        {playing && <Button size="sm" variant="secondary" onPress={() => setPlaying(false)}><Pause size={16} />Pause</Button>}
      </div>
      <div className="flex items-center gap-4">
        <Button size="sm" variant="secondary" isIconOnly aria-label="Revenir au premier point" onPress={() => seek(0)}><RotateCcw size={16} /></Button>
        <Button size="sm" variant="secondary" isIconOnly aria-label="Commande suivante" isDisabled={cursor === plan.count} onPress={() => seek(Math.min(plan.count, cursor + 1))}><StepForward size={16} /></Button>
        <Button size="sm" variant="secondary" isIconOnly aria-label="Afficher la broderie complète" isDisabled={cursor === plan.count} onPress={() => seek(plan.count)}><SkipForward size={16} /></Button>
      </div>
      <Select value={speed} onChange={value => { if (typeof value === "string") setSpeed(value); }} aria-label="Vitesse de simulation" variant="secondary" className="ml-auto w-20 shrink-0">
        <Select.Trigger className="min-h-8 py-1"><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox aria-label="Vitesse de simulation">{["1", "10", "60", "240"].map(value => <ListBox.Item key={value} id={value} textValue={`×${value}`}><Label>×{value}</Label><ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
      </Select>
      <Popover>
        <Button size="sm" variant="secondary" isIconOnly aria-label="Options de l’aperçu"><SlidersHorizontal size={16} /></Button>
        <Popover.Content placement="top end"><Popover.Dialog className="flex w-72 flex-col gap-4 p-4">
          <Popover.Heading>Options de l’aperçu</Popover.Heading>
          <ToggleSetting label="Afficher la sous-couche" value={underlay} onChange={setUnderlay} />
          <ToggleSetting label="Liaisons, sauts et ancrages" value={travel} onChange={setTravel} />
          <p className="text-xs leading-relaxed text-muted">Couverture : couleur du fil. Sous-couche : gris. Liaisons : ambre ; sauts en pointillés. Ancrages : violet. Les repères vert (départ) et rouge (aiguille) apparaissent pendant la lecture.</p>
          <p className="text-xs leading-relaxed text-muted">Dessin : {formatNumber(plan.bounds[2] - plan.bounds[0])} × {formatNumber(plan.bounds[3] - plan.bounds[1])} mm. Grille de 10 mm.</p>
          <p className="text-xs leading-relaxed text-muted">Simulation à {plan.stitchesPerMinute} points/min, accélérée ×{speed}. Sauts, coupes et changements de fil ne sont pas chronométrés.</p>
        </Popover.Dialog></Popover.Content>
      </Popover>
    </div>
    <div className="flex shrink-0 items-center gap-4 text-xs text-muted">
      <span className="shrink-0 tabular-nums" aria-label="Temps de couture écoulé">{sewingTime(sewn / plan.stitchesPerMinute)}</span>
      <Slider value={cursor} onChange={value => seek(Array.isArray(value) ? value[0] : value)} minValue={0} maxValue={plan.count} step={1} aria-label="Avancement de la broderie" className="min-w-0 flex-1">
        <Slider.Track><Slider.Fill /><Slider.Thumb aria-label="Position de lecture" /></Slider.Track>
      </Slider>
      <span className="shrink-0 tabular-nums" aria-label="Durée de couture estimée">{sewingTime(total / plan.stitchesPerMinute)}</span>
    </div>
  </div>;
}

export function StitchPlayer({ url }: { url: string }) {
  const query = useQuery({ queryKey: ["stitch-plan", url], queryFn: async ({ signal }) => parseStitchPlan(await apiRequest<unknown>(url, { signal })), staleTime: Infinity });
  if (query.isError) return <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Aperçu indisponible</Alert.Title><Alert.Description>{query.error.message}</Alert.Description><Button variant="secondary" size="sm" className="mt-4" onPress={() => { void query.refetch(); }}>Réessayer</Button></Alert.Content></Alert>;
  if (!query.data) return <div className="flex min-h-64 flex-1 items-center justify-center gap-4 text-muted" role="status"><Spinner />Chargement des points machine…</div>;
  return <Timeline key={url} plan={query.data} />;
}
