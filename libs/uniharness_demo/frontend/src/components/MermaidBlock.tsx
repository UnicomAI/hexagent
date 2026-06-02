import { useEffect, useRef, useState, useCallback } from "react";
import mermaid from "mermaid";
import { Plus, Minus, Maximize2 } from "lucide-react";
import { useThemeMode } from "../hooks/useThemeMode";
import VizModal, { useVizModal } from "./VizModal";

type MermaidConfig = Parameters<typeof mermaid.initialize>[0];

const LIGHT: MermaidConfig = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "base",
  themeVariables: {
    primaryColor: "#ffffff",
    primaryBorderColor: "#dddddd",
    primaryTextColor: "#333333",
    lineColor: "#999999",
    background: "#ffffff",
    clusterBkg: "#f8f8f8",
    clusterBorder: "#dddddd",
    edgeLabelBackground: "#ffffff",
    titleColor: "#333333",
    textColor: "#333333",
  },
};
const DARK: MermaidConfig = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "dark",
  themeVariables: {
    primaryColor: "#111111",
    primaryBorderColor: "#222222",
    primaryTextColor: "#ffffff",
    lineColor: "#666666",
    background: "#161616",
    clusterBkg: "#161616",
    clusterBorder: "#222222",
    edgeLabelBackground: "#161616",
    titleColor: "#cccccc",
    textColor: "#cccccc",
  },
};

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 5;
const ZOOM_STEP = 1.3;
const DRAG_THRESHOLD = 4;

// Serialize mermaid renders — mermaid.initialize() is global state.
let nextId = 0;
let queue: Promise<void> = Promise.resolve();

async function renderMermaid(source: string, config: MermaidConfig): Promise<string> {
  let svg = "";
  let error: unknown;
  queue = queue.then(async () => {
    try {
      mermaid.initialize(config);
      const result = await mermaid.render(`mermaid-${++nextId}`, source);
      svg = result.svg;
    } catch (e) {
      error = e;
    }
  });
  await queue;
  if (error) throw error;
  return svg;
}

// ── ViewBox helpers ──────────────────────────────────────────────────

interface VB { x: number; y: number; w: number; h: number }

function parseVB(svg: SVGSVGElement): VB | null {
  const a = svg.getAttribute("viewBox");
  if (!a) return null;
  const [x, y, w, h] = a.split(/[\s,]+/).map(Number);
  return [x, y, w, h].every((n) => !isNaN(n)) ? { x, y, w, h } : null;
}

function setVB(svg: SVGSVGElement, vb: VB) {
  svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
}

const clampZoom = (z: number) => Math.min(Math.max(z, ZOOM_MIN), ZOOM_MAX);

/** Strip mermaid's inline sizing so CSS can control the SVG dimensions. */
function prepFullscreenSvg(container: HTMLDivElement): SVGSVGElement | null {
  const svg = container.querySelector("svg");
  if (!svg) return null;
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.removeAttribute("style");
  return svg;
}

// ── Component ────────────────────────────────────────────────────────

