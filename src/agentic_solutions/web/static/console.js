// Agent console: chat bubbles, result cards, refusals and pause prompts (spec §6).
//
// Every piece of user or model text is set with textContent, never parsed as
// HTML (Review Focus 5): "<img src=x onerror=...>" shows up as those characters.
//
// mode "chat":    tokens stream into the assistant bubble; `interrupt` shows
//                 its payload as the agent's prompt (the graph is waiting).
// mode "trigger": one run per input; tokens stream into a result card that
//                 `run_finished.output` then fills.
//
// An `approval_request` pause (Approval spec §5.3) shows the approval card in
// place of the prompt: the proposed order, then Approve, Edit quantities or
// Reject. A decision goes to `onDecide({resume})`; until one is sent the text
// input is disabled. The card is built with DOM APIs only.
import { approvalView, errorNotice, resumeBody, ENDED_TEXT, REASON_MAX } from "./approval.js";

const DECIDE_FIRST = "Decide on the order first";
const OVER_BUDGET = "This total is over the remaining budget; the ERP will refuse it.";
const NO_CHANGES = "Change at least one quantity, or close Edit quantities to approve as quoted.";
const REQUOTED_LATER = "Re-quoted after you submit changes";
const QTY_MIN = 1;
const QTY_MAX = 999;

const isApproval = (payload) => payload !== null && typeof payload === "object" && payload.kind === "approval_request";

