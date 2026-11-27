// App shell: owns the app state, the views and hash routing (Catalog spec §4).
//
// The URL hash picks the view (router.js): `#/` is the catalog home and
// `#/<category>/<pattern>` a pattern page; M1's `#guardrail`-style links are
// rewritten in place. A pattern page loads its catalog page data. When the
// pattern has a live demo, the M1 workbench opens for it: its registry detail
// is loaded, the Guide rendered and a `pattern-change` event fired on
// `document`; the wiring below rebuilds the trace graph, timeline and console
// for it and runs messages through `streamRun`. Otherwise the Guide-only view
// shows.
import {
  ApiError, createThread, getCatalog, getCatalogPage, getPattern, getSession, getState, streamRun,
} from "./api.js";
import { renderGuide, renderInlineCode } from "./guide.js";
import { renderHome } from "./catalog.js";
import { createGraph } from "./graph.js";
import { createTrace } from "./trace.js";
import { createConsole } from "./console.js";
import { formatHash, parseHash } from "./router.js";

const NOT_FOUND_TEXT = "That pattern wasn't found";
const HOME = "home";  // requestedRoute while the catalog home is showing

export const state = { pattern: null, threadId: null, session: null };

const $ = (id) => document.getElementById(id);
let loadToken = 0;  // ignores late responses after a quicker route change
let requestedRoute = null;  // the route last asked for (state.pattern lags until its fetch lands)
let routed = false;  // after the first view, each route change moves focus to its heading

function announce(text) {
  $("announcer").textContent = text;
}

// Show one view ("home" or "pattern"); `bench` picks the workbench over the
// Guide-only view inside the pattern page.
function showView(view, { bench = false } = {}) {
  $("home").hidden = view !== "home";
  $("pattern-view").hidden = view !== "pattern";
  $("bench").hidden = !(view === "pattern" && bench);
  $("guide-only").hidden = !(view === "pattern" && !bench);
  updateSkipLink();
}

// The skip link (first tab stop) jumps to the current view's main content:
// the console input on a live page, else the view heading. It is handled here
// so the hash never changes: `#console` would otherwise route as unknown.
function skipToContent(event) {
  event.preventDefault();
  if ($("pattern-view").hidden) $("home-title").focus();
  else if ($("bench").hidden) $("page-title").focus();
  else $("console-text").focus();
}

function updateSkipLink() {
  const live = !$("bench").hidden && !$("pattern-view").hidden;
  $("skip-link").textContent = live ? "Skip to the agent console" : "Skip to the main content";
}

// Move focus to the new view's heading (Catalog spec §4.4); not on first load.
function focusHeading(id) {
  if (routed) $(id).focus();
  routed = true;
}

function setNotice(text) {
  const el = $("home-notice");
  el.textContent = text ?? "";
  el.hidden = !text;
}

// ---------- Catalog home ----------

let catalog = null;  // GET /api/catalog, fetched once
let names = new Map();  // route -> pattern name, from the catalog listing
let pendingCategory = null;  // the breadcrumb's category link: focus its card on arrival

async function loadCatalog() {
  if (!catalog) {
    catalog = await getCatalog();
    names = new Map(catalog.categories.flatMap((c) => c.patterns.map((p) => [p.route, p.name])));
  }
  return catalog;
}

// Guide links and breadcrumbs name patterns as the catalog does (null: unknown).
const nameFor = (route) => names.get(route) ?? null;

async function showHome({ notice = null } = {}) {
  const token = ++loadToken;
  requestedRoute = HOME;
  leavePattern();
  showView("home");
  setNotice(notice);
  renderCrumbs(null);
  document.title = "Catalog · Agentic Patterns Studio";
  const category = pendingCategory;
  pendingCategory = null;
  if (!category) focusHeading("home-title");
  announce(notice ?? "Opened Catalog");
  try {
    await loadCatalog();
  } catch (err) {
    if (token !== loadToken) return;
    requestedRoute = null;  // let the next hash change retry
    setNotice(`Could not load the catalog: ${err.message}. Reload the page to try again.`);
    return;
  }
  if (token !== loadToken) return;
  const home = renderHome($("home-body"), catalog, {
    onOpen: (route) => { location.hash = formatHash(route); },
  });
  if (category) {
    home.focusCategory(category);
    routed = true;
  }
}

