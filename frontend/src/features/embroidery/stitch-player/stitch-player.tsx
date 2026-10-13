"use client";

import { Alert, Button, Label, ListBox, Popover, Select, Slider, Spinner } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { Contrast, Pause, Play, RotateCcw, SkipForward, SlidersHorizontal, StepForward } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { ToggleSetting } from "../controls";
import { StitchCanvas } from "./canvas";
import type { PreviewColorMode } from "./canvas-theme";
import { advancePlayback, buildThreadSequence, eventLabel, parseStitchPlan, type StitchPlan } from "./model";
import { sewingTime, ThreadList } from "./thread-list";
import styles from "./stitch-player.module.css";

function Timeline({ plan, colorMode, onToggleContrast }: { plan: StitchPlan; colorMode: PreviewColorMode; onToggleContrast: () => void }) {
  const [cursor, setCursor] = useState(plan.count);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("150");
  const [underlay, setUnderlay] = useState(true);
  const [travel, setTravel] = useState(false);
  const [pauseAtColor, setPauseAtColor] = useState(false);
  const [waitingForThread, setWaitingForThread] = useState(false);
  const position = useRef(plan.count);
  const threads = useMemo(() => buildThreadSequence(plan), [plan]);
  const total = plan.stitches[plan.count], sewn = plan.stitches[cursor];
  const activeThread = cursor ? plan.colors[cursor - 1] : 0;

  function seek(next: number) { position.current = next; setCursor(next); setPlaying(false); setWaitingForThread(false); }
  function play() {
    if (position.current === plan.count) { position.current = 0; setCursor(0); }
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
    <div className="relative min-h-[360px] min-w-0 flex-1 md:min-h-[280px]">
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-4"
        onClick={event => event.stopPropagation()} onPaste={event => event.stopPropagation()}
        onDrop={event => { event.preventDefault(); event.stopPropagation(); }} onDragEnter={event => event.stopPropagation()}
        onDragOver={event => { event.preventDefault(); event.stopPropagation(); }} onDragLeave={event => event.stopPropagation()}>
        <ThreadList plan={plan} steps={threads} cursor={cursor} onSeek={seek} />
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant={colorMode === "contrast" ? "secondary" : "ghost"} aria-label="Contraste d’affichage" aria-pressed={colorMode === "contrast"}
            aria-description="Ajuste uniquement les couleurs peu lisibles dans l’aperçu. Les fils réels et les fichiers restent inchangés."
            className="shrink-0 gap-2 px-2" onPress={onToggleContrast}>
            <Contrast size={15} aria-hidden="true" />{colorMode === "contrast" ? "Contraste actif" : "Contraste"}
          </Button>
          <Popover>
            <Button size="sm" variant="ghost" isIconOnly aria-label="Options de l’aperçu"><SlidersHorizontal size={16} /></Button>
            <Popover.Content placement="bottom end"><Popover.Dialog className="flex w-72 flex-col gap-4 p-4">
              <Popover.Heading>Options de l’aperçu</Popover.Heading>
              <Select value={speed} onChange={value => { if (typeof value === "string") setSpeed(value); }} aria-label="Vitesse de simulation" variant="secondary">
                <Label>Vitesse de simulation</Label><Select.Trigger className="min-h-8 py-1"><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox aria-label="Vitesse de simulation">{["1", "10", "60", "150", "240"].map(value => <ListBox.Item key={value} id={value} textValue={`×${value}`}><Label>×{value}</Label><ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
              </Select>
              <ToggleSetting label="Afficher la sous-couche" value={underlay} onChange={setUnderlay} />
              <ToggleSetting label="Liaisons, sauts et ancrages" value={travel} onChange={setTravel} />
              <Button size="sm" variant="secondary" isDisabled={cursor === plan.count} onPress={() => seek(Math.min(plan.count, cursor + 1))}><StepForward size={16} />Commande suivante</Button>
              <p className="text-xs leading-relaxed text-muted">Continu traverse toutes les couleurs ; Par fil attend votre reprise à chaque changement. Modifier le mode ajuste les prochains arrêts et ne reprend pas une lecture en pause.</p>
              <p className="text-xs leading-relaxed text-muted">Le mode Couleurs réelles conserve les fils d’origine, y compris pour la sous-couche. Contraste ajuste seulement les teintes peu lisibles à l’écran ; la liste des fils et les fichiers restent inchangés. Les sauts sont en pointillés. Vert : départ, rouge : aiguille.</p>
              <p className="text-xs leading-relaxed text-muted">Dessin : {formatNumber(plan.bounds[2] - plan.bounds[0])} × {formatNumber(plan.bounds[3] - plan.bounds[1])} mm. Grille de 10 mm.</p>
              <p className="text-xs leading-relaxed text-muted">Simulation à {plan.stitchesPerMinute} points/min, accélérée ×{speed}. Sauts, coupes et changements de fil ne sont pas chronométrés.</p>
            </Popover.Dialog></Popover.Content>
          </Popover>
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 top-10 flex min-h-0">
        <StitchCanvas plan={plan} cursor={cursor} underlay={underlay} travel={travel} colorMode={colorMode} />
      </div>
    </div>
    <div className="flex shrink-0 flex-wrap items-center gap-4 border-t border-border pt-4">
      <div className="flex shrink-0 items-center gap-1" aria-label="Commandes de lecture">
        <Button size="sm" variant="secondary" isIconOnly aria-label={playing ? "Mettre en pause" : waitingForThread ? "Reprendre la lecture" : "Lire la broderie"} onPress={() => playing ? setPlaying(false) : play()}>{playing ? <Pause size={16} /> : <Play size={16} />}</Button>
        <Button size="sm" variant="ghost" isIconOnly aria-label="Revenir au premier point" onPress={() => seek(0)}><RotateCcw size={15} /></Button>
        <Button size="sm" variant="ghost" isIconOnly aria-label="Afficher la broderie complète" isDisabled={cursor === plan.count} onPress={() => seek(plan.count)}><SkipForward size={15} /></Button>
      </div>
      <Select value={pauseAtColor ? "thread" : "continuous"} onChange={value => { if (typeof value === "string") setPauseAtColor(value === "thread"); }} aria-label="Mode de lecture" variant="secondary" className="w-28 shrink-0">
        <Select.Trigger className="min-h-8 py-1"><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox aria-label="Mode de lecture"><ListBox.Item id="continuous" textValue="Continu"><Label>Continu</Label><ListBox.ItemIndicator /></ListBox.Item><ListBox.Item id="thread" textValue="Par fil"><Label>Par fil</Label><ListBox.ItemIndicator /></ListBox.Item></ListBox></Select.Popover>
      </Select>
      <span className="min-w-0 text-xs text-muted" title={`${eventLabel(plan, cursor)} · ${formatNumber(sewn)} / ${formatNumber(total)} points`}>{waitingForThread ? `Fil ${activeThread + 1} · ${threads[activeThread].name} à installer` : cursor === plan.count ? "Terminé" : `Fil ${activeThread + 1} · ${threads[activeThread].name}`}</span>
      <span role="status" aria-live="polite" className="sr-only">{waitingForThread ? `Installez le fil ${activeThread + 1} · ${threads[activeThread].name}, puis reprenez la lecture.` : cursor === plan.count ? "Broderie terminée" : ""}</span>
      <Slider value={cursor} onChange={value => seek(Array.isArray(value) ? value[0] : value)} minValue={0} maxValue={plan.count} step={1} aria-label="Avancement de la broderie" className={styles.timeline}>
        <Slider.Track><Slider.Fill /><Slider.Thumb aria-label="Position de lecture" /></Slider.Track>
      </Slider>
      <span className="shrink-0 text-xs text-muted tabular-nums" title="Temps de couture estimé, hors déplacements et changements de bobine">{sewingTime(sewn / plan.stitchesPerMinute)} / {sewingTime(total / plan.stitchesPerMinute)}</span>
    </div>
  </div>;
}

export function StitchPlayer({ url }: { url: string }) {
  const [colorMode, setColorMode] = useState<PreviewColorMode>("real");
  const query = useQuery({ queryKey: ["stitch-plan", url], queryFn: async ({ signal }) => parseStitchPlan(await apiRequest<unknown>(url, { signal })), staleTime: Infinity });
  if (query.isError) return <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Aperçu indisponible</Alert.Title><Alert.Description>{query.error.message}</Alert.Description><Button variant="secondary" size="sm" className="mt-4" onPress={() => { void query.refetch(); }}>Réessayer</Button></Alert.Content></Alert>;
  if (!query.data) return <div className="flex min-h-64 flex-1 items-center justify-center gap-4 text-muted" role="status"><Spinner />Chargement des points machine…</div>;
  return <Timeline key={url} plan={query.data} colorMode={colorMode} onToggleContrast={() => setColorMode(mode => mode === "real" ? "contrast" : "real")} />;
}
