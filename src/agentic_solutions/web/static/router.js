// Hash routes for the Studio (Catalog spec §4.1). Pure functions only: no DOM
// or browser globals, so Node's test runner can import this module directly.
//
//   ""  "#"  "#/"              -> {view: "home"}
//   "#/governance/approval"    -> {view: "pattern", route: "governance/approval"}
//   "#guardrail" (an M1 link)  -> {view: "legacy", route: "governance/guardrails"}
//   anything else              -> {view: "unknown"}
//
// A well-formed route the catalog doesn't know (#/a/b) still parses as a
// pattern; the app learns it is unknown when the page API answers 404.

// Milestone 1's `#<patternId>` links and where each one lives now.
export const LEGACY = Object.freeze({
  qa: "collaboration/single-agent",
  chat_loop: "memory/session",
  guardrail: "governance/guardrails",
  human_in_loop: "governance/approval",
});

const ROUTE = /^[a-z0-9-]+\/[a-z0-9-]+$/;  // <category>/<pattern> ids (Catalog spec §3.2)

export function parseHash(hash) {
  let path;
  try {
    path = decodeURIComponent(String(hash ?? "").replace(/^#/, ""));
  } catch {
    return { view: "unknown" };  // malformed escape such as #%E0
  }
  if (path === "" || path === "/") return { view: "home" };
  if (path.startsWith("/")) {
    const route = path.slice(1);
    return ROUTE.test(route) ? { view: "pattern", route } : { view: "unknown" };
  }
  // Own keys only, so "#constructor" isn't mistaken for a legacy id.
  if (Object.hasOwn(LEGACY, path)) return { view: "legacy", route: LEGACY[path] };
  return { view: "unknown" };
}

// The hash for a route; no route (or "") is the catalog home.
export function formatHash(route) {
  return route ? `#/${route}` : "#/";
}
