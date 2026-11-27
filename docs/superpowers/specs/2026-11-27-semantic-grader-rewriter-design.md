# Semantic demo: grader and query rewriter: design

Date: 2026-11-27
Status: draft for approval
Builds on: `2026-11-27-semantic-paradise-lost-design.md` (the live Semantic demo)

## 1. Intent

The Semantic Guide describes two optional roles that the live demo doesn't yet have. The **grader** checks whether retrieved passages are relevant to the question. The **query rewriter** rephrases the search when they aren't. This design adds both, so the demo shows the corrective form of the pattern: search, check, then rephrase and search again or answer.

## 2. Goals, non-goals, anti-goals

**Goals**
- Every `search_book` result is graded passage by passage. Passages that aren't relevant are dropped before the agent sees them.
- When no passage survives, the query is rewritten and the search runs again, at most 2 times per question.
- The trace shows the loop. The graph gains `grade` and `rewrite_query`, with labelled edges, in the fixed Approval-style layout.
- Works offline (scripted) and with both live models.

**Non-goals**
- No separate grader model. The grader and the rewriter use the model selected in the picker.
- No grading of `read_passage` results. Those are reads by position, not searches.
- No change to the answer format (two or three sentences, then "Sources:").

**Anti-goals**
- **A grader that empties every result.** If the grader fails (a malformed reply, or a tool error), the passages pass through unfiltered rather than being lost.
- **Unbounded loops.** Rewrites are capped per question, alongside the existing 6-round cap.
- **Sources the agent never saw.** Only the passages that survive grading can appear in the answer's "Sources".

## 3. Approaches considered

| Option | Trade-off | Chosen |
|---|---|---|
| **(a) Filter per passage; rewrite only if none survive** | Shorter, more relevant context for the answer; one grading call per search | **Yes** |
| (b) Grade the result set as a whole; rewrite if it fails | Simpler, but irrelevant passages still reach the answer and its sources | No |

How the grader and rewriter reply (my call): **a forced tool call**. Each gets a single tool, bound with `tool_choice` naming it: `grade_passages(relevant: list[int])` and `rewrite_search(query: str)`. Forced tool choice is already proven on Claude Haiku and on DeepSeek through OpenRouter. It gives a structured reply without relying on JSON parsing or `with_structured_output`, which the scripted model doesn't support.

## 4. Graph

```
START → ask ─(question)→ agent ─(search / read)→ tools → grade ─(relevant)→ agent
         ↑  ─(stop)→ END   └─(answer)→ ask                  └─(none relevant)→ rewrite_query → tools
         └─(empty)┘
```

**Nodes and edges:**
- `tools` → `grade` is now unconditional, replacing `tools` → `agent`.
- `grade` → `agent` covers three cases: at least one relevant passage, a read-only round (only `read_passage` ran), or the rewrite limit reached.
- `grade` → `rewrite_query` when no passage survives and fewer than 2 rewrites have been made for this question.
- `rewrite_query` → `tools` is unconditional. The node emits an `AIMessage` with one `search_book` call carrying the new query.

**State:** a new field, `rewrites: int`. `ask` resets it to 0 for each question, as it does `tool_rounds`.

**Edge labels**, short label first, full rule second:

| Edge | Label | Full rule |
|---|---|---|
| `grade` → `agent` | `relevant` | At least one passage is relevant (others are dropped), or the search was a read by position, or the rewrite limit was reached. |
| `grade` → `rewrite_query` | `none relevant` | No passage is relevant: rephrase the search (2 times per question at most). |

The existing labels stay as they are. The `agent` → `tools` rule still reads "search / read".

## 5. The grader (`grade`)

**Inputs:** the question (the latest human message) and the `search_book` results from the latest tool round. These are the `ToolMessage`s that answer the latest `AIMessage`'s `search_book` calls.

**Model call:** the selected model is bound to `grade_passages` with a forced `tool_choice`. The prompt lists each passage, numbered, with its Book and lines, and says:

> Decide which passages help answer the question. A passage is relevant if it contains information the answer needs. It is not relevant if it only shares words or names with the question. Call grade_passages with the numbers of the relevant passages; an empty list if none are.

