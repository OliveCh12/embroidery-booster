"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { pointAt, viewport, type StitchPlan } from "./model";

interface CanvasOptions { dark: boolean; underlay: boolean; travel: boolean }

class StitchRenderer {
  private cursor = 0;
  private target = 0;
  private frame = 0;
  private width = 0;
  private height = 0;
  private transform = viewport(1, 1, 100, 100);
  private context: CanvasRenderingContext2D;
  private overlay: CanvasRenderingContext2D;

  constructor(private canvas: HTMLCanvasElement, private needle: HTMLCanvasElement, private plan: StitchPlan, private options: CanvasOptions) {
    const context = canvas.getContext("2d"), overlay = needle.getContext("2d");
    if (!context || !overlay) throw new Error("Le navigateur ne prend pas en charge l’aperçu des points.");
    this.context = context; this.overlay = overlay;
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
    ctx.fillStyle = this.options.dark ? "#1c222c" : "#f2f4f7";
    ctx.fillRect(0, 0, width, height);
    const { left, top, scale } = this.transform, hoop = this.plan.hoop;
    ctx.fillStyle = this.options.dark ? "#717b8c" : "#c4ccd7";
    ctx.fillRect(left, top, hoop.width * scale, hoop.height * scale);
    ctx.strokeStyle = this.options.dark ? "#414b5b" : "#a4afbf";
    ctx.lineWidth = 0.5; ctx.setLineDash([]); ctx.beginPath();
    for (let mm = Math.ceil(-hoop.width / 20) * 10; mm <= hoop.width / 2; mm += 10) { ctx.moveTo(this.x(mm), top); ctx.lineTo(this.x(mm), top + hoop.height * scale); }
    for (let mm = Math.ceil(-hoop.height / 20) * 10; mm <= hoop.height / 2; mm += 10) { ctx.moveTo(left, this.y(mm)); ctx.lineTo(left + hoop.width * scale, this.y(mm)); }
    ctx.stroke();
    ctx.strokeStyle = this.options.dark ? "#c6ceda" : "#758196";
    ctx.lineWidth = 1; ctx.strokeRect(left, top, hoop.width * scale, hoop.height * scale);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = this.options.dark ? "#d3dae5" : "#5e6b80";
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
    let style = "", drawing = false;
    for (let index = this.cursor; index < end; index++) {
      const sewn = plan.codes[index] === plan.command.stitch && index > 0 && plan.codes[index - 1] === plan.command.stitch;
      const jump = this.options.travel && plan.codes[index] === plan.command.jump && index > 0;
      if (!sewn && !jump || sewn && plan.underlay[index] && !this.options.underlay) continue;
      const underlay = sewn && plan.underlay[index] === 1;
      const nextStyle = jump ? "jump" : underlay ? "underlay" : plan.threads[plan.colors[index]];
      if (nextStyle !== style) {
        if (drawing) ctx.stroke();
        style = nextStyle; drawing = true;
        ctx.beginPath(); ctx.setLineDash(jump ? [3, 4] : []);
        ctx.strokeStyle = jump ? (this.options.dark ? "#e4e8f0" : "#56647a") : underlay ? "#8c8c8c" : nextStyle;
        ctx.lineWidth = jump ? 0.7 : underlay ? Math.max(0.5, 0.15 * this.transform.scale) : Math.max(0.65, 0.3 * this.transform.scale);
        ctx.lineCap = "round"; ctx.lineJoin = "round";
      }
      ctx.moveTo(this.x(plan.points[(index - 1) * 2]), this.y(plan.points[(index - 1) * 2 + 1]));
      ctx.lineTo(this.x(plan.points[index * 2]), this.y(plan.points[index * 2 + 1]));
    }
    if (drawing) ctx.stroke();
    this.cursor = end; this.drawNeedle();
    this.canvas.dataset.ready = String(this.cursor === this.target);
    if (this.cursor < this.target) this.schedule();
  }

  private drawNeedle() {
    const ctx = this.overlay;
    ctx.clearRect(0, 0, this.width, this.height);
    const firstIndex = this.plan.codes.indexOf(this.plan.command.stitch);
    if (firstIndex >= 0) {
      ctx.strokeStyle = "#147d52"; ctx.lineWidth = 2; ctx.setLineDash([]); ctx.beginPath();
      ctx.arc(this.x(this.plan.points[firstIndex * 2]), this.y(this.plan.points[firstIndex * 2 + 1]), 5, 0, 2 * Math.PI); ctx.stroke();
    }
    const point = pointAt(this.plan, this.cursor);
    if (!point) return;
    const x = this.x(point[0]), y = this.y(point[1]);
    if (this.plan.codes[this.cursor - 1] === this.plan.command.jump && this.cursor > 1) {
      ctx.strokeStyle = "#f59e0b"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.beginPath();
      ctx.moveTo(this.x(this.plan.points[(this.cursor - 2) * 2]), this.y(this.plan.points[(this.cursor - 2) * 2 + 1])); ctx.lineTo(x, y); ctx.stroke();
    }
    ctx.setLineDash([]); ctx.fillStyle = "#ef4444"; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x - 9, y); ctx.lineTo(x + 9, y); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 9); ctx.stroke();
  }
}

export function StitchCanvas({ plan, cursor, underlay, travel }: { plan: StitchPlan; cursor: number; underlay: boolean; travel: boolean }) {
  const wrapper = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), needle = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<StitchRenderer | null>(null);
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    const element = wrapper.current;
    if (!element || !canvas.current || !needle.current) return;
    const current = new StitchRenderer(canvas.current, needle.current, plan, { dark: resolvedTheme === "dark", underlay, travel });
    renderer.current = current;
    const observer = new ResizeObserver(([entry]) => current.resize(entry.contentRect.width, entry.contentRect.height));
    observer.observe(element);
    return () => { observer.disconnect(); current.destroy(); renderer.current = null; };
  }, [plan, resolvedTheme, underlay, travel]);
  useEffect(() => { renderer.current?.setCursor(cursor); }, [cursor, plan, resolvedTheme, underlay, travel]);
  return <div ref={wrapper} className="relative min-h-64 flex-1 overflow-hidden rounded-xl border border-border" role="img" aria-label={`Cadre ${plan.hoop.width} par ${plan.hoop.height} mm. ${plan.stitches[cursor]} points cousus. Grille de 10 mm. Vert : premier point, rouge : aiguille.`}>
    <canvas ref={canvas} className="absolute inset-0 size-full" aria-hidden="true" />
    <canvas ref={needle} className="pointer-events-none absolute inset-0 size-full" aria-hidden="true" />
  </div>;
}
