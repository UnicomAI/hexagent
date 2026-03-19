/**
 * Word document viewer built on docx-preview.
 *
 * Lazy-loaded via React.lazy() — docx-preview is only fetched
 * when a user actually opens a .docx file.
 *
 * Layout mirrors PdfViewer exactly:
 *   .docx-viewer      → scroll container   (= .pdf-viewer)
 *   .document-pages   → flex column + pad  (shared with PdfViewer)
 *     .document-page  → width:100% + shadow (shared with PdfViewer)
 *       section        → transform:scale()   (= canvas width:100%)
 *
 * Each page section renders at its native document size (in CSS pt).
 * It sits inside a .document-page card that is width:100%. A CSS transform
 * scales the section to fill the card — text layout never reflows.
 */

import { useState, useEffect, useLayoutEffect, useRef } from "react";
import { renderAsync } from "docx-preview";
import { Loader2 } from "lucide-react";

interface Props {
  url: string;
  visible: boolean;
}

function DocxViewer({ url, visible }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  const styleRef = useRef<HTMLDivElement>(null);
  const wasVisible = useRef(visible);

  // Reset scroll on panel reopen
  if (visible && !wasVisible.current && scrollRef.current) {
    scrollRef.current.scrollTop = 0;
  }
  wasVisible.current = visible;

  // Fetch & render at native page dimensions.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch");
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled || !pagesRef.current) return;
        return renderAsync(buffer, pagesRef.current, styleRef.current ?? undefined, {
          className: "docx-page",
          inWrapper: false,
          ignoreWidth: false,
          ignoreHeight: false,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
          breakPages: true,
        });
      })
      .then(() => {
        if (!cancelled) setLoading(false);
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

  // After render: wrap each section in a .document-page card
  // and scale sections to fill the card via transform.
  // useLayoutEffect so scaling happens before browser paint.
  useLayoutEffect(() => {
    const container = pagesRef.current;
    if (loading || !container || !scrollRef.current) return;

    const sections = Array.from(
      container.querySelectorAll(":scope > section.docx-page"),
    ) as HTMLElement[];
    if (sections.length === 0) return;

    // Measure native pixel dimensions BEFORE wrapping in cards.
    // The library sets inline widths in pt (e.g. "612pt" for US Letter),
    // so we must use offsetWidth/offsetHeight which return actual pixels.
    const nativeWidth = sections[0].offsetWidth;
    const nativeHeights = sections.map((s) => s.offsetHeight);

    // Wrap each section in a card div (like .pdf-page wraps canvas)
    const cards: HTMLDivElement[] = [];
    sections.forEach((section) => {
      const card = document.createElement("div");
      card.className = "document-page";
      section.parentNode!.insertBefore(card, section);
      card.appendChild(section);
      cards.push(card);
    });

    const scrollEl = scrollRef.current!;

    const updateScale = () => {
      cards.forEach((card, i) => {
        const cardWidth = card.clientWidth;
        if (cardWidth <= 0 || nativeWidth <= 0) return;
        const scale = cardWidth / nativeWidth;
        const section = card.firstElementChild as HTMLElement;
        section.style.transform = `scale(${scale})`;
        section.style.transformOrigin = "top left";
        card.style.height = `${nativeHeights[i] * scale}px`;
      });
    };

    const ro = new ResizeObserver(updateScale);
    ro.observe(scrollEl);
    updateScale();

    return () => {
      ro.disconnect();
      // Unwrap sections on cleanup (e.g. URL change)
      cards.forEach((card) => {
        const section = card.firstElementChild;
        if (section && card.parentNode) {
          card.parentNode.insertBefore(section, card);
          card.remove();
        }
      });
    };
  }, [loading]);

  if (error) {
    return (
      <div className="file-preview-unsupported">
        <p>Failed to load document.</p>
      </div>
    );
  }

  return (
    <div className="docx-viewer" ref={scrollRef}>
      <div ref={styleRef} style={{ display: "none" }} />
      {loading && (
        <div className="file-preview-loading">
          <Loader2 size={24} className="file-preview-spinner" />
        </div>
      )}
      <div
        className="document-pages"
        ref={pagesRef}
        style={loading ? { visibility: "hidden", position: "absolute" } : undefined}
      />
    </div>
  );
}

export default DocxViewer;