**Result:**
- Each graded `ToolMessage` is replaced (same `id`, so `add_messages` updates it in place) with `{"passages": [the relevant passages], "not_relevant": n}`, where n is how many were removed.
- **None survive:** `"passages"` is `[]`, so the agent sees that the search found nothing relevant.

**When grading fails:** a missing or malformed `grade_passages` call, numbers out of range, or a tool-error result. The passages pass through unchanged and the run goes to `agent`. There is no retry.

**What it costs:** one model call per graded search round.

## 6. The query rewriter (`rewrite_query`)

**Model call:** bound to `rewrite_search` with a forced `tool_choice`. The prompt gives the question and the queries already tried in this question (taken from the `search_book` calls since the last human message), and says:

> The searches so far found no relevant passages in Paradise Lost. Write one new search query that uses different words: the poem's own vocabulary, a character's name, or the event or place involved. Do not repeat a query already tried.

**Output:** an `AIMessage` with a `search_book` call (`id` `rewrite-<uuid>`), with `rewrites + 1` and `tool_rounds + 1`. The rewrite counts as a tool round, so the 6-round cap still holds.

**Fallback:** if the call is missing or malformed, the query becomes the question itself, with the previous query's words removed. If nothing is left after that, the run goes to `agent`.

## 7. Offline (scripted) model

The scripted model gets two more tool-bound rules, keyed on which tool the model is bound to (`bound_tool_names`):
- **`grade_passages`:** marks a passage relevant when it shares a content word with the question, using the existing `_content_words` and `_in_poem` rules.
- **`rewrite_search`:** returns a fixed rephrasing for known questions and otherwise the question's content words. The breakfast question, for example, is rewritten to "meal food eating at morning".

**The samples:**
- **Satan and the end of the poem:** grade relevant on the first pass, so the trace shows `grade` → `agent`.
- **"What did Milton eat for breakfast?":** the "Try this" example. It shows `grade` → `rewrite_query` → `tools` → `grade` twice, then `agent`, and the answer says the passages don't cover it.

**Builder note:** today, a scripted reply function receives only the messages, not the tools the model is bound to. Either give the reply function the bound tool names (a small change to `ScriptedChatModel`), or have the scripts recognise the grader and rewriter by their system prompts. Either is fine, as long as the agent's own rules are unaffected.

## 8. Studio

- **Layout:** the fixed layout adds `grade` and `rewrite_query`. The positions are left to the builder, but must meet two conditions. Every label and run count must be readable at 1440 px after the breakfast run. The `tools` → `grade` → `rewrite_query` → `tools` loop must read as a loop.
- **Edge labels:** for the new edges, as in §4.
- **Guide:** the Mapping section maps Grader → `grade` and Query rewriter → `rewrite_query`, replacing "not separate nodes". "Try this" covers the breakfast loop. The Framework concepts section notes that the grader and the rewriter use forced tool calls.

## 9. Testing

**Graph unit tests,** with a fake model and a fake library:
- The grader drops irrelevant passages, and the agent sees only the survivors.
- When nothing is relevant, `rewrite_query` runs and a new `search_book` follows.
- The rewrite cap of 2 holds, then the run goes to `agent`.
- A malformed grader reply passes the passages through.
- A `read_passage`-only round skips grading.
- `rewrites` resets for each question.
- Every conditional edge has a label.

**Offline:**
- The breakfast run's trace contains `grade`, `rewrite_query`, `grade`, `rewrite_query`, `grade`, `agent`, and the answer says "don't cover".
- The three samples still pass their source checks.
- No source in an answer cites a passage the grader dropped.

**Live:** Claude Haiku and DeepSeek both accept the forced `grade_passages` and `rewrite_search` calls. One question that is answered and one that isn't, on each model.

**Browser at 1440 px:** the layout after the breakfast run, with no console errors.

## 10. Calls made in this design (for the owner to check)

- **Forced tool calls** for the grader and the rewriter, rather than parsing JSON from text.
- **Same model as the agent.** No separate, cheaper grader.
- **Rewrite cap of 2 per question,** and each rewrite counts toward the 6-round cap.
- **A failing grader lets passages through** rather than dropping them.
- **`read_passage` results aren't graded.**
