// Thin client for the Studio's JSON + SSE API (spec §3, §5).
// Every non-2xx response becomes an ApiError carrying the server's `detail`.

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : `request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function raiseFor(res) {
  let detail = res.statusText || "request failed";
  try {
    const body = await res.json();
    if (body && body.detail !== undefined) detail = body.detail;
  } catch { /* not JSON: keep the status text */ }
  throw new ApiError(res.status, detail);
}

async function request(path, options = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...options });
  if (!res.ok) await raiseFor(res);
  return res.json();
}

function postJson(body) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  };
}

export const getPatterns = () => request("/api/patterns");
export const getPattern = (id) => request(`/api/patterns/${encodeURIComponent(id)}`);
export const getSession = () => request("/api/session");
export const createThread = (patternId) =>
  request(`/api/patterns/${encodeURIComponent(patternId)}/threads`, postJson({}));
export const getState = (threadId) =>
  request(`/api/threads/${encodeURIComponent(threadId)}/state`);

// The catalog menu (Catalog spec §5.2): all categories, and one page by route.
export const getCatalog = () => request("/api/catalog");
export const getCatalogPage = (route) =>
  request(`/api/catalog/${route.split("/").map(encodeURIComponent).join("/")}`);

// Parse one SSE frame ("data: <json>" lines); returns null for frames with no data.
function parseFrame(frame) {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  return data ? JSON.parse(data) : null;
}

// Start a run and yield each trace event as it arrives.
export async function* streamRun(threadId, text, { signal } = {}) {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}/runs`, {
    ...postJson({ text }),
    credentials: "same-origin",
    signal,
  });
  if (!res.ok) await raiseFor(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop();  // last piece may be incomplete
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) yield event;
      }
      if (done) break;
    }
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    // Stopping early (consumer broke out, or an error) hangs up on the server,
    // which frees the session's run slot; after a clean end this is a no-op.
    await reader.cancel().catch(() => {});
  }
}
