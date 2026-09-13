#!/usr/bin/env python3
"""Run a single query and print the whole trace. Your inner development loop.

    python scripts/run_one.py "Can I still return MRD-700100?" --customer C-1001
    python scripts/run_one.py --query-id dev-011          # replay a dev query
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from support_agent import trace  # noqa: E402
from support_agent.agent import SupportAgent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("--customer", default=None)
    ap.add_argument("--query-id", default=None, help="replay a query from dev_queries.jsonl")
    ap.add_argument("--json", action="store_true", help="print the raw trace")
    a = ap.parse_args()

    if a.query_id:
        rows = trace.read_jsonl(ROOT / "data" / "dev_queries.jsonl")
        record = next((r for r in rows if r["query_id"] == a.query_id), None)
        if record is None:
            raise SystemExit(f"no such query_id: {a.query_id}")
    elif a.query:
        record = {"query_id": "adhoc", "query": a.query,
                  "customer_id": a.customer, "history": []}
    else:
        raise SystemExit("give a query string or --query-id")

    result = SupportAgent().resolve(record)
    debug = result.pop("_debug", {})

    if a.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\nQ ({record['query_id']}, customer={record.get('customer_id')}): "
          f"{record['query']}\n")
    print(f"route      {result['route']}")
    print(f"answer     {result['answer']}\n")
    print(f"citations  {result['citations']}")
    print("actions:")
    for act in result["actions"] or ["  (none)"]:
        print(f"  {act['status']:9s} {act['tool']}({json.dumps(act.get('args', {}))})"
              if isinstance(act, dict) else act)
    if result.get("escalation"):
        print(f"escalation {result['escalation']}")
    print(f"\nretrieved  {[h['doc_id'] for h in debug.get('hits', [])]}")
    print(f"path       {' -> '.join(result['meta'].get('graph_path', []))}")
    print(f"meta       {result['meta'].get('llm_calls')} llm calls, "
          f"{result['meta'].get('latency_s')}s")


if __name__ == "__main__":
    main()
