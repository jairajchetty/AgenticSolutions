// App shell: owns the app state, the pattern tabs and hash routing (spec §6).
//
// The URL hash (#guardrail) selects the pattern; the default is `qa`.
// Choosing a pattern loads its detail, renders the Guide and fires a
// `pattern-change` event on `document` so the trace and console (Task 10)
// can rebuild themselves from `state.pattern`.
import { getPatterns, getPattern, getSession } from "./api.js";
import { renderGuide, renderInlineCode } from "./guide.js";

const DEFAULT_PATTERN = "qa";
const TAB_SLOTS = 7;  // the full catalog (spec §4); unbuilt patterns show as placeholders

export const state = { pattern: null, threadId: null, session: null };

const $ = (id) => document.getElementById(id);
let patterns = [];
let loadToken = 0;  // ignores late responses after a quicker tab switch

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
      tab.title = p.summary;
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
  const id = decodeURIComponent(location.hash.slice(1));
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
    if (state.pattern?.id !== id) selectPattern(id);
  });
  const id = patternFromHash();
  if (location.hash.slice(1) !== id) history.replaceState(null, "", `#${id}`);
  selectPattern(id);
}

start();
