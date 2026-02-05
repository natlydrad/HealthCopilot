/**
 * In-memory flow log for live action/decision tracing.
 * Any module (e.g. api.js) can call flowLog.add(); FlowLogPanel subscribes and renders.
 */

const MAX_ENTRIES = 200;
let entries = [];
let nextId = 1;
const subscribers = new Set();

function notify() {
  subscribers.forEach((cb) => cb());
}

/**
 * @param {{ type?: string, message: string, source?: string, detail?: object }} opts
 */
export function add(opts) {
  const { type = "event", message, source, detail } = opts;
  const id = nextId++;
  const ts = new Date();
  entries.push({ id, ts, type, message, source: source ?? "frontend", detail });
  if (entries.length > MAX_ENTRIES) {
    entries = entries.slice(-MAX_ENTRIES);
  }
  notify();
}

/**
 * @param {() => void} callback - invoked when entries change
 * @returns {() => void} unsubscribe
 */
export function subscribe(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}

/**
 * @returns {Array<{ id: number, ts: Date, type: string, message: string, source: string, detail?: object }>}
 */
export function getEntries() {
  return [...entries];
}

export function clear() {
  entries = [];
  notify();
}