// ---------- Pattern page ----------

async function selectRoute(route) {
  const token = ++loadToken;
  requestedRoute = route;
  leavePattern();  // a stream from the page being left stops now, not when the fetch lands
  try {
    // The listing names the breadcrumb and Guide links; a page still opens without it.
    const [page] = await Promise.all([getCatalogPage(route), loadCatalog().catch(() => null)]);
    if (token !== loadToken) return;
    const detail = page.demo ? await getPattern(page.demo) : null;
    if (token !== loadToken) return;
    renderPageChrome(page);
    if (detail) openLivePage(page, detail);
    else showGuideOnly(page);
    focusHeading("page-title");
    announce(`Opened ${nameFor(page.route) ?? page.name}`);
  } catch (err) {
    if (token !== loadToken) return;
    if (err instanceof ApiError && err.status === 404) return notFound();
    showHome({ notice: `Could not load this pattern: ${err.message}. Reload the page to try again.` });
    requestedRoute = null;  // so a hash change back to this route retries it
  }
}

// Catalog › {Category} › {Pattern} (Catalog spec §4.3, §4.4). `page` null
// (the home) leaves the breadcrumb empty. The last crumb is the REQUESTED
// entry, so a cross-list reads "Execution › Tool Use" over ReAct's content.
function renderCrumbs(page) {
  const nav = $("breadcrumbs");
  $("stepper").hidden = !page;
  if (!page) return nav.replaceChildren();
  const list = document.createElement("ol");
  const crumb = (text, href, extra) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = href;
    a.textContent = text;
    extra?.(a);
    li.append(a);
    list.append(li);
  };
  crumb("Catalog", formatHash());
  crumb(page.category.name, formatHash(), (a) => {
    a.addEventListener("click", (e) => {
      // A modifier or middle click opens a new tab: this view is not leaving.
      if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      pendingCategory = page.category.id;
    });
  });
  crumb(nameFor(page.route) ?? page.name, formatHash(page.route), (a) => a.setAttribute("aria-current", "page"));
  nav.replaceChildren(list);

  for (const [id, route, word] of [["step-prev", page.prev, "Previous"], ["step-next", page.next, "Next"]]) {
    const a = $(id);
    a.href = formatHash(route);
    const label = `${word} in ${page.category.name}: ${nameFor(route) ?? route}`;
    a.setAttribute("aria-label", label);
    a.title = label;
  }
}

// The heading, breadcrumb and title every pattern page shares (Catalog spec
// §4.3). The heading is the content's own name (ReAct, for Tool Use); a
// cross-list says so underneath.
function renderPageChrome(page) {
  const listed = nameFor(page.route) ?? page.name;
  $("page-title").textContent = page.name;
  const note = $("page-note");
  note.hidden = page.target === page.route;
  note.textContent = note.hidden ? "" : `${listed} is listed under ${page.category.name}; it opens the ${page.name} page.`;
  renderCrumbs(page);
  document.title = `${listed} · ${page.category.name} · Agentic Patterns Studio`;
}

// A live demo: the M1 workbench, unchanged, for the registry pattern `demo`.
function openLivePage(page, detail) {
  showView("pattern", { bench: true });
  state.pattern = detail;
  state.threadId = null;
  renderPatternChrome(detail);
  renderGuide($("guide-body"), page.explanation_md, { linkFor: nameFor });
  document.dispatchEvent(new CustomEvent("pattern-change", { detail: { pattern: detail } }));
}

// A pattern with no demo yet (Catalog spec §4.3): the banner, its skeleton as
// a static diagram, and the Guide. No thread and no run (Review Focus 5).
let staticGraph = null;
function showGuideOnly(page) {
  showView("pattern");
  state.pattern = null;
  state.threadId = null;
  staticGraph = createGraph($("guide-only-graph"), page.topology, { static: true });
  renderGuide($("guide-only-body"), page.explanation_md, { linkFor: nameFor });
}

