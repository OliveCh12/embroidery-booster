"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { readCanvasTheme, threadNeedsOutline } from "./canvas-theme";
import { pointAt, STITCH_PHASE, viewport, type StitchPlan } from "./model";

interface CanvasOptions { underlay: boolean; travel: boolean }

class StitchRenderer {
  private cursor = 0;
  private target = 0;
  private frame = 0;
  private width = 0;
  private height = 0;
  private transform = viewport(1, 1, 100, 100);
  private context: CanvasRenderingContext2D;
  private overlay: CanvasRenderingContext2D;
  private firstStitch: number;
  private colors: ReturnType<typeof readCanvasTheme>;
  private outlinedThreads: boolean[];

  constructor(private canvas: HTMLCanvasElement, private needle: HTMLCanvasElement, private plan: StitchPlan, private options: CanvasOptions) {
    const context = canvas.getContext("2d"), overlay = needle.getContext("2d");
    if (!context || !overlay) throw new Error("Le navigateur ne prend pas en charge l’aperçu des points.");
    this.context = context; this.overlay = overlay;
    this.firstStitch = plan.codes.indexOf(plan.command.stitch);
    this.colors = readCanvasTheme(canvas);
    this.outlinedThreads = plan.threads.map(color => threadNeedsOutline(color, this.colors.textile));
  }

  resize(width: number, height: number) {
    this.width = width; this.height = height;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    for (const canvas of [this.canvas, this.needle]) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); }
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.overlay.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.transform = viewport(width, height, this.plan.hoop.width, this.plan.hoop.height);
    this.reset(); this.schedule();
  }

  setCursor(cursor: number) {
    this.target = Math.min(this.plan.count, Math.max(0, cursor));
    if (this.target < this.cursor) this.reset();
    this.schedule();
  }

  destroy() { cancelAnimationFrame(this.frame); }

  private schedule() { if (!this.frame) this.frame = requestAnimationFrame(() => this.draw()); }
  private x(value: number) { return this.transform.centerX + value * this.transform.scale; }
  private y(value: number) { return this.transform.centerY + value * this.transform.scale; }

  private reset() {
    this.cursor = 0;
    const ctx = this.context, { width, height } = this;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = this.colors.background;
    ctx.fillRect(0, 0, width, height);
    const { left, top, scale } = this.transform, hoop = this.plan.hoop;
    ctx.fillStyle = this.colors.textile;
    ctx.fillRect(left, top, hoop.width * scale, hoop.height * scale);
    ctx.strokeStyle = this.colors.grid;
    ctx.lineWidth = 0.5; ctx.setLineDash([]); ctx.beginPath();
    for (let mm = Math.ceil(-hoop.width / 20) * 10; mm <= hoop.width / 2; mm += 10) { ctx.moveTo(this.x(mm), top); ctx.lineTo(this.x(mm), top + hoop.height * scale); }
    for (let mm = Math.ceil(-hoop.height / 20) * 10; mm <= hoop.height / 2; mm += 10) { ctx.moveTo(left, this.y(mm)); ctx.lineTo(left + hoop.width * scale, this.y(mm)); }
    ctx.stroke();
    ctx.strokeStyle = this.colors.hoop;
    ctx.lineWidth = 1; ctx.strokeRect(left, top, hoop.width * scale, hoop.height * scale);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = this.colors.label;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const labelStep = scale < 3 ? 20 : 10;
    for (let mm = Math.ceil(-hoop.width / (2 * labelStep)) * labelStep; mm <= hoop.width / 2; mm += labelStep) ctx.fillText(String(mm + hoop.width / 2), this.x(mm), top + hoop.height * scale + 16);
    ctx.textAlign = "right";
    for (let mm = Math.ceil(-hoop.height / (2 * labelStep)) * labelStep; mm <= hoop.height / 2; mm += labelStep) ctx.fillText(String(mm + hoop.height / 2), left - 8, this.y(mm));
    ctx.textAlign = "center"; ctx.fillText(`${hoop.width} × ${hoop.height} mm`, width / 2, top - 14);
    this.canvas.dataset.ready = "false";
  }

  private draw() {
    this.frame = 0;
    if (!this.width || !this.height) return;
    const ctx = this.context, { plan } = this;
    // Full scrubs are chunked; normal playback appends only the new stitch segments.
    const end = Math.min(this.target, this.cursor + 8_000);
    let style = "", drawing = false, outline = false;
    const stroke = () => {
      if (outline) {
        const color = ctx.strokeStyle, width = ctx.lineWidth;
        ctx.strokeStyle = this.colors.threadOutline;
        ctx.lineWidth = width + 0.55;
        ctx.stroke();
        ctx.strokeStyle = color; ctx.lineWidth = width;
      }
      ctx.stroke();
    };
    for (let index = this.cursor; index < end; index++) {
      const sewn = plan.codes[index] === plan.command.stitch && index > 0 && plan.codes[index - 1] === plan.command.stitch;
      const jump = this.options.travel && plan.codes[index] === plan.command.jump && index > 0;
      const underlay = sewn && plan.phases[index] === STITCH_PHASE.underlay;
      const travel = sewn && plan.phases[index] === STITCH_PHASE.travel;
      const lock = sewn && plan.phases[index] === STITCH_PHASE.lock;
      if (!sewn && !jump || underlay && !this.options.underlay || (travel || lock) && !this.options.travel) continue;
      const nextStyle = jump ? "jump" : underlay ? "underlay" : travel ? "travel" : lock ? "lock" : plan.threads[plan.colors[index]];
      if (nextStyle !== style) {
        if (drawing) stroke();
        style = nextStyle; drawing = true;
        outline = !jump && !underlay && !travel && !lock && this.outlinedThreads[plan.colors[index]];
        ctx.beginPath(); ctx.setLineDash(jump ? [3, 4] : []);
        ctx.strokeStyle = jump || travel ? this.colors.travel : lock ? this.colors.lock : underlay ? this.colors.underlay : nextStyle;
        ctx.lineWidth = jump ? 0.7 : underlay || travel || lock ? Math.max(0.5, 0.15 * this.transform.scale) : Math.max(0.65, 0.3 * this.transform.scale);
        ctx.lineCap = "round"; ctx.lineJoin = "round";
      }
      ctx.moveTo(this.x(plan.points[(index - 1) * 2]), this.y(plan.points[(index - 1) * 2 + 1]));
      ctx.lineTo(this.x(plan.points[index * 2]), this.y(plan.points[index * 2 + 1]));
    }
    if (drawing) stroke();
    this.cursor = end; this.drawNeedle();
    this.canvas.dataset.ready = String(this.cursor === this.target);
    if (this.cursor < this.target) this.schedule();
  }

  private drawNeedle() {
    const ctx = this.overlay;
    ctx.clearRect(0, 0, this.width, this.height);
    if (this.cursor === this.plan.count) return;
    const firstIndex = this.firstStitch;
    if (firstIndex >= 0) {
      ctx.strokeStyle = this.colors.textile; ctx.lineWidth = 4; ctx.setLineDash([]); ctx.beginPath();
      ctx.arc(this.x(this.plan.points[firstIndex * 2]), this.y(this.plan.points[firstIndex * 2 + 1]), 5, 0, 2 * Math.PI); ctx.stroke();
      ctx.strokeStyle = this.colors.start; ctx.lineWidth = 2; ctx.stroke();
    }
    const point = pointAt(this.plan, this.cursor);
    if (!point) return;
    const x = this.x(point[0]), y = this.y(point[1]);
    if (this.plan.codes[this.cursor - 1] === this.plan.command.jump && this.cursor > 1) {
      ctx.strokeStyle = this.colors.travel; ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.beginPath();
      ctx.moveTo(this.x(this.plan.points[(this.cursor - 2) * 2]), this.y(this.plan.points[(this.cursor - 2) * 2 + 1])); ctx.lineTo(x, y); ctx.stroke();
    }
    ctx.setLineDash([]); ctx.fillStyle = this.colors.needle; ctx.strokeStyle = this.colors.textile; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(x - 9, y); ctx.lineTo(x + 9, y); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 9); ctx.stroke();
    ctx.strokeStyle = this.colors.needle; ctx.lineWidth = 1; ctx.stroke();
  }
}

