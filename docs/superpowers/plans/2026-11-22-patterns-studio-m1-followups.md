# Patterns Studio M1: follow-ups for the M2 and M3 plans

Milestone 1 (Core) is complete on `feature/patterns-studio`. The whole-branch review is clean after one fix wave, and 82 tests pass. The task reviews and the final review deferred the items below. Fold them into the next plans' Global Constraints, Review Focus or tasks.

## Carry into the M2 plan (patterns 5–7)

- **`to_jsonable`:** map `NaN`/`inf` to `null`. Reflection scores could otherwise produce invalid JSON in the SSE stream.
- **`to_jsonable`:** two-string lists such as `["user", "hi"]` are turned into messages. Re-check this once Plan-and-Execute stores plans as lists.
- **`ScriptedChatModel`:** add `bind_tools` and `with_structured_output`. Add tests for callable rules, multi-turn matching and the pacing path. Also add tests for runner early-close and for `tool_call`/`tool_result`/`usage` aggregation, which ReAct exercises.
- **Guide:** add a test enforcing the "Key code ≤ 25 lines" rule for the three new `explanation.md` files.
- **UI:** a failed pattern switch leaves the previous pattern's chrome on screen, with the error shown in the guide body.
- **Spec §4.7:** ReAct tool-call chips will rely on the runner's `tool_call`/`tool_result` events. Those events are implemented, but no live tool-calling pattern has exercised them yet.

## Carry into the M3 plan (Live mode, hardening, deploy)

- **Live models:** list-of-block content and tokens. The runner now uses `text_of`; verify this with real `ChatAnthropic` streaming when tools are bound.
- **Runner deadline:** `aget_state` and `output(...)` run outside the 90 s deadline.
- **Timed-out sync nodes** keep their executor threads until they finish. Account for this in the load test.
- **Priming:** it is not counted in the session run slot, and a cancelled priming leaks its `ThreadStore` record. Address both with rate limits and session expiry.
- **Lifespan:** setup has no cleanup on failure (aiosqlite connection and executor).
- **Unbounded growth:** the in-memory `ThreadStore` and the SQLite file both grow without limit, because every trigger run creates a thread. Covered by the 24 h cleanup and session expiry.
- **`GET /state` checkpoint count** deserializes the full history, O(n) per call. Count rows with `checkpointer.alist` instead, or cap the count.
- **`__main__`:** host and port are hard-coded to `127.0.0.1:8000`. Read them from the environment for Docker.
- **Accessibility pass:** `aria-controls` on the tabs points at a non-tabpanel. Screen-reader output still needs a human check.
- **`once()` wiring** inside `run_thread` is only tested indirectly. The load test covers it.

## Known limitations accepted in M1

- A run cut mid-stream closes its thread, and the user must start a New chat (ruling R6). The same applies to a response that never started streaming.
- After two guardrail refusals in a row, a reload shows only one placeholder/refusal pair, because `refusal` is a single state field.
- New chat clicked while a thread is still being primed orphans the first server thread. This is harmless.
- While a run is in progress, the trace caption shows "paused at ask" until the refresh after the run.
- The guide fence parser doesn't handle info strings on closing fences, and the guide layout CSS depends on heading text.