// Leaving any pattern page: stop a live bench, drop a static diagram.
function leavePattern() {
  leaveBench();
  staticGraph?.destroy();
  staticGraph = null;
}

// Plain ←/→ step through the breadcrumb's category (Catalog spec §4.3), but
// never while typing, and never with a modifier: Alt+←/→ are Back/Forward.
function stepWithArrows(e) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.defaultPrevented) return;
  if ($("pattern-view").hidden || $("stepper").hidden) return;
  const t = e.target;
  if (t instanceof Element && t.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])")) return;
  e.preventDefault();
  location.hash = $(e.key === "ArrowLeft" ? "step-prev" : "step-next").getAttribute("href");
}

function notFound() {
  history.replaceState(null, "", formatHash());
  showHome({ notice: NOT_FOUND_TEXT });
}

function renderPatternChrome(detail) {
  const heading = $("trace-pattern");
  heading.replaceChildren();
  renderInlineCode(heading, detail.title);  // the registry title, as the subtitle
  $("console-summary").textContent = detail.summary;
  $("console").dataset.mode = detail.mode;  // "chat" or "trigger"
  $("console-send").textContent = detail.mode === "chat" ? "Send" : "Run";
}

function renderSession(session) {
  const badge = $("mode-badge");
  badge.dataset.mode = session.mode;
  badge.querySelector(".mode-text").textContent =
    session.mode === "offline" ? "Offline (scripted)" : "Live";
  if (session.max_input_chars) $("console-text").maxLength = session.max_input_chars;  // the server's limit
}

// Show whatever the hash names. A legacy M1 link is rewritten in place
// (replaceState: no extra history entry); its remembered thread is keyed by
// the registry id, so it still restores on the new route.
function route() {
  const where = parseHash(location.hash);
  if (where.view === "legacy") {
    history.replaceState(null, "", formatHash(where.route));
    where.view = "pattern";
  }
  if (where.view === "unknown") return notFound();
  const key = where.view === "home" ? HOME : where.route;
  if (requestedRoute === key) return;  // already showing (or loading) it
  if (where.view === "home") showHome();
  else selectRoute(where.route);
}

async function start() {
  $("skip-link").addEventListener("click", skipToContent);
  document.addEventListener("keydown", stepWithArrows);
  try {
    state.session = await getSession();
  } catch (err) {
    showView("home");
    setNotice(`Could not reach the Studio server: ${err.message}. Reload the page to try again.`);
    return;
  }
  renderSession(state.session);
  window.addEventListener("hashchange", route);
  route();
}

// ---------- Trace + console wiring (spec §5, §6) ----------
//
// One "bench" per selected pattern: its graph, trace and console. `benchToken`
// plays the same role as `loadToken` above: every await re-checks it, so a
// late response for a pattern the user has already left is dropped.
//
// `chatGen` does the same for one conversation inside a bench: opening a
// pattern and New chat/Clear bump it, so a send still in flight from the old
// conversation stops at its next await instead of writing into the new one.

const STARTED_NEW = "Started a new chat";
const ENDED_TEXT = "This conversation has ended. Start a New chat.";
let bench = null;
let benchToken = 0;
let chatGen = 0;

const live = (b, gen) => b.token === benchToken && gen === chatGen;

const threadKey = (patternId) => `studio.thread.${patternId}`;
function rememberThread(patternId, threadId) {
  try {
    if (threadId) sessionStorage.setItem(threadKey(patternId), threadId);
    else sessionStorage.removeItem(threadKey(patternId));
  } catch { /* storage blocked: the chat just won't survive a reload */ }
}
function rememberedThread(patternId) {
  try {
    return sessionStorage.getItem(threadKey(patternId));
  } catch {
    return null;
  }
}

function setThread(threadId) {
  state.threadId = threadId;
  rememberThread(state.pattern.id, threadId);
}

