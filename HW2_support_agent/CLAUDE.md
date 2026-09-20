# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A homework assignment (HW2 "Meridian"): a customer-support agent for a fictional Indian
electronics retailer, built with LangGraph. The skeleton runs end-to-end but several core
pieces are intentionally missing (`raise NotImplementedError`) — the assignment is to fill
them in. `README.md` and `RUBRIC.md` are the assignment spec; read them before changing scope
or grading-relevant behavior. Time is frozen at 2026-09-15 (`data/records/meta.json`) — always
get "today" via `Records.today()`, never `datetime.date.today()`.

## Commands

```bash
python scripts/check_env.py              # preflight: python version, packages, API key, index
python scripts/build_index.py --force    # (re)build the retrieval index — needed after changing
                                          # kb.py, chunking strategy, or handbook.md
python scripts/evaluate_dev.py           # run + score the dev set (24 queries), ~70 baseline
python scripts/evaluate_dev.py --retrieval-only   # score retrieval recall only, no LLM calls/cost
python scripts/evaluate_dev.py --workers 4 --show 10
python -m support_agent.app              # Gradio console at http://127.0.0.1:7860
python -m pytest tests -q                # contract tests — no LLM calls, keep these passing
python scripts/run_one.py "Can I return MRD-700028?" [--customer C-1001]   # single query, full trace
python scripts/run_batch.py --in data/test_queries.jsonl --out submission.jsonl --workers 4
python scripts/run_batch.py --resume     # continue a batch run that hit a rate limit
python -c "from support_agent.graph import draw; draw()"   # ASCII/mermaid render of the graph
make help                                # lists Makefile shortcuts for all of the above
```

Run a single test: `python -m pytest tests/test_contract.py::test_name -q`.

Config can be overridden via env vars without editing files, e.g.
`RETRIEVAL_MODE=hybrid TOP_K=6 python scripts/evaluate_dev.py`. See `support_agent/config.py`
for every setting (models, retrieval mode, chunking, refund limit, tool-loop cap, etc.).

Requires Python 3.10+ (3.11 recommended); `pip install -r requirements.txt`;
`cp .env.example .env` with an `OPENROUTER_API_KEY`. Every LLM call is disk-cached under
`.cache/llm/`, so re-running the same input is nearly free — delete `.cache/` for fresh answers.
`make clean` drops `.index`, `.cache`, and run artifacts.

## Architecture

**Flow (`support_agent/graph.py`, LangGraph `StateGraph`):** the shipped graph is a straight
line `lookup -> retrieve -> respond -> END` and is not agentic — `lookup` is just a regex for
order IDs. The assignment's target flow is:

```
(start) --> triage --+--> retrieve --> act --(loop)--> verify --> respond --> (end)
              |                          ^      |
              +--> clarify               +------+
              +--> escalate ------------------------> (end)
```

`triage` routes each message (answer / ask a clarifying question / hand to a human), `act` is
the tool-calling loop (ask model -> run requested tool -> feed result back -> repeat, bounded by
`config.MAX_TOOL_STEPS`), `verify` checks the drafted answer is actually supported by retrieved
text before it goes out. Branching uses `add_conditional_edges`; conversation memory and a
human-approval pause use `compile(checkpointer=MemorySaver(), interrupt_before=["act"])`.

**State (`support_agent/state.py`):** a single `TypedDict` threaded through every node. Fields
annotated `Annotated[list, operator.add]` (`messages`, `steps`) accumulate across loop
iterations; everything else is overwritten on each node's return. Getting this annotation wrong
silently drops information on the next pass through the tool loop.

