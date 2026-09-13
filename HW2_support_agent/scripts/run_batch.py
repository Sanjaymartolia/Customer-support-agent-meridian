#!/usr/bin/env python3
"""Run the agent over a whole query file and write the submission traces.

    python scripts/run_batch.py --in data/dev_queries.jsonl  --out dev_traces.jsonl
    python scripts/run_batch.py --in data/test_queries.jsonl --out submission.jsonl

`submission.jsonl` produced by this script is exactly what you upload. Resumable:
rerun with --resume and it skips query_ids already present in the output file, so
a rate-limit blowup halfway through costs you nothing.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from support_agent import llm, trace  # noqa: E402
from support_agent.agent import SupportAgent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(ROOT / "data" / "test_queries.jsonl"))
    ap.add_argument("--out", dest="out", default=str(ROOT / "submission.jsonl"))
    ap.add_argument("--limit", type=int, default=0, help="first N queries only")
    ap.add_argument("--workers", type=int, default=4, help="parallel queries")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--keep-debug", action="store_true",
                    help="keep _debug in the output (never submit that file)")
    a = ap.parse_args()

    queries = trace.read_jsonl(a.inp)
    if a.limit:
        queries = queries[:a.limit]

    done = {}
    out_path = Path(a.out)
    if a.resume and out_path.exists():
        done = {r["query_id"]: r for r in trace.read_jsonl(out_path)}
        print(f"resuming: {len(done)} already done")
    todo = [q for q in queries if q["query_id"] not in done]

    agent = SupportAgent()
    started = time.time()
    results, failures = dict(done), 0

    def work(q):
        return q["query_id"], agent.resolve(q)

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        for i, (qid, rec) in enumerate(pool.map(work, todo), 1):
            if not a.keep_debug:
                rec.pop("_debug", None)
            results[qid] = rec
            if rec["route"] is None:
                failures += 1
            print(f"[{i}/{len(todo)}] {qid:<10} {rec['route']:<10} "
                  f"{rec['meta'].get('latency_s', 0):>5.1f}s  "
                  f"{(rec['answer'] or '')[:60]!r}")

    ordered = [results[q["query_id"]] for q in queries if q["query_id"] in results]
    for r in ordered:
        trace.validate(r, known_ids={q["query_id"] for q in queries})
    trace.write_jsonl(out_path, ordered)

    usage = llm.usage_snapshot()
    print(f"\nwrote {len(ordered)} traces -> {out_path}")
    print(f"{time.time() - started:.0f}s wall · {usage['calls']} live LLM calls · "
          f"{usage['cached']} cache hits · "
          f"{usage['prompt_tokens'] + usage['completion_tokens']} tokens")
    if failures:
        print(f"WARNING: {failures} queries produced no route")


if __name__ == "__main__":
    main()
