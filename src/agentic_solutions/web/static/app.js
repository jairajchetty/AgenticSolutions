// App shell: owns the app state, the pattern tabs and hash routing (spec §6).
//
// The URL hash (#guardrail) selects the pattern; the default is `qa`.
// Choosing a pattern loads its detail, renders the Guide and fires a
// `pattern-change` event on `document`; the wiring below rebuilds the trace
// graph, timeline and console for it and runs messages through `streamRun`.
import { ApiError, createThread, getPatterns, getPattern, getSession, getState, streamRun } from "./api.js";
import { renderGuide, renderInlineCode } from "./guide.js";
import { createGraph } from "./graph.js";
import { createTrace } from "./trace.js";
import { createConsole } from "./console.js";

const DEFAULT_PATTERN = "qa";
const TAB_SLOTS = 7;  // the full catalog (spec §4); unbuilt patterns show as placeholders

export const state = { pattern: null, threadId: null, session: null };

const $ = (id) => document.getElementById(id);
let patterns = [];
let loadToken = 0;  // ignores late responses after a quicker tab switch
let requestedId = null;  // the pattern last asked for (state.pattern lags until its fetch lands)

function announce(text) {
  $("announcer").textContent = text;
}

function renderTabs() {
  const list = $("pattern-tabs");
  list.replaceChildren();
  for (let i = 0; i < TAB_SLOTS; i++) {
    const p = patterns[i];
    const li = document.createElement("li");
    li.setAttribute("role", "presentation");
    const tab = document.createElement(p ? "a" : "span");
    tab.className = "tab";
    const num = document.createElement("span");
    num.className = "tab-num";
    num.textContent = String(i + 1);
    const label = document.createElement("span");
    label.className = "tab-label";
    if (p) {
      tab.href = `#${p.id}`;
      tab.id = `tab-${p.id}`;
      tab.dataset.pattern = p.id;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", "bench");
      tab.title = p.title.replace(/`/g, "");  // the label may be cut short with an ellipsis
      renderInlineCode(label, p.title);
    } else {
      tab.classList.add("tab-soon");
      tab.setAttribute("aria-disabled", "true");
      tab.title = "Coming soon";
      label.classList.add("visually-hidden");  // number only, to keep the bar compact
      label.textContent = `Pattern ${i + 1}, coming soon`;
    }
    tab.append(num, label);
    li.append(tab);
    list.append(li);
  }
}

function markActiveTab(id) {
  for (const tab of document.querySelectorAll(".tab[data-pattern]")) {
    const on = tab.dataset.pattern === id;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
  }
}

// Arrow keys move between the built tabs (WAI-ARIA tabs pattern).
function onTabKey(event) {
  const tabs = [...document.querySelectorAll(".tab[data-pattern]")];
  const at = tabs.indexOf(document.activeElement);
  if (at < 0) return;
  const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
  let next = null;
  if (step) next = tabs[(at + step + tabs.length) % tabs.length];
  if (event.key === "Home") next = tabs[0];
  if (event.key === "End") next = tabs[tabs.length - 1];
  if (!next) return;
  event.preventDefault();
  next.focus();
  location.hash = next.dataset.pattern;
}

function patternFromHash() {
  let id;
  try {
    id = decodeURIComponent(location.hash.slice(1));
  } catch {
    return DEFAULT_PATTERN;  // malformed escape such as #%E0
  }
  return patterns.some((p) => p.id === id) ? id : DEFAULT_PATTERN;
}

function renderPatternChrome(detail) {
  const heading = $("trace-pattern");
  heading.replaceChildren();
  renderInlineCode(heading, detail.title);
  $("console-summary").textContent = detail.summary;
  $("console").dataset.mode = detail.mode;  // "chat" or "trigger"
  $("console-send").textContent = detail.mode === "chat" ? "Send" : "Run";
  document.title = `${detail.title.replace(/`/g, "")} · Agentic Patterns Studio`;
}

async function selectPattern(id) {
  const token = ++loadToken;
  requestedId = id;
  markActiveTab(id);
  try {
    const detail = await getPattern(id);
    if (token !== loadToken) return;
    state.pattern = detail;
    state.threadId = null;
    renderPatternChrome(detail);
    renderGuide($("guide-body"), detail.explanation_md);
    announce(`Pattern: ${detail.title.replace(/`/g, "")}`);
    document.dispatchEvent(new CustomEvent("pattern-change", { detail: { pattern: detail } }));
  } catch (err) {
    if (token !== loadToken) return;
    requestedId = null;  // let a click on any tab, even this one, retry
    showGuideError(`Could not load this pattern: ${err.message}. Reload the page to try again.`);
  }
}

function showGuideError(text) {
  const p = document.createElement("p");
  p.className = "error-note";
  p.textContent = text;
  $("guide-body").replaceChildren(p);
}

function renderSession(session) {
  const badge = $("mode-badge");
  badge.dataset.mode = session.mode;
  badge.querySelector(".mode-text").textContent =
    session.mode === "offline" ? "Offline (scripted)" : "Live";
  if (session.max_input_chars) $("console-text").maxLength = session.max_input_chars;  // the server's limit
}

async function start() {
  $("pattern-tabs").addEventListener("keydown", onTabKey);
  try {
    [patterns, state.session] = await Promise.all([getPatterns(), getSession()]);
  } catch (err) {
    showGuideError(`Could not reach the Studio server: ${err.message}. Reload the page to try again.`);
    return;
  }
  renderSession(state.session);
  renderTabs();
  window.addEventListener("hashchange", () => {
    const id = patternFromHash();
    if (location.hash.slice(1) !== id) history.replaceState(null, "", `#${id}`);
    if (requestedId !== id) selectPattern(id);
  });
  const id = patternFromHash();
  if (location.hash.slice(1) !== id) history.replaceState(null, "", `#${id}`);
  selectPattern(id);
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
