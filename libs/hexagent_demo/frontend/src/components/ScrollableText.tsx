import { useRef, useCallback } from "react";

/**
 * Text that scrolls horizontally on hover when truncated.
 *
 * Renders as a div (overflow:hidden) wrapping a span. When the span
 * overflows, hovering triggers a translateX animation to reveal the
 * full text. Caller provides className for the outer div.
 */
export default function ScrollableText({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLSpanElement>(null);

  const onEnter = useCallback(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner) return;
    const overflow = inner.scrollWidth - outer.clientWidth;
    if (overflow > 1) {
      const duration = Math.min(Math.max(overflow / 40, 1), 4);
      inner.style.setProperty("--scroll-dist", `-${overflow}px`);
      inner.style.setProperty("--scroll-duration", `${duration}s`);
      inner.classList.add("scrolling");
    }
  }, []);

  const onLeave = useCallback(() => {
    const inner = innerRef.current;
    if (!inner) return;
    inner.classList.remove("scrolling");
  }, []);

  return (
    <div
      ref={outerRef}
      className={`scrollable-text ${className ?? ""}`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <span ref={innerRef}>{children}</span>
    </div>
  );
}
