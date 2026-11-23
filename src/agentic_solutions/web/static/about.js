// About copy and the obfuscated contact link (Blueprint spec §4.1, §5).
// Edit the text here. The address is kept in parts so it never appears whole
// in a served file; it is joined only when someone asks to get in touch.
export const ABOUT = {
  name: "Jairaj Chetty",
  role: "Solution architect, enterprise integration and agentic AI",
  record:
    "20+ years of integration architecture across Africa and the Middle East. " +
    "120+ integrations for MTN's group-wide Oracle Fusion ERP. " +
    "Reference architectures for Eskom and Equity Bank. " +
    "TOGAF 10, Oracle Generative AI and AI Vector Search certified. " +
    "Built this Studio with LangGraph and Claude.",
  builtWith: "Built this Studio with LangGraph and Claude.",
};

const PARTS = ["jairajchetty", "gmail.com"];
const SUBJECT = "Agentic Patterns Studio";

export function contactAddress() {
  return PARTS.join("@");
}

export function contactHref() {
  return `mailto:${contactAddress()}?subject=${encodeURIComponent(SUBJECT)}`;
}

// One delegated listener on `root` for every [data-contact] element. Safe to
// call twice. The first activation also shows the address as plain text, for
// visitors with no mail app.
export function bindContact(root) {
  if (root.__contactBound) return;
  root.__contactBound = true;
  const activate = (event) => {
    const trigger = event.target.closest?.("[data-contact]");
    if (!trigger) return;
    event.preventDefault();
    const scope = trigger.parentElement || root;
    const reveal = scope.querySelector("[data-contact-reveal]") || root.querySelector("[data-contact-reveal]");
    if (reveal) {
      reveal.textContent = `or copy: ${contactAddress()}`;
      reveal.hidden = false;
    }
    window.location.href = contactHref();
  };
  root.addEventListener("click", activate);
  root.addEventListener("keydown", (event) => {
    if (event.key === "Enter") activate(event);
  });
}