// Route one trace event to the graph, the trace and the console.
function dispatch(b, evt) {
  const g = b.graph;
  switch (evt.type) {
    case "run_started":
      for (const n of b.pattern.topology.nodes) g.setNodeState(n.id, "idle");
      break;
    case "node_started":
      g.setNodeState(evt.node, "active");
      b.active = evt.node;
      announce(`Running ${evt.node}`);
      break;
    case "node_finished":
      g.setNodeState(evt.node, evt.update && evt.update.refusal ? "error" : "done");
      if (b.active === evt.node) b.active = null;
      break;
    case "edge":
      g.flashEdge(evt.source, evt.target);
      break;
    case "interrupt":
      g.setNodeState(evt.node, "paused");
      announce(`Paused at ${evt.node}`);
      break;
    case "error":
      if (b.active) g.setNodeState(b.active, "error");
      announce("The run failed");
      break;
    case "run_finished":
      if (evt.status === "completed") announce("Finished");
      break;
    default:
      break;
  }
  b.trace.onEvent(evt);
  b.console.onEvent(evt);
}

// Show a thread's saved state in every panel (page reload, new thread).
function restoreBench(b, saved, { fresh = false } = {}) {
  b.graph.reset();
  if (saved.paused) b.graph.setNodeState(saved.paused.node, "paused");
  if (saved.ended) b.graph.setNodeState("__end__", "done");
  b.trace.restore(saved, { fresh });
  b.console.restore(saved);
  showThreadCaption(b, state.threadId, saved);
}

// The Human-in-the-loop view of a chat (spec §4.6): where it is paused, which
// checkpoint thread holds it, and how many checkpoints that thread has saved.
function showThreadCaption(b, threadId, saved) {
  const el = $("trace-thread");
  if (b.pattern.mode !== "chat" || !threadId || !saved) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const n = saved.checkpoints ?? 0;
  const parts = [];
  if (saved.paused) parts.push(`⏸ paused at ${saved.paused.node}`);
  parts.push(`thread ${threadId.slice(0, 4)}…`, `${n} checkpoint${n === 1 ? "" : "s"}`);
  el.textContent = parts.join("  ·  ");
  el.title = `thread_id ${threadId}`;
  el.hidden = false;
}

// After a run, re-read the checkpoint count; a failure just leaves the old caption.
async function refreshThreadCaption(b, gen, threadId) {
  try {
    const saved = await getState(threadId);
    if (live(b, gen) && state.threadId === threadId) showThreadCaption(b, threadId, saved);
  } catch { /* the caption is informational only */ }
}

async function newChatThread(b, gen) {
  const { thread_id } = await createThread(b.pattern.id);
  if (!live(b, gen)) return null;
  setThread(thread_id);
  const saved = await getState(thread_id);  // primed: paused at `ask`
  if (!live(b, gen)) return null;
  restoreBench(b, saved, { fresh: true });
  return thread_id;
}

async function runOnce(b, gen, threadId, text) {
  let started = false;
  for await (const evt of streamRun(threadId, text, { signal: b.abort.signal })) {
    if (!live(b, gen)) return;  // the conversation was replaced mid-stream
    if (!started) {
      started = true;
      b.console.addUser(text);
    }
    dispatch(b, evt);
  }
  if (live(b, gen) && b.pattern.mode === "chat") refreshThreadCaption(b, gen, threadId);  // not awaited
}

