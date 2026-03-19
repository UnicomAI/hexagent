import { useEffect, useRef, useCallback } from "react";
import { useAppContext } from "../store";
import MessageBubble from "./MessageBubble";
import type { Conversation } from "../types";

interface MessageListProps {
  conversation: Conversation | null;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Walk offsetTop up the offsetParent chain until we reach `ancestor`.
 * Unlike getBoundingClientRect(), offsetTop is NOT affected by CSS transforms
 * (e.g. translateY from animations), giving us stable layout positions.
 */
function getOffsetTopTo(el: HTMLElement, ancestor: HTMLElement): number {
  let offset = 0;
  let current: HTMLElement | null = el;
  while (current && current !== ancestor) {
    offset += current.offsetTop;
    current = current.offsetParent as HTMLElement | null;
  }
  return offset;
}

export default function MessageList({ conversation, scrollContainerRef }: MessageListProps) {
  const { state } = useAppContext();
  const firstUserMsgRef = useRef<HTMLDivElement>(null);
  const lastUserMsgRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const spacerDivRef = useRef<HTMLDivElement>(null);
  const prevMsgCountRef = useRef(0);

  const messages = conversation?.messages ?? [];

  const updateSpacer = useCallback(() => {
    const container = scrollContainerRef.current;
    const firstEl = firstUserMsgRef.current;
    const lastEl = lastUserMsgRef.current;
    const spacerDiv = spacerDivRef.current;
    if (!container || !firstEl || !lastEl || !spacerDiv) {
      if (spacerDiv) spacerDiv.style.height = "0px";
      return;
    }

    const clientH = container.clientHeight;
    const currentSpacerH = parseFloat(spacerDiv.style.height) || 0;
    const scrollHWithoutSpacer = container.scrollHeight - currentSpacerH;

    const firstUserAbsTop = getOffsetTopTo(firstEl, container);
    const lastUserAbsTop = getOffsetTopTo(lastEl, container);

    // We want: when scrolled to last user msg, it sits at the same position as the first.
    // Target scrollTop = lastUserAbsTop - firstUserAbsTop
    // For that to work: scrollHeight - clientHeight >= lastUserAbsTop - firstUserAbsTop
    // => spacer = max(0, clientH + (lastUserAbsTop - firstUserAbsTop) - scrollHWithoutSpacer + 1)
    const needed = Math.ceil(Math.max(0, clientH + (lastUserAbsTop - firstUserAbsTop) - scrollHWithoutSpacer + 1));
    if (Math.abs(needed - currentSpacerH) >= 1) {
      spacerDiv.style.height = needed + "px";
    }
  }, [scrollContainerRef]);

  // When a new user message appears, update spacer then scroll
  useEffect(() => {
    const prevCount = prevMsgCountRef.current;
    prevMsgCountRef.current = messages.length;

    if (messages.length <= prevCount) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "user") {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          updateSpacer();
          const container = scrollContainerRef.current;
          const firstEl = firstUserMsgRef.current;
          const lastEl = lastUserMsgRef.current;
          if (!container || !firstEl || !lastEl) return;
          const targetScroll = getOffsetTopTo(lastEl, container) - getOffsetTopTo(firstEl, container);
          container.scrollTo({ top: targetScroll, behavior: "smooth" });
        });
      });
    }
  }, [messages.length, messages, updateSpacer, scrollContainerRef]);

  // Recalculate spacer as streaming content grows
  useEffect(() => {
    updateSpacer();
  }, [state.streamingBlocks, state.isStreaming, updateSpacer]);

  // ResizeObserver on content area (streaming growth, markdown rendering, etc.)
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => updateSpacer());
    observer.observe(el);
    return () => observer.disconnect();
  }, [messages.length, updateSpacer]);

  // ResizeObserver on scroll container (window resize changes clientHeight)
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => updateSpacer());
    observer.observe(container);
    return () => observer.disconnect();
  }, [scrollContainerRef, updateSpacer]);

  if (!conversation) return null;

  let firstUserIdx = -1;
  let lastUserIdx = -1;
  let lastAssistantIdx = -1;
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role === "user" && firstUserIdx === -1) firstUserIdx = i;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user" && lastUserIdx === -1) lastUserIdx = i;
    if (messages[i].role === "assistant" && lastAssistantIdx === -1) lastAssistantIdx = i;
    if (lastUserIdx !== -1 && lastAssistantIdx !== -1) break;
  }

  return (
    <div className="message-list" ref={contentRef}>
      {messages.map((msg, i) => {
        const isStreamingMsg = state.isStreaming && msg.id === state.streamingMessageId;
        const ref =
          i === firstUserIdx && i === lastUserIdx
            ? (node: HTMLDivElement | null) => {
                (firstUserMsgRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
                (lastUserMsgRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
              }
            : i === firstUserIdx
              ? firstUserMsgRef
              : i === lastUserIdx
                ? lastUserMsgRef
                : undefined;
        return (
          <MessageBubble
            key={msg.id}
            ref={ref}
            message={msg}
            isLastAssistant={!state.isStreaming && i === lastAssistantIdx}
            streamingBlocks={isStreamingMsg ? state.streamingBlocks : undefined}
            isStreaming={isStreamingMsg}
          />
        );
      })}

      <div ref={spacerDivRef} style={{ height: 0 }} aria-hidden="true" />
    </div>
  );
}
