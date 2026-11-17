import { useEffect, useState } from "react";
import { getSession, type Session } from "../api";

export interface SessionFormProps {
  sessionId: string;
  session: Session;
  onUpdate: (session: Session, checking?: boolean, error?: string) => void;
}

/** Keep countdowns current and reload the result when the checkout expires. */
export function useSessionExpiry({ sessionId, session, onUpdate }: SessionFormProps) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (Date.parse(session.expires_at) <= now) {
      getSession(sessionId).then((next) => onUpdate(next)).catch(() => undefined);
    }
  }, [now, session.expires_at, sessionId, onUpdate]);
  return now;
}
