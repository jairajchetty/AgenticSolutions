// Unit tests for the purpose-first Guide split (Blueprint spec §4.2, §9.4).
import { test } from "node:test";
import assert from "node:assert/strict";
import { splitPurpose } from "../../src/agentic_solutions/web/static/guide.js";

const SECTIONS = {
  what: "## What it is\nA graph.\n",
  when: "## When to use it\nWhen you branch.\n",
  how: "## How this graph works\nSteps.\n",
  concepts: "## LangGraph concepts\nNodes.\n",
  trade: "## Trade-offs\nCost.\n",
  code: "## Key code\n```python\nx = 1\n```\n",
  try: "## Try this\nRun it.\n",
};
const headings = (md) => [...md.matchAll(/^## (.+)$/gm)].map((m) => m[1]);
const sample = (order) => "# Routing\n\n" + order.map((k) => SECTIONS[k]).join("\n");

test("splits the purpose sections from the rest, H1 excluded", () => {
  const { purpose, rest } = splitPurpose(sample(["what", "when", "how", "concepts", "trade", "code", "try"]));
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.deepEqual(headings(rest), ["How this graph works", "LangGraph concepts", "Trade-offs", "Key code", "Try this"]);
  assert.ok(!/^# /m.test(rest));
  assert.ok(purpose.includes("A graph.") && purpose.includes("When you branch."));
});

test("matches by name when sections are in a different order", () => {
  const { purpose, rest } = splitPurpose(sample(["how", "when", "trade", "what", "code"]));
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.deepEqual(headings(rest), ["How this graph works", "Trade-offs", "Key code"]);
});

test("missing purpose heading: purpose empty, rest is input minus the H1", () => {
  const input = sample(["what", "how", "trade"]);
  const { purpose, rest } = splitPurpose(input);
  assert.equal(purpose, "");
  assert.equal(rest, input.replace(/^# Routing\n/, ""));
});

test("headings inside code fences are ignored", () => {
  const md = "# T\n\n## How\n```md\n## What it is\nfake\n## When to use it\n```\n\n" + SECTIONS.what + "\n" + SECTIONS.when;
  const { purpose, rest } = splitPurpose(md);
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.ok(!purpose.includes("fake"));
  assert.ok(rest.includes("fake"));
});

test("no H1 and empty input are handled", () => {
  assert.deepEqual(splitPurpose(""), { purpose: "", rest: "" });
  assert.equal(splitPurpose(SECTIONS.how).rest, SECTIONS.how);
});

test("a ### subheading inside a purpose section stays in that section", () => {
  const md = "# T\n\n## What it is\nA.\n\n### Detail\nMore.\n\n## When to use it\nB.\n\n## Other\nC.\n";
  const { purpose, rest } = splitPurpose(md);
  assert.ok(purpose.includes("### Detail") && purpose.includes("More."));
  assert.ok(!rest.includes("Detail"));
});

test("CRLF input splits the same as LF", () => {
  const md = sample(["what", "when", "how"]);
  assert.deepEqual(splitPurpose(md.replace(/\n/g, "\r\n")), splitPurpose(md));
});

test("a heading at end of file with no body is kept", () => {
  const { purpose, rest } = splitPurpose("# T\n\n" + SECTIONS.what + "\n" + SECTIONS.when + "\n## Try this");
  assert.deepEqual(headings(purpose), ["What it is", "When to use it"]);
  assert.deepEqual(headings(rest), ["Try this"]);
  const { purpose: p2 } = splitPurpose("# T\n\n" + SECTIONS.how + "\n" + SECTIONS.what + "\n## When to use it");
  assert.deepEqual(headings(p2), ["What it is", "When to use it"]);
});

test("an H1 that is not on line 1 is still dropped", () => {
  const { purpose, rest } = splitPurpose("\n\n# Late Title\n\n" + SECTIONS.what + "\n" + SECTIONS.when + "\n" + SECTIONS.how);
  assert.ok(!/^# /m.test(purpose + rest));
  assert.deepEqual(headings(rest), ["How this graph works"]);
});

test("lossless: non-H1, non-blank lines of purpose + rest equal the input's", () => {
  const md = sample(["how", "when", "code", "what", "try"]).replace("Steps.", "Steps.\n### Sub\n- item");
  const keep = (t) => t.split("\n").filter((l) => l.trim() && !/^# /.test(l)).sort();
  const { purpose, rest } = splitPurpose(md);
  assert.deepEqual(keep(purpose + "\n" + rest), keep(md));
});

// ---- splitStudio: the collapsed "How this Studio implements it" section ----
import { splitStudio } from "../../src/agentic_solutions/web/static/guide.js";

const STUDIO_TITLE = "How this Studio implements it";
const STUDIO = `## ${STUDIO_TITLE}\nIntro line.\n\n### Graph\nG body.\n\n### Tools\n- a\n- b\n\n### State\nS body.\n\n### Run it\nR body.\n`;
const BODY = "## What it is\nA graph.\n\n## Trade-offs\nCost.\n";

test("splitStudio returns the four subsections in order", () => {
  const { body, studio } = splitStudio(BODY + "\n" + STUDIO);
  assert.equal(studio.title, STUDIO_TITLE);
  assert.deepEqual(studio.subsections.map((s) => s.title), ["Graph", "Tools", "State", "Run it"]);
  assert.equal(studio.subsections[0].markdown, "G body.");
  assert.equal(studio.subsections[1].markdown, "- a\n- b");
  assert.deepEqual(headings(body), ["What it is", "Trade-offs"]);
  assert.ok(!body.includes("Studio implements"));
});

test("splitStudio with no section 7 gives null studio and the body unchanged", () => {
  const { body, studio } = splitStudio(BODY);
  assert.equal(studio, null);
  assert.equal(body.trim(), BODY.trim());
});

test("splitStudio ignores the heading inside a code fence", () => {
  const md = BODY + "\n```md\n## How this Studio implements it\n### Graph\n```\n";
  const { body, studio } = splitStudio(md);
  assert.equal(studio, null);
  assert.ok(body.includes("### Graph"));
});

test("splitStudio ignores ### inside a fence within the section", () => {
  const md = "## " + STUDIO_TITLE + "\n### Graph\n```\n### not a heading\n```\n### Tools\nT\n";
  const { studio } = splitStudio(md);
  assert.deepEqual(studio.subsections.map((s) => s.title), ["Graph", "Tools"]);
  assert.ok(studio.subsections[0].markdown.includes("### not a heading"));
});

test("splitStudio handles CRLF", () => {
  const { body, studio } = splitStudio((BODY + "\n" + STUDIO).replace(/\n/g, "\r\n"));
  assert.deepEqual(studio.subsections.map((s) => s.title), ["Graph", "Tools", "State", "Run it"]);
  assert.equal(studio.subsections[3].markdown, "R body.");
  assert.ok(!body.includes("\r"));
});

test("useCaseParagraphs splits the owner's text on blank lines", async () => {
  const { useCaseParagraphs } = await import("../../src/agentic_solutions/web/static/guide.js");
  assert.deepEqual(useCaseParagraphs("First line\nstill first.\n\n  Second.  \n\n\n"), ["First line still first.", "Second."]);
  assert.deepEqual(useCaseParagraphs(null), []);
  assert.deepEqual(useCaseParagraphs("   "), []);
});
