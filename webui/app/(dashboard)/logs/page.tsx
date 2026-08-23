"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollText, Pause, Play, Trash2, RefreshCw, Search, AlertTriangle, XCircle } from "lucide-react";
import { useLogStream } from "@/hooks/use-logs";
import { cn } from "@/lib/utils";

type LevelFilter = "all" | "WARNING" | "ERROR";

const LEVEL_STYLES: Record<string, string> = {
  ERROR: "text-red-600",
  CRITICAL: "text-red-700 font-semibold",
  WARNING: "text-amber-600",
};

export default function LogsPage() {
  const { logs, connected, paused, setPaused, clear, reconnect } = useLogStream();
  const [level, setLevel] = useState<LevelFilter>("all");
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return logs.filter((entry) => {
      if (level !== "all" && entry.level !== level) return false;
      if (needle) {
        const haystack = `${entry.message} ${entry.name} ${entry.function}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [logs, level, search]);

  // Auto-scroll to bottom only when the user hasn't scrolled up.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && autoScroll) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered, autoScroll]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }

  function togglePause() {
    setPaused(!paused);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-on-surface flex items-center gap-2">
            <ScrollText className="w-5 h-5 text-primary" />
            System Logs
          </h2>
          <p className="text-sm text-on-surface-variant mt-1">
            Live WARNING / ERROR stream from the gateway. Admin only.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border",
              connected ? "text-emerald-700 bg-emerald-50 border-emerald-200" : "text-red-700 bg-red-50 border-red-200"
            )}
          >
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                connected ? "bg-emerald-500 animate-pulse" : "bg-red-500"
              )}
            />
            {connected ? "Connected" : "Disconnected"}
          </span>
          <button
            onClick={togglePause}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-outline-variant/50 bg-white/60 text-on-surface hover:bg-white/90 transition-colors"
          >
            {paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            {paused ? "Resume" : "Pause"}
          </button>
          <button
            onClick={reconnect}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-outline-variant/50 bg-white/60 text-on-surface hover:bg-white/90 transition-colors"
            title="Reconnect"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reconnect
          </button>
          <button
            onClick={clear}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-outline-variant/50 bg-white/60 text-on-surface hover:bg-red-50 hover:text-red-700 hover:border-red-200 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 bg-white/70 border border-outline-variant/40 rounded-full p-1">
          {(["all", "WARNING", "ERROR"] as LevelFilter[]).map((lv) => (
            <button
              key={lv}
              onClick={() => setLevel(lv)}
              className={cn(
                "px-3 py-1.5 rounded-full text-xs font-medium transition-colors capitalize",
                level === lv
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              )}
            >
              {lv}
            </button>
          ))}
        </div>

        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/60" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search message, module, function..."
            className="w-full pl-9 pr-4 py-2 bg-white/70 border border-outline-variant/40 rounded-full text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container/50 focus:bg-white/90 transition-all"
          />
        </div>

        <span className="text-xs text-on-surface-variant ml-auto">
          {filtered.length} / {logs.length} entries
        </span>
      </div>

      {/* Log stream */}
      <div className="glass-panel rounded-3xl overflow-hidden">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-[60vh] overflow-y-auto bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl font-mono text-xs"
        >
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-on-surface-variant gap-2 p-8">
              <AlertTriangle className="w-8 h-8 text-on-surface-variant/30" />
              <p className="text-sm">
                {logs.length === 0 ? "No WARNING/ERROR logs captured yet. Waiting for events..." : "No entries match the current filters."}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-outline-variant/10">
              {filtered.map((entry, idx) => (
                <div key={idx} className="flex items-start gap-3 px-4 py-2 hover:bg-surface-container-lowest/40 transition-colors">
                  <span className={cn("shrink-0 font-semibold w-16", LEVEL_STYLES[entry.level] || "text-on-surface")}>
                    {entry.level}
                  </span>
                  <span className="shrink-0 text-on-surface-variant/70 tabular-nums w-[185px]">
                    {formatTime(entry.time)}
                  </span>
                  <span className="shrink-0 text-on-surface-variant/80 w-[260px] truncate">
                    {entry.name}
                    <span className="text-on-surface-variant/50">:{entry.function}:{entry.line}</span>
                  </span>
                  <span className="flex-1 break-words whitespace-pre-wrap text-on-surface min-w-0">
                    {entry.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between px-4 py-2 border-t border-outline-variant/20 bg-white/60 text-xs text-on-surface-variant">
          <span>
            {paused ? "Paused — live stream suspended." : "Streaming live..."}
          </span>
          <span className="inline-flex items-center gap-1">
            <XCircle className="w-3.5 h-3.5 text-on-surface-variant/50" />
            Auto-scroll {autoScroll ? "on" : "off"}
          </span>
        </div>
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
