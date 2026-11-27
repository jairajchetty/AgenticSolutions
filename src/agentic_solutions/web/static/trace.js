// Timeline and state view (spec §6).
//
// The timeline gets one row per finished step: "#step node · N ms", tagged
// "resumed" when the step re-ran a paused node (spec §5, edges). Clicking a
// row shows the state as it stood after that step: every `update` so far,
// merged the way the graph's state merges them. That is inspection only,
// not replay. All text goes in through textContent.

const OPEN_DEPTH = 3;  // JSON levels shown expanded

// Merge one node's update into the accumulated state. `messages` uses the
// add_messages reducer, so updates append to it. Serialized messages carry no
// ids, so a {role: "remove"} entry drops the newest message, which is what the
// catalog's only remover (the guardrail's `refuse`) deletes.
function merge(acc, update) {
  const next = { ...acc };
  for (const [key, value] of Object.entries(update || {})) {
    if (key === "messages" && Array.isArray(value)) {
      const list = Array.isArray(next.messages) ? [...next.messages] : [];
      for (const m of value) {
        if (m && m.role === "remove") list.pop();
        else list.push(m);
      }
      next.messages = list;
    } else {
      next[key] = value;
    }
  }
  return next;
}

function scalar(value) {
  const span = document.createElement("span");
  const type = value === null ? "null" : typeof value;
  span.className = `json-${type}`;
  span.textContent = type === "string" ? JSON.stringify(value) : String(value);
  return span;
}

function keyLabel(key) {
  const span = document.createElement("span");
  span.className = "json-key";
  span.textContent = `${key}: `;
  return span;
}

// Render a JSON value as nested <details> blocks (collapsible), text only.
function renderJson(value, key, depth = 0) {
  if (value === null || typeof value !== "object") {
    const row = document.createElement("div");
    row.className = "json-row";
    if (key !== undefined) row.append(keyLabel(key));
    row.append(scalar(value));
    return row;
  }
  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
  const box = document.createElement("details");
  box.className = "json-node";
  box.open = depth < OPEN_DEPTH;
  const summary = document.createElement("summary");
  if (key !== undefined) summary.append(keyLabel(key));
  const shape = document.createElement("span");
  shape.className = "json-shape";
  shape.textContent = isArray ? `[${entries.length}]` : `{${entries.length}}`;
  summary.append(shape);
  box.append(summary);
  const body = document.createElement("div");
  body.className = "json-body";
  for (const [k, v] of entries) body.append(renderJson(v, k, depth + 1));
  if (!entries.length) {
    const none = document.createElement("span");
    none.className = "json-empty";
    none.textContent = "empty";
    body.append(none);
  }
  box.append(body);
  return box;
}

// createTrace(timelineEl, stateEl, {onSelect}) -> {onEvent, reset, restore}
// `onSelect(node | null)` lets the caller highlight the selected step's node.
export function createTrace(timelineEl, stateEl, { onSelect } = {}) {
  let acc = {};
  let run = 0;
  let resumedSteps = new Set();
  let selected = null;  // the selected row's <button>

  function showState(values, caption) {
    const head = document.createElement("p");
    head.className = "state-caption";
    head.textContent = caption;
    const empty = !values || !Object.keys(values).length;
    // The top-level keys sit directly in the panel (no wrapper for the root).
    const rows = empty ? [] : Object.entries(values).map(([k, v]) => renderJson(v, k, 1));
    stateEl.replaceChildren(head, ...rows);
  }

  function select(button, snapshot, caption, node) {
    if (selected) selected.setAttribute("aria-pressed", "false");
    selected = button;
    if (button) button.setAttribute("aria-pressed", "true");
    showState(snapshot, caption);
    onSelect?.(node);
  }

  function hint(text) {
    const li = document.createElement("li");
    li.className = "empty-hint";
    li.textContent = text;
    timelineEl.replaceChildren(li);
  }

  function mark(text, kind) {
    timelineEl.querySelector(".empty-hint")?.remove();
    const li = document.createElement("li");
    li.className = `timeline-mark mark-${kind}`;
    li.textContent = text;
    timelineEl.append(li);
    li.scrollIntoView({ block: "nearest" });
    return li;
  }

  function addRow(evt) {
    acc = merge(acc, evt.update);
    const snapshot = structuredClone(acc);
    const caption = `State after run ${run}, step #${evt.step} (${evt.node})`;

    const li = document.createElement("li");
    li.className = "timeline-row";
    li.dataset.node = evt.node;
    li.dataset.step = String(evt.step);
    li.dataset.empty = String(!evt.update || !Object.keys(evt.update).length);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "timeline-step";
    button.setAttribute("aria-pressed", "false");
    const num = document.createElement("span");
    num.className = "step-num";
    num.textContent = `#${evt.step}`;
    const node = document.createElement("span");
    node.className = "step-node";
    node.textContent = evt.node;
    const time = document.createElement("span");
    time.className = "step-time";
    time.textContent = `· ${evt.duration_ms} ms`;
    button.append(num, node, time);
    if (resumedSteps.has(evt.step)) {
      const tag = document.createElement("span");
      tag.className = "step-tag";
      tag.textContent = "resumed";
      button.append(tag);
    }
    button.addEventListener("click", () => select(button, snapshot, caption, evt.node));
    li.append(button);

    timelineEl.querySelector(".empty-hint")?.remove();
    timelineEl.append(li);
    li.scrollIntoView({ block: "nearest" });
    select(button, snapshot, caption, null);  // follow the run live; no highlight until clicked
  }

  function onEvent(evt) {
    switch (evt.type) {
      case "run_started":
        run += 1;
        resumedSteps = new Set();
        mark(`Run ${run}`, "run");
        break;
      case "node_started":
        if (evt.resumed) resumedSteps.add(evt.step);
        break;
      case "node_finished":
        addRow(evt);
        break;
      case "interrupt": {
        // The paused node "finished" only by pausing: it is waiting, not done,
        // so its step row is replaced by a waiting mark.
        const last = timelineEl.lastElementChild;
        if (last?.classList.contains("timeline-row") && last.dataset.node === evt.node
            && last.dataset.empty === "true") {
          last.remove();
        }
        mark(`⏸ Waiting at ${evt.node}`, "paused");
        break;
      }
      case "error":
        mark(`✕ ${evt.message}`, "error");
        break;
      case "run_finished":
        if (evt.status === "completed") mark("✓ Reached the end", "done");
        break;
      default:
        break;
    }
  }

  function reset() {
    acc = {};
    run = 0;
    resumedSteps = new Set();
    selected = null;
    hint("Steps appear here as the graph runs.");
    showState({}, "No steps yet");
    onSelect?.(null);
  }

  // After a reload: the saved checkpoint is the starting state. Earlier
  // steps are not replayed, so the timeline starts empty.
  // `fresh` marks a thread just created (no conversation to restore yet).
  function restore(stateResponse, { fresh = false } = {}) {
    reset();
    acc = structuredClone(stateResponse.values || {});
    if (!fresh) hint("Restored from the saved checkpoint. New steps appear here.");
    showState(acc, fresh ? "Starting state" : "State from the saved checkpoint");
  }

  reset();
  return { onEvent, reset, restore };
}