async function send(b, text) {
  const chat = b.pattern.mode === "chat";
  const gen = chatGen;
  b.console.setBusy(true);
  try {
    let tid = state.threadId;
    if (!chat) {
      // A trigger thread runs once, so every Run gets a fresh thread and trace.
      ({ thread_id: tid } = await createThread(b.pattern.id));
      if (!live(b, gen)) return;
      setThread(tid);
      b.graph.reset();
      // The input is the run's starting state, not a node's update: seed it.
      b.trace.restore({ values: { messages: [{ role: "user", content: text }] } }, { fresh: true });
    }
    if (!tid) tid = await newChatThread(b, gen);
    if (!tid) return;
    try {
      await runOnce(b, gen, tid, text);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404) || !live(b, gen)) throw err;
      // The server forgot this thread (it restarted): start over once, quietly.
      tid = chat ? await newChatThread(b, gen) : null;
      if (!chat) {
        ({ thread_id: tid } = await createThread(b.pattern.id));
        if (!live(b, gen)) return;
        setThread(tid);
      }
      if (!tid) return;
      b.console.showNotice(STARTED_NEW);
      await runOnce(b, gen, tid, text);
    }
  } catch (err) {
    if (!live(b, gen) || err.name === "AbortError") return;
    if (err instanceof ApiError && err.status === 409 && err.detail === "conversation ended") {
      b.console.showNotice(ENDED_TEXT, { action: "new-chat" });
    } else if (err instanceof ApiError) {
      b.console.showNotice(`Could not run the graph: ${err.message}.`);
    } else {
      b.console.showNotice("Lost the connection to the Studio server. Check that it is running, then send again.");
    }
    b.console.setDraft(text);
  } finally {
    if (live(b, gen)) b.console.setBusy(false);
  }
}

// Create and prime a chat thread with the console busy, so a sample clicked
// meanwhile can't start a second thread.
async function primeChat(b, gen) {
  b.console.setBusy(true);
  try {
    await newChatThread(b, gen);
  } catch (err) {
    if (live(b, gen)) b.console.showNotice(`Could not start a chat: ${err.message}.`);
  } finally {
    if (live(b, gen)) b.console.setBusy(false);
  }
}

async function startNewChat(b) {
  const gen = ++chatGen;  // any send still running belongs to the old chat
  b.abort.abort();
  b.abort = new AbortController();
  setThread(null);
  b.graph.reset();
  b.trace.reset();
  b.console.reset();
  showThreadCaption(b, null, null);
  b.console.setBusy(false);
  if (b.pattern.mode === "chat") await primeChat(b, gen);
}

// Leaving a live page (for the catalog, a Guide-only page or another demo):
// hang up on its stream, which frees the session's run slot, and bump the
// tokens so nothing still in flight lands in the next view (Review Focus 4).
function leaveBench() {
  if (!bench) return;
  bench.abort.abort();
  bench.console.setBusy(true);  // a send now would run on the page being left
  bench.graph.destroy();  // no live Cytoscape instance outlives its page
  bench = null;
  benchToken++;
  chatGen++;
}

async function openBench(pattern) {
  bench?.abort.abort();  // leaving a running pattern hangs up on its stream
  const b = {
    pattern,
    token: ++benchToken,
    abort: new AbortController(),
    active: null,
  };
  bench = b;
  const gen = ++chatGen;
  b.graph = createGraph($("trace-graph"), pattern.topology);
  b.trace = createTrace($("trace-timeline"), $("trace-state"), { onSelect: (node) => b.graph.highlight(node) });
  b.console = createConsole($("console"), {
    mode: pattern.mode,
    samples: pattern.samples,
    onSend: (text) => send(b, text),
    onNewChat: () => startNewChat(b),
  });

  showThreadCaption(b, null, null);

  // Reload mid-conversation: rebuild the panels from the saved checkpoint.
  // The console stays busy meanwhile: a send now would race the restore.
  const saved = rememberedThread(pattern.id);
  if (saved) {
    b.console.setBusy(true);
    try {
      const snapshot = await getState(saved);
      if (!live(b, gen)) return;
      state.threadId = saved;
      restoreBench(b, snapshot);
      b.console.setBusy(false);
      return;
    } catch (err) {
      if (!live(b, gen)) return;
      rememberThread(pattern.id, null);  // unknown after a restart: start fresh below
      b.console.setBusy(false);
      if (!(err instanceof ApiError && err.status === 404)) {
        b.console.showNotice(`Could not restore the last chat: ${err.message}.`);
      }
    }
  }
  if (pattern.mode === "chat") await primeChat(b, gen);
}

document.addEventListener("pattern-change", (e) => openBench(e.detail.pattern));

start();