// createConsole(el, {mode, samples, onSend, onDecide, onNewChat})
//   -> {onEvent, addUser, addDecision, restore, setBusy, showNotice, reset, setDraft}
export function createConsole(el, { mode, samples = [], onSend, onDecide, onNewChat }) {
  const list = el.querySelector("#console-messages");
  const chips = el.querySelector("#console-samples");
  const form = el.querySelector("#console-form");
  const input = el.querySelector("#console-text");
  const send = el.querySelector("#console-send");
  const newChat = el.querySelector("#console-new");
  const trigger = mode === "trigger";

  let busy = false;
  let stream = null;   // {node, text: Text} the assistant text being streamed
  let card = null;     // trigger mode: the result card of the current run
  let prompt = null;   // the pause prompt (or approval card) at the end of the list
  let approval = null; // {box, title, controls} while an approval card is pending
  let refocus = false; // a decision was sent from the card: put focus somewhere sensible next
  let lastError = null; // the latest `error` event's message, for the notice after the run
  const placeholder = input.placeholder;

  function scroll() {
    list.scrollTop = list.scrollHeight;
  }

  function add(node) {
    list.querySelector(":scope > .empty-hint")?.remove();
    if (prompt && node !== prompt) prompt.before(node);  // the prompt always stays last
    else list.append(node);
    scroll();
    return node;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function bubble(role, text, label) {
    const box = element("div", `msg msg-${role}`);
    box.append(element("p", "msg-who", label));
    const body = element("p", "msg-text");
    if (role === "user" && !text.trim()) {
      body.classList.add("msg-blank");
      body.textContent = text.length ? "(blank message)" : "(empty)";
    } else {
      body.textContent = text;
    }
    box.append(body);
    return add(box);
  }

  function resultCard() {
    const box = element("section", "result-card");
    box.append(element("p", "msg-who", "Result"));
    const body = element("p", "msg-text");
    box.append(body);
    add(box);
    return { box, body, text: body.appendChild(document.createTextNode("")) };
  }

  function chip(className, label, detail) {
    const box = element("div", `chip-line ${className}`);
    box.append(element("span", "chip-label", label));
    if (detail) box.append(element("code", "chip-detail", detail));
    return add(box);
  }

  function setPrompt(text) {
    clearPrompt();
    prompt = element("div", "msg-prompt");
    prompt.append(element("span", "badge badge-paused", "⏸ Paused"));
    prompt.append(element("span", "prompt-text", String(text)));
    list.querySelector(":scope > .empty-hint")?.remove();
    list.append(prompt);
    scroll();
  }

  function clearPrompt() {
    prompt?.remove();
    prompt = null;
    approval = null;
    syncControls();
  }

  // ---------- The approval card ----------

  function button(label, className = "btn") {
    const b = element("button", className, label);
    b.type = "button";
    return b;
  }

  function fact(dl, term, ...details) {
    dl.append(element("dt", "", term));
    const dd = element("dd");
    dd.append(...details);
    dl.append(dd);
  }

  function showApproval(payload) {
    clearPrompt();
    const view = approvalView(payload);
    const uid = `approval-${Math.random().toString(36).slice(2, 8)}`;
    const box = element("section", "approval-card");
    box.setAttribute("aria-labelledby", `${uid}-title`);
    const controls = [];

    const head = element("header", "approval-head");
    const title = element("h3", "approval-title", "Approval needed");
    title.id = `${uid}-title`;
    title.tabIndex = -1;
    head.append(title);
    const ref = [view.reqId, view.version !== null ? `v${view.version}` : "", view.shortHash && `#${view.shortHash}`]
      .filter(Boolean).join(" · ");
    if (ref) head.append(element("p", "approval-ref", ref));
    box.append(head);
    // Why this order: the model's own words, labelled as such, and the
    // requisition's justification (part of what the approval is bound to).
    const why = element("dl", "approval-facts approval-why");
    if (view.summary) fact(why, "Agent's summary", view.summary);
    if (view.justification) fact(why, "Justification", view.justification);
    if (why.children.length) box.append(why);
    if (view.requoted) box.append(element("p", "approval-note", "Prices were re-quoted"));

    // The lines table scrolls inside the card, never the page.
    const wrap = element("div", "approval-table");
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", "Order lines");
    wrap.tabIndex = 0;
    const table = element("table");
    table.append(element("caption", "visually-hidden", "Proposed order"));
    const thead = element("thead");
    const hr = element("tr");
    for (const [text, cls] of [["Item", ""], ["Qty", "num"], ["Unit price", "num"], ["Line total", "num"]]) {
      const th = element("th", cls, text);
      th.scope = "col";
      hr.append(th);
    }
    thead.append(hr);
    const tbody = element("tbody");
    const qtyInputs = [];
    for (const row of view.rows) {
      const tr = element("tr");
      const item = element("th", "approval-item");
      item.scope = "row";
      item.append(element("span", "approval-name", row.name), element("span", "approval-sku", row.sku));
      const qty = element("td", "num");
      const shown = element("span", "approval-qty", String(row.qty));
      const field = element("input", "approval-qty-input");
      Object.assign(field, { type: "number", min: String(QTY_MIN), max: String(QTY_MAX), step: "1",
                             required: true, value: String(row.qty), hidden: true, inputMode: "numeric" });
      field.setAttribute("aria-label", `Quantity of ${row.name}`);
      field.dataset.sku = row.sku;
      field.dataset.original = String(row.qty);
      qtyInputs.push({ field, shown });
      controls.push(field);
      qty.append(shown, field);
      // Prices and totals are quoted for the current quantities: while they
      // are being edited these figures are stale, so they are muted.
      tr.append(item, qty, element("td", "num approval-quoted", row.unit),
        element("td", "num approval-quoted", row.lineTotal));
      tbody.append(tr);
    }
    const tfoot = element("tfoot");
    const fr = element("tr");
    const totalLabel = element("th", "", "Total");
    totalLabel.scope = "row";
    totalLabel.colSpan = 3;
    fr.append(totalLabel, element("td", "num approval-total approval-quoted", view.total));
    const staleRow = element("tr", "approval-stale");
    const staleCell = element("td", "", REQUOTED_LATER);
    staleCell.colSpan = 4;
    staleRow.append(staleCell);
    tfoot.append(fr, staleRow);
    table.append(thead, tbody, tfoot);
    wrap.append(table);
    box.append(wrap);

    // The total also sits here, so it is in view when the table scrolls (375 px).
    const facts = element("dl", "approval-facts");
    const factStale = element("span", "approval-stale", ` · ${REQUOTED_LATER}`);
    fact(facts, "Total", element("strong", "approval-quoted", view.total), factStale);
    fact(facts, "Cost centre", view.costCentre,
      ...(view.budgetRemaining ? [element("span", "approval-muted", ` · ${view.budgetRemaining} remaining`)] : []));
    if (view.policyReason) fact(facts, "Policy", view.policyReason);
    if (view.expires) fact(facts, "Quotes valid until", `${view.expires} (your time)`);
    box.append(facts);
    if (view.overBudget) box.append(element("p", "approval-warn", OVER_BUDGET));

    const problem = element("p", "approval-problem");
    problem.setAttribute("role", "alert");
    problem.hidden = true;
    const say = (text) => { problem.textContent = text; problem.hidden = !text; };

    // Edit: number inputs in the Qty column, then "Submit changes".
    const editPanel = element("div", "approval-panel");
    editPanel.hidden = true;
    editPanel.id = `${uid}-edit`;
    editPanel.append(element("p", "approval-muted", "Change the quantities above, then submit. The agent re-quotes the order."));
    const submitEdit = button("Submit changes");
    editPanel.append(submitEdit);

    // Reject: an optional reason, then "Reject order".
    const rejectPanel = element("div", "approval-panel");
    rejectPanel.hidden = true;
    rejectPanel.id = `${uid}-reject`;
    const reasonLabel = element("label", "approval-label", "Reason (optional)");
    const reason = element("textarea", "approval-reason");
    reason.id = `${uid}-reason`;
    reason.rows = 2;
    reason.maxLength = REASON_MAX;
    reasonLabel.htmlFor = reason.id;
    const rejectOrder = button("Reject order");
    rejectPanel.append(reasonLabel, reason, rejectOrder);

    const actions = element("div", "approval-actions");
    const approve = button("Approve", "btn btn-primary");
    const edit = button("Edit quantities");
    const reject = button("Reject");
    edit.setAttribute("aria-controls", editPanel.id);
    reject.setAttribute("aria-controls", rejectPanel.id);
    actions.append(approve, edit, reject);
    controls.push(approve, edit, reject, submitEdit, reason, rejectOrder);

    // Approve commits exactly what the card shows, so it is available only
    // while neither panel is open: then "Submit changes" or "Reject order" is
    // the one way to commit. Disabled, it steps down from amber.
    function refresh() {
      const open = !editPanel.hidden || !rejectPanel.hidden;
      approve.disabled = busy || open;
      approve.classList.toggle("btn-primary", !approve.disabled);
      approve.title = open ? "Close the open panel to approve the order as shown" : "";
    }
    function setEditing(on) {
      editPanel.hidden = !on;
      edit.setAttribute("aria-expanded", String(on));
      box.classList.toggle("is-editing", on);
      staleRow.hidden = !on;
      factStale.hidden = !on;
      for (const { field, shown } of qtyInputs) {
        if (!on) field.value = field.dataset.original;
        field.hidden = !on;
        shown.hidden = on;
      }
      refresh();
    }
    function setRejecting(on) {
      rejectPanel.hidden = !on;
      reject.setAttribute("aria-expanded", String(on));
      refresh();
    }
    setEditing(false);
    setRejecting(false);

    function decide(body) {
      if (busy) return;
      say("");
      refocus = true;
      onDecide?.(body);
    }

    approve.onclick = () => decide(resumeBody("approve", { card: view }));
    edit.onclick = () => {
      const on = editPanel.hidden;
      say("");
      setRejecting(false);
      setEditing(on);
      if (on) qtyInputs[0]?.field.focus();
    };
    reject.onclick = () => {
      const on = rejectPanel.hidden;
      say("");
      setEditing(false);
      setRejecting(on);
      if (on) reason.focus();
    };
    submitEdit.onclick = () => {
      const bad = qtyInputs.find(({ field }) => !field.checkValidity());
      if (bad) {
        say(`Quantities must be whole numbers from ${QTY_MIN} to ${QTY_MAX}.`);
        bad.field.focus();
        return;
      }
      const body = resumeBody("edit", { card: view, edits: qtyInputs.map(({ field }) => (
        { sku: field.dataset.sku, quantity: field.value, original: field.dataset.original })) });
      if (!body.resume.edits.length) {
        say(NO_CHANGES);
        qtyInputs[0]?.field.focus();
        return;
      }
      decide(body);
    };
    // Enter in a quantity submits the changes (a number input has no form here).
    for (const { field } of qtyInputs) {
      field.onkeydown = (e) => {
        if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); submitEdit.click(); }
      };
    }
    rejectOrder.onclick = () => decide(resumeBody("reject", { card: view, reason: reason.value }));

    box.append(actions, editPanel, rejectPanel, problem);

    list.querySelector(":scope > .empty-hint")?.remove();
    list.append(box);
    prompt = box;
    approval = { box, title, controls, refresh };
    syncControls();
    scroll();
    if (refocus) {  // a new card after an edit (or a re-quote): keyboard users land on it
      refocus = false;
      title.focus({ preventScroll: true });
    }
  }

  function showPause(payload) {
    if (isApproval(payload)) showApproval(payload);
    else setPrompt(payload);
  }

  // The decision was sent and its run has started: the card goes, a note stays.
  function addDecision(text) {
    clearPrompt();
    stream = null;
    const note = element("p", "decision-note");
    note.append(element("span", "decision-label", "Decision"), element("span", "", text));
    add(note);
  }

  function showNotice(text, { action } = {}) {
    const last = prompt ? prompt.previousElementSibling : list.lastElementChild;
    if (last?.classList.contains("notice") && last.querySelector(".notice-text")?.textContent === text) {
      scroll();  // already the latest thing on screen: don't stack a duplicate
      return last;
    }
    const box = element("div", "notice");
    box.setAttribute("role", "status");
    box.append(element("span", "notice-text", text));
    if (action === "new-chat") {
      const button = element("button", "btn btn-small", "New chat");
      button.type = "button";
      button.addEventListener("click", () => onNewChat?.());
      box.append(button);
    }
    return add(box);
  }

  function addUser(text) {
    clearPrompt();
    stream = null;
    bubble("user", text, "You");
  }

  function streamText(node, text) {
    if (trigger) {
      if (!card) card = resultCard();
      card.text.appendData(text);
    } else {
      if (!stream || stream.node !== node) {
        const box = bubble("assistant", "", "Agent");
        box.classList.add("streaming");
        const body = box.querySelector(".msg-text");
        stream = { node, box, text: body.appendChild(document.createTextNode("")) };
      }
      stream.text.appendData(text);
    }
    scroll();
  }

  function assistantFrom(update) {
    const msgs = Array.isArray(update?.messages) ? update.messages : [];
    return msgs.filter((m) => m && m.role === "assistant" && m.content).map((m) => m.content);
  }

  function onNodeFinished(evt) {
    const update = evt.update || {};
    if (update.refusal) {
      const box = bubble("refusal", update.refusal, "✕ Refused by the guardrail");
      box.setAttribute("role", "alert");
    }
    if (!trigger) {
      // A node that produced a reply without streaming tokens still gets a bubble.
      const streamed = stream && stream.node === evt.node;
      if (streamed) stream.box.classList.remove("streaming");
      else for (const text of assistantFrom(update)) bubble("assistant", text, "Agent");
      stream = null;
    }
  }

  function onEvent(evt) {
    switch (evt.type) {
      case "run_started":
        stream = null;
        card = null;
        lastError = null;
        break;
      case "token":
        streamText(evt.node, evt.text);
        break;
      case "tool_call":
        chip("chip-call", `Tool call: ${evt.name}`, JSON.stringify(evt.args));
        break;
      case "tool_result":
        chip("chip-result", `Tool result: ${evt.name}`, String(evt.content));
        break;
      case "node_finished":
        onNodeFinished(evt);
        break;
      case "interrupt":
        showPause(evt.payload);
        break;
      case "error":
        lastError = evt.message;
        bubble("error", evt.message, "✕ Error").setAttribute("role", "alert");
        break;
      case "run_finished":
        if (trigger && evt.status === "completed") {
          if (!card) card = resultCard();
          card.body.textContent = evt.output ?? "(no output)";
          card.box.classList.add("done");
        } else if (!trigger && evt.status === "completed") {
          showNotice(ENDED_TEXT, { action: "new-chat" });
        } else if (!trigger && evt.status === "error") {
          // The server closes a chat thread whose run failed: say what to do next.
          showNotice(errorNotice(lastError), { action: "new-chat" });
        }
        break;
      default:
        break;
    }
  }

  // Rebuild the conversation from GET /api/threads/{id}/state after a reload.
  function restore(stateResponse) {
    list.replaceChildren();
    prompt = null;
    approval = null;
    stream = null;
    card = null;
    const values = stateResponse.values || {};
    const messages = values.messages || [];
    for (const m of messages) {
      if (m.role === "user") bubble("user", m.content ?? "", "You");
      else if (m.role === "assistant" && trigger) {
        const c = resultCard();
        c.body.textContent = m.content;
        c.box.classList.add("done");
      } else if (m.role === "assistant") {
        for (const call of m.tool_calls || []) chip("chip-call", `Tool call: ${call.name}`, JSON.stringify(call.args));
        if (m.content) bubble("assistant", m.content, "Agent");
      } else if (m.role === "tool") chip("chip-result", `Tool result: ${m.name ?? "tool"}`, m.content);
    }
    // The guardrail removed the refused prompt from `messages`, so stand in for
    // it. `refusal` outlives later turns (a blank message or `stop` keeps it),
    // so it is drawn only while it is still the latest event: when the last
    // message is not a newer user turn.
    if (values.refusal && messages.at(-1)?.role !== "user") {
      bubble("user", "(message removed by the guardrail)", "You").querySelector(".msg-text")
        .classList.add("msg-blank");
      bubble("refusal", values.refusal, "✕ Refused by the guardrail");
    }
    if (stateResponse.paused) showPause(stateResponse.paused.payload);
    else if (!trigger && (stateResponse.ended || stateResponse.closed)) {
      showNotice(ENDED_TEXT, { action: "new-chat" });
    }
    if (!list.children.length) reset();
    syncControls();
  }

  function reset() {
    list.replaceChildren(element("p", "empty-hint",
      trigger ? "Pick a sample or type a question, then Run the graph."
              : "Pick a sample or type a message to run the graph."));
    prompt = null;
    approval = null;
    stream = null;
    card = null;
    refocus = false;
    syncControls();
  }

  // While an approval card is pending, the text input, Send and the samples
  // wait for the decision, and Send steps down from amber: Approve is the one
  // primary action in view. Every control is disabled while a run is busy.
  function syncControls() {
    const deciding = approval !== null;
    send.disabled = busy || deciding;
    for (const b of chips.querySelectorAll("button")) b.disabled = busy || deciding;
    send.classList.toggle("btn-primary", !deciding);
    input.disabled = deciding;
    input.placeholder = deciding ? DECIDE_FIRST : placeholder;
    for (const c of approval?.controls ?? []) c.disabled = busy;
    approval?.refresh();
    approval?.box.setAttribute("aria-busy", String(busy));
  }

  function setBusy(on) {
    busy = on;
    el.querySelector(".console-messages").setAttribute("aria-busy", String(on));
    send.textContent = on ? (trigger ? "Running…" : "Sending…") : (trigger ? "Run" : "Send");
    syncControls();
    // A decision was sent from the card, whose buttons were then disabled:
    // focus goes back to the card (the server refused it, so it is still
    // here) or, once the card has gone, to the message box.
    if (!on && refocus) {
      refocus = false;
      if (approval) {
        if (!approval.box.contains(document.activeElement)) approval.title.focus({ preventScroll: true });
      } else if (!input.disabled) {
        input.focus({ preventScroll: true });
      }
    }
  }

  function submit(text) {
    if (busy || approval) return;
    // Chat: whitespace is a real input (the router sends it back to `ask`).
    // Trigger: the server rejects blank input, so say so here.
    if (!text.length || (trigger && !text.trim())) {
      input.focus();
      return;
    }
    input.value = "";
    onSend?.(text);
  }

  // Property handlers (not addEventListener): a console rebuilt for another
  // pattern replaces them instead of stacking a second set.
  form.onsubmit = (e) => { e.preventDefault(); submit(input.value); };
  input.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      submit(input.value);
    }
  };
  newChat.onclick = () => onNewChat?.();
  newChat.textContent = trigger ? "Clear" : "New chat";

  chips.replaceChildren();
  for (const sample of samples) {
    const b = element("button", "sample-chip", sample);
    b.type = "button";
    b.onclick = () => { input.value = sample; submit(sample); };
    chips.append(b);
  }

  reset();
  setBusy(false);
  return { onEvent, addUser, addDecision, restore, setBusy, showNotice, reset, setDraft: (t) => { input.value = t; } };
}
