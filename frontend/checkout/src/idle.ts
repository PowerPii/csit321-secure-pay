// Idle sign-out with a warning (FR-ACC-10): warn after `warnMinutes` without activity, sign
// out at `endMinutes`. Activity (pointer, keys, scroll, touch) resets the clock and, at most
// once a minute, keeps the server session alive too, so the server's idle limit and this one
// move together. While the warning shows, only "Stay signed in" resets it.
// The same file is in frontend/dashboard/src/idle.ts.
import { useCallback, useEffect, useRef, useState } from "react";

const EVENTS = ["pointerdown", "keydown", "scroll", "touchstart"] as const;
const PING_EVERY_MS = 60_000;

export interface IdleOptions {
  enabled: boolean;
  warnMinutes: number;
  endMinutes: number;
  keepAlive: () => void;
  onEnd: () => void;
}

export function useIdleSignOut({ enabled, warnMinutes, endMinutes, keepAlive, onEnd }: IdleOptions) {
  const warnMs = warnMinutes * 60_000;
  const endMs = endMinutes * 60_000;
  const last = useRef(Date.now());
  const lastPing = useRef(Date.now());
  const ended = useRef(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!enabled) return;
    last.current = lastPing.current = Date.now();
    ended.current = false;
    const onActivity = () => {
      const t = Date.now();
      if (t - last.current >= warnMs) return; // the warning is showing
      last.current = t;
      if (t - lastPing.current >= PING_EVERY_MS) {
        lastPing.current = t;
        keepAlive();
      }
    };
    EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      EVENTS.forEach((e) => window.removeEventListener(e, onActivity));
      window.clearInterval(timer);
    };
  }, [enabled, warnMs, keepAlive]);

  const idle = now - last.current;
  useEffect(() => {
    if (enabled && idle >= endMs && !ended.current) {
      ended.current = true;
      onEnd();
    }
  }, [enabled, idle, endMs, onEnd]);

  const stay = useCallback(() => {
    last.current = lastPing.current = Date.now();
    keepAlive();
    setNow(Date.now());
  }, [keepAlive]);

  return {
    warning: enabled && idle >= warnMs && idle < endMs,
    secondsLeft: Math.max(0, Math.ceil((endMs - idle) / 1000)),
    stay,
  };
}

/** 95 -> "1:35" */
export function minSec(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