**Retrieval pipeline:** `kb.py` loads `data/kb/handbook.md`, splits it on `##` headings into
`Section`s (each carrying an `id` used as the citation key, plus `status`/`trust` metadata from
an HTML-comment line right under the heading), then `chunk_documents` cuts sections into
`Chunk`s via a pluggable strategy (`fixed` cuts every N characters ignoring structure; the
intended `structured` strategy respects heading boundaries). `index.py` embeds chunks into
Chroma (default ONNX MiniLM embedder, CPU-only, no torch). `retrieval.py`'s `Retriever` exposes
`dense` (embedding search, works), `lexical` (BM25), and `hybrid` (RRF merge of the two,
`config.RRF_K`) modes, selected by `RETRIEVAL_MODE`; `postprocess` is where the two trap
sections get demoted/dropped/kept-but-unciteable per `config.UNTRUSTED_DOCS` /
`SUPERSEDED_DOCS`. `get_retriever()` is a process-wide singleton (index load is slow).

**Tools (`support_agent/tools.py`):** each tool is a plain function wrapped with
`@tool` and closed over a per-conversation `ToolContext` (`records`, `retriever`, `actions` log,
`hits`). Read tools (`get_order`, `list_customer_orders`, `get_ticket_history`,
`check_return_eligibility`, `search_knowledge_base`) hit `records.py` / the retriever directly.
Write tools (`create_return`, `cancel_order`, `issue_refund`, `issue_wallet_credit`) never touch
disk — they go through `_guarded`, which calls `policy.requires_approval` and either logs a
`blocked` entry (human must approve) or an `executed` one with a fabricated success message.
`escalate_to_human` always executes and produces the handover packet. **Tool names and argument
names are part of the grading contract — do not rename them**; `tests/test_contract.py` pins
this down. `ctx.actions` is exactly what ends up in the submitted trace.

**Policy (`support_agent/policy.py`):** business rules pre-implemented as pure functions —
return-window arithmetic, refund-approval thresholds (over the configured limit, or return
window already closed), and keyword-based escalation triggers (safety, legal, privacy/DPDP,
account compromise, bulk/business, repeat-ticket). None of this fires until wired into the graph
in `node_act`/routing. `wrap_untrusted` fences text from the KB or tickets so the model is told
(not guaranteed) to treat it as data, not instructions — the stronger defenses (keyword
detection, and taking the *authority* itself out of the model's hands via `requires_approval`)
are the assignment's security piece.

**Records (`support_agent/records.py`):** a read-only fake DB over `data/records/*.json` — one
customer, her orders, her tickets. `Records.today()` returns the frozen date; never substitute
the real clock.

**Facade (`support_agent/agent.py`):** `SupportAgent.resolve()` is the single entry point used
by `scripts/run_batch.py`, the Gradio app, and tests — it builds a fresh `SupportGraph` per
query (reusing the singleton retriever), runs it, and wraps the result into the trace format via
`trace.build`. Keep new entry points going through this facade rather than constructing
`SupportGraph` directly, so the three callers don't drift apart. `resume()` is where
human-approve/reject from the web app feeds back into a paused graph
(`get_state` / `update_state` / `invoke(None, cfg)`).

**Trace/output contract:** every resolved query becomes one JSON record with
`query_id, route (resolved|needs_info|escalated), answer, citations, actions, escalation`,
validated by `trace.validate`. `evalkit/metrics.py` is the (non-secret) scoring script:
ending 25%, actions 35%, facts 25%, sources 15%, with two hard rules — a wrong action on a
safety-critical query zeroes that query regardless of the reply text, and citing a trap section
(`community`, `archive_returns_2024`) zeroes the sources component for that query. Only actions
the code actually *executed* count against you; a `blocked` write is the guardrail succeeding.

## Working within the assignment constraints

- Data under `data/` (`handbook.md`, `records/*.json`, `dev_gold.jsonl`, `test_queries.jsonl`)
  must not be edited — it's the fixed spec/answer key the grader checks against.
- Don't special-case behavior by `query_id` or hand-author answers; everything must come from
  the program actually running (`test_every_order_id_mentioned_anywhere_actually_exists` and
  similar contract tests exist partly to catch drift like this).
- When changing retrieval/chunking, measure with `evaluate_dev.py --retrieval-only` (no LLM
  cost) and change one variable at a time so the effect of chunking vs. search strategy can be
  isolated.
- `tests/test_contract.py` is the regression floor for anything the grader depends on (tool
  names/args, trace schema, policy numbers, section metadata) — keep it green while refactoring.