export function StitchCanvas({ plan, cursor, underlay, travel }: { plan: StitchPlan; cursor: number; underlay: boolean; travel: boolean }) {
  const wrapper = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), needle = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<StitchRenderer | null>(null);
  const latestCursor = useRef(cursor);
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    const element = wrapper.current;
    if (!element || !canvas.current || !needle.current) return;
    const drawing = canvas.current, overlay = needle.current;
    let current: StitchRenderer | null = null, observer: ResizeObserver | null = null;
    // next-themes applies its DOM class in a parent effect, after this child effect.
    const frame = requestAnimationFrame(() => {
      const instance = new StitchRenderer(drawing, overlay, plan, { underlay, travel });
      current = instance; renderer.current = instance;
      instance.setCursor(latestCursor.current);
      observer = new ResizeObserver(([entry]) => instance.resize(entry.contentRect.width, entry.contentRect.height));
      observer.observe(element);
    });
    return () => {
      cancelAnimationFrame(frame); observer?.disconnect(); current?.destroy();
      if (renderer.current === current) renderer.current = null;
    };
  }, [plan, resolvedTheme, underlay, travel]);
  useEffect(() => { latestCursor.current = cursor; renderer.current?.setCursor(cursor); }, [cursor, plan, resolvedTheme, underlay, travel]);
  return <div ref={wrapper} className="relative min-h-64 flex-1 overflow-hidden rounded-xl border border-border @2xl:min-h-40" role="img" aria-label={`Cadre ${plan.hoop.width} par ${plan.hoop.height} mm. ${plan.stitches[cursor]} points cousus. Grille de 10 mm. Vert : premier point, rouge : aiguille.`}>
    <canvas ref={canvas} className="absolute inset-0 size-full" aria-hidden="true" />
    <canvas ref={needle} className="pointer-events-none absolute inset-0 size-full" aria-hidden="true" />
  </div>;
}
