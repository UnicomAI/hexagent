/**
 * PDF viewer built on react-pdf (which wraps pdfjs-dist).
 *
 * Lazy-loaded via React.lazy() — react-pdf + pdfjs-dist are only fetched
 * when a user actually opens a PDF file.
 */

import { useState, useEffect, useRef, useCallback, useMemo, memo } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { Loader2 } from "lucide-react";

// Worker — must match react-pdf's bundled pdfjs-dist version
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// ---------------------------------------------------------------------------
// PdfPage — renders lazily via IntersectionObserver
// ---------------------------------------------------------------------------

const PdfPage = memo(function PdfPage({
  pageNum,
  totalPages,
  width,
  aspectRatio,
}: {
  pageNum: number;
  totalPages: number;
  width: number;
  /** CSS aspect-ratio value (e.g. "612 / 792") so the wrapper tracks resize. */
  aspectRatio: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(pageNum === 1);

  // Lock render width on first render — CSS width:100% handles visual
  // scaling during resize, so we never need to re-render the canvas.
  const renderWidth = useRef(width);

  // Two IntersectionObservers:
  //   • Inner (400px margin): triggers rendering when approaching viewport
  //   • Outer (2000px margin): frees canvas memory when scrolled far away
  //
  // On unload we zero out canvas dimensions before unmounting — browsers
  // don't always free GPU-backed bitmap memory when a canvas is simply
  // removed from the DOM, but setting width/height to 0 forces it.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const loadObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setActive(true);
      },
      { rootMargin: "400px" },
    );

    const unloadObserver = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          // Zero canvas dimensions to release GPU memory before React unmounts
          const canvas = el.querySelector("canvas");
          if (canvas) {
            canvas.width = 0;
            canvas.height = 0;
          }
          setActive(false);
        }
      },
      { rootMargin: "2000px" },
    );

    loadObserver.observe(el);
    unloadObserver.observe(el);

    return () => {
      loadObserver.disconnect();
      unloadObserver.disconnect();
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className="document-page pdf-page"
      style={{ aspectRatio }}
    >
      {active ? (
        <Page
          pageNumber={pageNum}
          width={renderWidth.current}
          devicePixelRatio={Math.max(window.devicePixelRatio || 1, 3)}
          renderTextLayer={false}
          renderAnnotationLayer={false}
          loading=""
        />
      ) : (
        <div className="pdf-page-loading">
          <Loader2 size={20} className="file-preview-spinner" />
        </div>
      )}
      <span className="document-page-number">
        {pageNum} / {totalPages}
      </span>
    </div>
  );
});

// ---------------------------------------------------------------------------
// PdfViewer — loads document, measures width, renders pages
// ---------------------------------------------------------------------------

interface Props {
  url: string;
  visible: boolean;
}

/** Per-page aspect ratio read from the PDF's native dimensions. */
interface PageDim {
  /** Native width (PDF points). */
  w: number;
  /** Native height (PDF points). */
  h: number;
}

function PdfViewer({ url, visible }: Props) {
  const [pageDims, setPageDims] = useState<PageDim[]>([]);
  const [width, setWidth] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  const wasVisible = useRef(visible);

  // Reset scroll on panel reopen
  if (visible && !wasVisible.current && scrollRef.current) {
    scrollRef.current.scrollTop = 0;
  }
  wasVisible.current = visible;

  // Measure container width once for initial page rendering.
  // CSS width:100% on canvases handles visual scaling after that.
  useEffect(() => {
    const el = pagesRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setWidth((prev) => prev || Math.floor(entry.contentRect.width));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [pageDims.length]);

  // On document load, read every page's native dimensions so we can
  // compute pixel-perfect placeholder heights — no layout shifts.
  const onLoadSuccess = useCallback(
    async (pdf: { numPages: number; getPage: (n: number) => Promise<{ getViewport: (opts: { scale: number }) => { width: number; height: number } }> }) => {
      const dims: PageDim[] = [];
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const vp = page.getViewport({ scale: 1 });
        dims.push({ w: vp.width, h: vp.height });
      }
      setPageDims(dims);
    },
    [],
  );

  const onLoadError = useCallback((error: Error) => {
    console.error("[PdfViewer] Failed to load PDF:", error);
  }, []);

  // Memoize options to avoid re-triggering Document's load effect
  const options = useMemo(
    () => ({
      cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/standard_fonts/`,
      // Disable range requests — our backend streams from a temp file that
      // gets cleaned up after the response, so subsequent range requests
      // would each trigger a new sandbox download.
      disableRange: true,
      disableStream: true,
    }),
    [],
  );

  return (
    <div className="pdf-viewer" ref={scrollRef}>
      <Document
        file={url}
        onLoadSuccess={onLoadSuccess}
        onLoadError={onLoadError}
        options={options}
        loading={
          <div className="file-preview-loading">
            <Loader2 size={24} className="file-preview-spinner" />
          </div>
        }
        error={
          <div className="file-preview-unsupported">Failed to load PDF.</div>
        }
      >
        <div className="document-pages pdf-viewer-pages" ref={pagesRef}>
          {width > 0 &&
            pageDims.map((dim, i) => (
              <PdfPage
                key={i + 1}
                pageNum={i + 1}
                totalPages={pageDims.length}
                width={width}
                aspectRatio={`${dim.w} / ${dim.h}`}
              />
            ))}
        </div>
      </Document>
    </div>
  );
}

export default PdfViewer;
