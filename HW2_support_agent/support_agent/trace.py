"""What you submit, and exactly what shape it must be.

One line of JSON per customer message, in a file called `submission.jsonl`.

This file is all we look at. We never run your code, so if your agent did
something clever and it is not written down here, it did not happen as far as
your mark is concerned.

    {
      "query_id":  "test-001",
      "route":     "resolved" | "needs_info" | "escalated",
      "answer":    "the reply shown to the customer",
      "citations": ["returns", "membership"],
      "actions":   [{"tool": "get_order",
                     "args": {"order_id": "MRD-700100"},
                     "status": "executed"}],
      "escalation": {"priority": "P2", "reason_code": "...", "summary": "..."} | null,
      "meta":      {"latency_s": 2.9, "llm_calls": 3, ...}
    }

`status` on each action is one of three words:

    "executed"   the tool ran
    "blocked"    your own safety check stopped it. This is a GOOD result when the
                 action needed a human's approval
    "failed"     the tool was called but errored

Only "executed" actions are counted, both for actions you should have taken and
for actions you must not take. So a refund your safety check blocked never counts
against you — that is the safety check doing its job.
"""

import json

from . import config

REQUIRED_FIELDS = ("query_id", "route", "answer", "citations", "actions")


class TraceError(ValueError):
    """Format problem in a trace; the message is safe to show to a student."""


def build(query_id, route, answer, citations=(), actions=(), escalation=None, meta=None):
    return {
        "query_id": query_id,
        "route": route,
        "answer": answer or "",
        "citations": sorted({c for c in citations if isinstance(c, str) and c.strip()}),
        "actions": [normalise_action(a) for a in actions],
        "escalation": escalation,
        "meta": meta or {},
    }


def normalise_action(a):
    return {"tool": str(a.get("tool", "")),
            "args": {k: v for k, v in (a.get("args") or {}).items()},
            "status": a.get("status", "executed"),
            **({"reason": a["reason"]} if a.get("reason") else {})}


def validate(record, known_ids=None):
    """Raise TraceError if this record would be rejected at submission time."""
    for f in REQUIRED_FIELDS:
        if f not in record:
            raise TraceError(f"missing field {f!r}")
    if record["route"] not in config.ROUTES:
        raise TraceError(f"route must be one of {config.ROUTES}, got {record['route']!r}")
    if known_ids is not None and record["query_id"] not in known_ids:
        raise TraceError(f"unknown query_id {record['query_id']!r}")
    if not isinstance(record["citations"], list):
        raise TraceError("citations must be a list of doc_id strings")
    if not isinstance(record["actions"], list):
        raise TraceError("actions must be a list of {tool, args, status} objects")
    for a in record["actions"]:
        if not isinstance(a, dict) or "tool" not in a:
            raise TraceError(f"bad action entry: {a!r}")
        if a.get("status") not in ("executed", "blocked", "failed"):
            raise TraceError(f"action status must be executed/blocked/failed: {a!r}")
    esc = record.get("escalation")
    if esc is not None:
        if not isinstance(esc, dict):
            raise TraceError("escalation must be an object or null")
        if esc.get("priority") not in config.PRIORITIES:
            raise TraceError(f"escalation.priority must be one of {config.PRIORITIES}")
    return True


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise TraceError(f"line {lineno} is not valid JSON: {e}") from e
    return out
