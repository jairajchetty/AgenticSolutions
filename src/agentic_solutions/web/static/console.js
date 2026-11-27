// Agent console: chat bubbles, result cards, refusals and pause prompts (spec §6).
//
// Every piece of user or model text is set with textContent, never parsed as
// HTML (Review Focus 5): "<img src=x onerror=...>" shows up as those characters.
//
// mode "chat":    tokens stream into the assistant bubble; `interrupt` shows
//                 its payload as the agent's prompt (the graph is waiting).
// mode "trigger": one run per input; tokens stream into a result card that
//                 `run_finished.output` then fills.

const ENDED_TEXT = "This conversation has ended. Start a New chat.";

// createConsole(el, {mode, samples, onSend, onNewChat})
//   -> {onEvent, addUser, restore, setBusy, showNotice}
export function createConsole(el, { mode, samples = [], onSend, onNewChat }) {
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
  let prompt = null;   // the pause prompt at the end of the list

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
        setPrompt(evt.payload);
        break;
      case "error":
        bubble("error", evt.message, "✕ Error").setAttribute("role", "alert");
        break;
      case "run_finished":
        if (trigger && evt.status === "completed") {
          if (!card) card = resultCard();
          card.body.textContent = evt.output ?? "(no output)";
          card.box.classList.add("done");
        } else if (!trigger && evt.status === "completed") {
          showNotice(ENDED_TEXT, { action: "new-chat" });
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
    if (stateResponse.paused) setPrompt(stateResponse.paused.payload);
    else if (!trigger && (stateResponse.ended || stateResponse.closed)) {
      showNotice(ENDED_TEXT, { action: "new-chat" });
    }
    if (!list.children.length) reset();
  }

  function reset() {
    list.replaceChildren(element("p", "empty-hint",
      trigger ? "Pick a sample or type a question, then Run the graph."
              : "Pick a sample or type a message to run the graph."));
    prompt = null;
    stream = null;
    card = null;
  }

  function setBusy(on) {
    busy = on;
    send.disabled = on;
    for (const b of chips.querySelectorAll("button")) b.disabled = on;
    el.querySelector(".console-messages").setAttribute("aria-busy", String(on));
    send.textContent = on ? (trigger ? "Running…" : "Sending…") : (trigger ? "Run" : "Send");
  }

  function submit(text) {
    if (busy) return;
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
  return { onEvent, addUser, restore, setBusy, showNotice, reset, setDraft: (t) => { input.value = t; } };
}
