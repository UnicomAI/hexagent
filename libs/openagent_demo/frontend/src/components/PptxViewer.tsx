/**
 * PowerPoint viewer built on pptx-viewer.
 *
 * Lazy-loaded via React.lazy() — pptx-viewer is only fetched
 * when a user actually opens a .pptx file.
 *
 * Layout mirrors PdfViewer:
 *   .pptx-viewer        → scroll container  (= .pdf-viewer)
 *   .document-pages      → flex column + pad (= .pdf-viewer-pages)
 *     .document-page     → width:100% + shadow (= .pdf-page)
 *       SVG              → viewBox scales to fill card
 *
 * Each slide renders as an SVG at the presentation's native dimensions.
 * The SVG's width is set to 100% so it scales to fill the card, and
 * height follows automatically via the viewBox aspect ratio.
 */

import { useState, useEffect, useRef, useCallback, memo } from "react";
import { loadPresentation, renderSlideToElement } from "pptx-viewer";
import type { LoadedPresentation } from "pptx-viewer";
import { Loader2 } from "lucide-react";

/** How many slides to render initially before deferring the rest. */
const INITIAL_BATCH = 3;

interface Props {
  url: string;
  visible: boolean;
}

function PptxViewer({ url, visible }: Props) {
  const [presentation, setPresentation] = useState<LoadedPresentation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  /** How many slides are currently rendered (progressive loading). */
  const [renderedCount, setRenderedCount] = useState(INITIAL_BATCH);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wasVisible = useRef(visible);

  // Reset scroll on panel reopen
  if (visible && !wasVisible.current && scrollRef.current) {
    scrollRef.current.scrollTop = 0;
  }
  wasVisible.current = visible;

  // Fetch & parse the PPTX
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    setRenderedCount(INITIAL_BATCH);

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch");
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        return loadPresentation(buffer);
      })
      .then((pres) => {
        if (!cancelled && pres) {
          setPresentation(pres);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  // Progressively render remaining slides in idle callbacks so the first
  // few slides appear immediately without blocking the main thread.
  useEffect(() => {
    if (!presentation) return;
    const total = presentation.slides.length;
    if (renderedCount >= total) return;

    // Use requestIdleCallback where available, fall back to rAF + setTimeout
    const schedule =
      typeof requestIdleCallback === "function"
        ? requestIdleCallback
        : (cb: () => void) => setTimeout(cb, 32);
    const cancel =
      typeof cancelIdleCallback === "function"
        ? cancelIdleCallback
        : clearTimeout;

    const id = schedule(() => {
      setRenderedCount((n) => Math.min(n + INITIAL_BATCH, total));
    });
    return () => cancel(id);
  }, [presentation, renderedCount]);

  // Cleanup blob URLs when presentation changes or unmounts
  useEffect(() => {
    return () => {
      presentation?.cleanup();
    };
  }, [presentation]);

  if (error) {
    return (
      <div className="file-preview-unsupported">
        <p>Failed to load presentation.</p>
      </div>
    );
  }

  const total = presentation?.slides.length ?? 0;
  const visibleCount = Math.min(renderedCount, total);

  return (
    <div className="pptx-viewer" ref={scrollRef}>
      {loading && (
        <div className="file-preview-loading">
          <Loader2 size={24} className="file-preview-spinner" />
        </div>
      )}
      {presentation && (
        <div className="document-pages pptx-viewer-pages">
          {presentation.slides.slice(0, visibleCount).map((_, i) => (
            <PptxSlide
              key={i}
              presentation={presentation}
              slideIndex={i}
              totalSlides={total}
            />
          ))}
          {visibleCount < total && (
            <div className="file-preview-loading" style={{ padding: "1rem" }}>
              <Loader2 size={20} className="file-preview-spinner" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PptxSlide — renders a single slide SVG into a card
// ---------------------------------------------------------------------------

const PptxSlide = memo(function PptxSlide({
  presentation,
  slideIndex,
  totalSlides,
}: {
  presentation: LoadedPresentation;
  slideIndex: number;
  totalSlides: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  const renderSlide = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    // Clear previous render
    el.innerHTML = "";
    renderSlideToElement(presentation, slideIndex, el);

    // Make the SVG scale responsively within the card
    const svg = el.querySelector("svg");
    if (svg) {
      svg.style.width = "100%";
      svg.style.height = "auto";
      svg.style.display = "block";
    }
  }, [presentation, slideIndex]);

  useEffect(() => {
    renderSlide();
  }, [renderSlide]);

  const { width: sw, height: sh } = presentation.slideSize;

  return (
    <div
      className="document-page pptx-slide"
      style={{ aspectRatio: `${sw} / ${sh}` }}
    >
      <div ref={containerRef} className="pptx-slide-content" />
      <span className="document-page-number">
        {slideIndex + 1} / {totalSlides}
      </span>
    </div>
  );
});

export default PptxViewer;
