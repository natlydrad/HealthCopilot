import { useState, useEffect, useRef } from "react";
import * as flowLog from "./utils/flowLog";

function formatTime(ts) {
  if (!(ts instanceof Date)) ts = new Date(ts);
  return ts.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function FlowLogPanel() {
  const [expanded, setExpanded] = useState(false);
  const [entries, setEntries] = useState(() => flowLog.getEntries());
  const listRef = useRef(null);

  useEffect(() => {
    const unsub = flowLog.subscribe(() => setEntries(flowLog.getEntries()));
    return unsub;
  }, []);

  useEffect(() => {
    if (expanded && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [entries, expanded]);

  const handleCopy = async () => {
    const text = entries
      .map((e) => `[${formatTime(e.ts)}] ${e.source} | ${e.message}${e.detail && Object.keys(e.detail).length ? " " + JSON.stringify(e.detail) : ""}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {}
  };

  return (
    <div className="fixed top-0 right-0 z-50 flex h-full" style={{ fontFamily: "ui-monospace, monospace" }}>
      {/* Tab: always visible */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center justify-center w-8 h-24 mt-24 rounded-l-lg shadow-md bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium border border-r-0 border-slate-600"
        title={expanded ? "Hide flow log" : "Show flow log"}
      >
        <span className="-rotate-90 whitespace-nowrap">Flow</span>
      </button>

      {/* Panel: collapsible */}
      {expanded && (
        <div
          className="w-80 max-w-[90vw] h-full flex flex-col bg-slate-800/95 border-l border-slate-600 shadow-xl"
          style={{ userSelect: "text" }}
        >
          <div className="flex items-center justify-between gap-2 p-2 border-b border-slate-600 shrink-0">
            <span className="text-sm font-semibold text-slate-200">Flow log</span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={flowLog.clear}
                className="px-2 py-1 text-xs rounded bg-slate-600 hover:bg-slate-500 text-slate-200"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={handleCopy}
                className="px-2 py-1 text-xs rounded bg-slate-600 hover:bg-slate-500 text-slate-200"
              >
                Copy log
              </button>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="px-2 py-1 text-xs rounded bg-slate-600 hover:bg-slate-500 text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
          <div
            ref={listRef}
            className="flex-1 overflow-y-auto p-2 text-xs text-slate-300 space-y-1"
          >
            {entries.length === 0 && (
              <p className="text-slate-500 italic">No entries yet. Parse a meal or load data to see the flow.</p>
            )}
            {entries.map((e) => (
              <div
                key={e.id}
                className="rounded px-2 py-1 bg-slate-700/50 border border-slate-600/50 break-words"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-slate-400 shrink-0">{formatTime(e.ts)}</span>
                  <span
                    className={`shrink-0 px-1 rounded text-[10px] ${
                      e.source === "parse-api" ? "bg-amber-900/60 text-amber-200" : "bg-slate-600 text-slate-300"
                    }`}
                  >
                    {e.source}
                  </span>
                </div>
                <div className="mt-0.5 text-slate-200">{e.message}</div>
                {e.detail && Object.keys(e.detail).length > 0 && (
                  <pre className="mt-1 text-[10px] text-slate-400 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(e.detail)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
