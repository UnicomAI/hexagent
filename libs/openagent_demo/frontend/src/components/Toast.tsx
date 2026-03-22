import { useState, useEffect, useRef, useCallback } from "react";
import type { Notification } from "../store";

interface ToastProps {
  notifications: Notification[];
  onDismiss: (id: string) => void;
}

export default function Toast({ notifications, onDismiss }: ToastProps) {
  if (notifications.length === 0) return null;

  return (
    <div className="toast-container">
      {notifications.map((n) => (
        <ToastItem key={n.id} notification={n} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

const SLIDE_OUT_MS = 250;

function ToastItem({
  notification,
  onDismiss,
}: {
  notification: Notification;
  onDismiss: (id: string) => void;
}) {
  const [exiting, setExiting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const duration = notification.type === "error" ? 8000 : 4000;

  // Stable refs so the timer callback never goes stale
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  const dismiss = useCallback(() => {
    setExiting(true);
    setTimeout(() => onDismissRef.current(notification.id), SLIDE_OUT_MS);
  }, [notification.id]);

  const startTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(dismiss, duration);
  }, [dismiss, duration]);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Start timer once on mount — stable deps prevent restarts
  useEffect(() => {
    startTimer();
    return clearTimer;
  }, [startTimer, clearTimer]);

  const handleMouseEnter = useCallback(() => {
    clearTimer();
  }, [clearTimer]);

  const handleMouseLeave = useCallback(() => {
    startTimer();
  }, [startTimer]);

  return (
    <div
      className={`toast toast-${notification.type} ${exiting ? "toast-exit" : ""}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <span className="toast-message">{notification.message}</span>
      <button className="toast-close" onClick={dismiss}>
        &times;
      </button>
    </div>
  );
}
