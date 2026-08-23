"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface LogEntry {
  time: string;
  level: string;
  name: string;
  function: string;
  line: number;
  message: string;
}

const MAX_ENTRIES = 500;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

export function useLogStream() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const pausedRef = useRef(false);
  const retryMsRef = useRef(RECONNECT_BASE_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openRef = useRef<() => void>(() => {});

  const clear = useCallback(() => {
    setLogs([]);
  }, []);

  const reconnect = useCallback(() => {
    setConnected(false);
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    // Drop reconnect state and reconnect immediately.
    retryMsRef.current = RECONNECT_BASE_MS;
    openRef.current();
  }, []);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    let active = true;

    const open = () => {
      if (!active) return;
      const es = new EventSource("/api/logs/stream");
      esRef.current = es;

      es.onopen = () => {
        if (!active) return;
        setConnected(true);
        retryMsRef.current = RECONNECT_BASE_MS;
      };

      es.onmessage = (event) => {
        if (!active || pausedRef.current) return;
        try {
          const entry = JSON.parse(event.data) as LogEntry;
          setLogs((prev) => {
            const next = [...prev, entry];
            return next.length > MAX_ENTRIES ? next.slice(-MAX_ENTRIES) : next;
          });
        } catch {
          // Ignore malformed frames.
        }
      };

      es.onerror = () => {
        if (!active) return;
        setConnected(false);
        if (esRef.current === es) {
          es.close();
          esRef.current = null;
        }
        // EventSource auto-reconnects, but driving it deterministically here
        // avoids silent gaps and lets us back off.
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(open, retryMsRef.current);
        retryMsRef.current = Math.min(retryMsRef.current * 2, RECONNECT_MAX_MS);
      };
    };

    openRef.current = open;
    open();

    return () => {
      active = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  return { logs, connected, paused, setPaused, clear, reconnect };
}