export default function MermaidBlock({ children, actions }: { children: string; actions?: React.ReactNode }) {
  const inlineDiagramRef = useRef<HTMLDivElement>(null);
  const inlineContainerRef = useRef<HTMLDivElement>(null);
  const modalDiagramRef = useRef<HTMLDivElement>(null);
  const modalAreaRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const modal = useVizModal();
  const theme = useThemeMode();

  // Inline: CSS-transform pan state
  const inlinePan = useRef({ x: 0, y: 0 });

  // Fullscreen: viewBox state
  const origVB = useRef<VB | null>(null);
  const curVB = useRef<VB | null>(null);
  const animId = useRef(0);

  // ── Render inline SVG ──────────────────────────────────────────────
  useEffect(() => {
    const el = inlineDiagramRef.current;
    if (!el) return;
    let cancelled = false;
    renderMermaid(children, theme === "dark" ? DARK : LIGHT).then(
      (svg) => {
        if (cancelled) return;
        el.innerHTML = svg;
        inlinePan.current = { x: 0, y: 0 };
        el.style.transform = "";
        setError(null);
      },
      (e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); },
    );
    return () => { cancelled = true; };
  }, [children, theme]);

  // ── Inline drag + click-to-expand ──────────────────────────────────
  useEffect(() => {
    const container = inlineContainerRef.current;
    const diagram = inlineDiagramRef.current;
    if (!container || !diagram) return;

    const d = { active: false, didDrag: false, sx: 0, sy: 0, lx: 0, ly: 0 };

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
      d.active = true;
      d.didDrag = false;
      d.sx = d.lx = e.clientX;
      d.sy = d.ly = e.clientY;
      container.setPointerCapture(e.pointerId);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!d.active) return;
      if (!d.didDrag &&
        (Math.abs(e.clientX - d.sx) > DRAG_THRESHOLD ||
         Math.abs(e.clientY - d.sy) > DRAG_THRESHOLD)) {
        d.didDrag = true;
      }
      inlinePan.current.x += e.clientX - d.lx;
      inlinePan.current.y += e.clientY - d.ly;
      d.lx = e.clientX;
      d.ly = e.clientY;
      diagram.style.transform =
        `translate(${inlinePan.current.x}px, ${inlinePan.current.y}px)`;
    };

    const onPointerUp = () => {
      if (d.active && !d.didDrag) modal.open();
      d.active = false;
    };

    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointercancel", onPointerUp);
    return () => {
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointercancel", onPointerUp);
    };
  }, [modal]);

  // ── Render fullscreen SVG ──────────────────────────────────────────
  useEffect(() => {
    if (!modal.expanded) return;
    const el = modalDiagramRef.current;
    if (!el) return;
    let cancelled = false;
    renderMermaid(children, theme === "dark" ? DARK : LIGHT).then(
      (svg) => {
        if (cancelled) return;
        el.innerHTML = svg;
        const svgEl = prepFullscreenSvg(el);
        if (!svgEl) return;
        requestAnimationFrame(() => {
          if (cancelled) return;
          const vb = parseVB(svgEl);
          if (!vb) return;
          // Expand viewBox to match container AR → no letterboxing
          const rect = svgEl.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            const cAR = rect.width / rect.height;
            const dAR = vb.w / vb.h;
            if (cAR > dAR) {
              const newW = vb.h * cAR;
              vb.x -= (newW - vb.w) / 2;
              vb.w = newW;
            } else {
              const newH = vb.w / cAR;
              vb.y -= (newH - vb.h) / 2;
              vb.h = newH;
            }
          }
          origVB.current = { ...vb };
          curVB.current = { ...vb };
          setVB(svgEl, vb);
        });
      },
      () => {},
    );
    return () => { cancelled = true; origVB.current = null; curVB.current = null; };
  }, [modal.expanded, children, theme]);

  // ── Fullscreen gestures (drag + wheel zoom/pan) ────────────────────
  useEffect(() => {
    if (!modal.expanded) return;
    const area = modalAreaRef.current;
    if (!area) return;

    const getSvg = (): SVGSVGElement | null =>
      modalDiagramRef.current?.querySelector("svg") ?? null;

    const getZoom = () =>
      origVB.current && curVB.current ? origVB.current.w / curVB.current.w : 1;

    const drag = { active: false, lx: 0, ly: 0, rect: null as DOMRect | null };

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
      drag.active = true;
      drag.lx = e.clientX;
      drag.ly = e.clientY;
      drag.rect = getSvg()?.getBoundingClientRect() ?? null;
      area.setPointerCapture(e.pointerId);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!drag.active) return;
      const vb = curVB.current;
      const r = drag.rect;
      if (!vb || !r) return;
      vb.x -= (e.clientX - drag.lx) * (vb.w / r.width);
      vb.y -= (e.clientY - drag.ly) * (vb.h / r.height);
      drag.lx = e.clientX;
      drag.ly = e.clientY;
      const svg = getSvg();
      if (svg) setVB(svg, vb);
    };

    const onPointerUp = () => { drag.active = false; };

    const zoomToward = (sx: number, sy: number, newZoom: number) => {
      const svg = getSvg();
      const vb = curVB.current;
      const orig = origVB.current;
      if (!svg || !vb || !orig) return;
      const z = clampZoom(newZoom);
      const rect = svg.getBoundingClientRect();
      const svgX = vb.x + (sx / rect.width) * vb.w;
      const svgY = vb.y + (sy / rect.height) * vb.h;
      const newW = orig.w / z;
      const newH = orig.h / z;
      curVB.current = {
        x: svgX - (sx / rect.width) * newW,
        y: svgY - (sy / rect.height) * newH,
        w: newW,
        h: newH,
      };
      setVB(svg, curVB.current);
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const vb = curVB.current;
      if (!vb) return;
      const svg = getSvg();
      if (!svg) return;
      if (e.ctrlKey) {
        const rect = svg.getBoundingClientRect();
        const factor = Math.pow(2, -e.deltaY * 0.01);
        zoomToward(e.clientX - rect.left, e.clientY - rect.top, getZoom() * factor);
      } else {
        const rect = svg.getBoundingClientRect();
        vb.x += e.deltaX * (vb.w / rect.width);
        vb.y += e.deltaY * (vb.h / rect.height);
        setVB(svg, vb);
      }
    };

    area.addEventListener("pointerdown", onPointerDown);
    area.addEventListener("pointermove", onPointerMove);
    area.addEventListener("pointerup", onPointerUp);
    area.addEventListener("pointercancel", onPointerUp);
    area.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      area.removeEventListener("pointerdown", onPointerDown);
      area.removeEventListener("pointermove", onPointerMove);
      area.removeEventListener("pointerup", onPointerUp);
      area.removeEventListener("pointercancel", onPointerUp);
      area.removeEventListener("wheel", onWheel);
    };
  }, [modal.expanded]);

  // ── Zoom buttons (animated) ────────────────────────────────────────
  const zoomByButton = useCallback((factor: number) => {
    const svg = modalDiagramRef.current?.querySelector("svg") as SVGSVGElement | null;
    const vb = curVB.current;
    const orig = origVB.current;
    if (!svg || !vb || !orig) return;

    cancelAnimationFrame(animId.current);

    const targetZoom = clampZoom((orig.w / vb.w) * factor);
    const targetW = orig.w / targetZoom;
    const targetH = orig.h / targetZoom;
    const cx = vb.x + vb.w / 2;
    const cy = vb.y + vb.h / 2;

    const start = { ...vb };
    const t0 = performance.now();
    const step = (now: number) => {
      const p = Math.min((now - t0) / 150, 1);
      const ease = p * (2 - p);
      curVB.current = {
        x: start.x + (cx - targetW / 2 - start.x) * ease,
        y: start.y + (cy - targetH / 2 - start.y) * ease,
        w: start.w + (targetW - start.w) * ease,
        h: start.h + (targetH - start.h) * ease,
      };
      setVB(svg, curVB.current);
      if (p < 1) animId.current = requestAnimationFrame(step);
    };
    animId.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => () => cancelAnimationFrame(animId.current), []);

  if (error) return <pre className="viz-error">{error}</pre>;

  return (
    <>
      <div className="viz-container mermaid-container">
        <div className="viz-actions-anchor">
          <div className="viz-actions">
            {actions}
            <button className="viz-action-btn" onClick={modal.open} aria-label="Expand diagram">
              <Maximize2 />
            </button>
          </div>
        </div>
        <div ref={inlineContainerRef} className="mermaid-content">
          <div ref={inlineDiagramRef} className="mermaid-diagram" />
        </div>
      </div>

      <VizModal
        state={modal.state}
        onClose={modal.close}
        onExitDone={modal.onExitDone}
        actions={
          <>
            <button className="viz-action-btn" onClick={() => zoomByButton(ZOOM_STEP)} aria-label="Zoom in"><Plus /></button>
            <button className="viz-action-btn" onClick={() => zoomByButton(1 / ZOOM_STEP)} aria-label="Zoom out"><Minus /></button>
          </>
        }
      >
        <div ref={modalAreaRef} className="mermaid-modal-svg">
          <div ref={modalDiagramRef} className="mermaid-diagram" />
        </div>
      </VizModal>
    </>
  );
}
