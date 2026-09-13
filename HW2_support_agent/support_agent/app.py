"""Gradio console for the Meridian support agent.

    python -m support_agent.app          # http://127.0.0.1:7860

Three tabs:

  Support console   talk to the agent and watch the trace it produced — route,
                    citations, every tool call, the retrieved chunks, the cost
  Retrieval lab     query the index directly, with scores and metadata, so you
                    can debug retrieval without paying for generation
  Evaluation        run the dev set and see the scorecard the grader will use

The right-hand trace panel is the point of this app. A support agent that gives
a plausible answer and cannot show you *why* is not shippable; the panel is how
you (and a reviewer) see the difference between an answer that was retrieved and
one that was invented.

The Approve / Reject buttons call `SupportAgent.resume()` — TODO 6c. Wiring that up
is the human-in-the-loop story end to end. Streaming the graph with
`graph.stream(...)` so nodes light up as they run is optional polish.
"""

import json
import time

import gradio as gr

from . import config, trace
from .agent import SupportAgent
from .graph import as_text
from .records import get_records
from .retrieval import get_retriever

ROUTE_STYLE = {
    "resolved": ("#0f7b3f", "RESOLVED"),
    "needs_info": ("#8a6d00", "NEEDS INFO"),
    "escalated": ("#a02020", "ESCALATED"),
}
STATUS_ICON = {"executed": "OK", "blocked": "BLOCKED", "failed": "FAILED"}


def _customer_choices(records):
    """One test customer, plus the anonymous session the `missing_info` cases use."""
    c = records.customer
    return [f"{c['customer_id']} · {c['name']} · {c['tier']} · "
            f"{len(records.orders_for_customer())} orders",
            "(not signed in)"]


def _cid(choice):
    return None if not choice or choice.startswith("(") else choice.split(" · ")[0]


def _route_html(route, meta):
    colour, label = ROUTE_STYLE.get(route, ("#555", str(route).upper()))
    path = " → ".join(meta.get("graph_path", [])) or "—"
    return (f"<div style='display:flex;gap:.75rem;align-items:center;flex-wrap:wrap'>"
            f"<span style='background:{colour};color:#fff;padding:.2rem .6rem;"
            f"border-radius:.35rem;font-weight:600;font-size:.85rem'>{label}</span>"
            f"<code style='font-size:.8rem'>{path}</code>"
            f"<span style='opacity:.7;font-size:.8rem'>"
            f"{meta.get('llm_calls', 0)} LLM calls · {meta.get('latency_s', 0)}s · "
            f"{meta.get('tokens', 0)} tokens · {meta.get('retrieval_mode', '')}</span></div>")


def _actions_rows(actions):
    return [[STATUS_ICON.get(a.get("status"), a.get("status", "")), a.get("tool", ""),
             json.dumps(a.get("args", {}), ensure_ascii=False)[:160],
             a.get("reason", "")] for a in actions or []] or [["", "(no tool calls)", "", ""]]


def _hits_rows(hits):
    return [[h.get("doc_id", ""), h.get("status", ""), f"{h.get('score', 0):.3f}",
             (h.get("text", "") or "").strip().replace("\n", " ")[:180]]
            for h in hits or []] or [["", "", "", "(nothing retrieved)"]]


def _chatbot(**kw):
    """Gradio 5 needs type="messages"; Gradio 6 removed the argument and made it
    the only format. Build for whichever the student installed."""
    try:
        return gr.Chatbot(type="messages", **kw)
    except TypeError:
        return gr.Chatbot(**kw)


def build_ui():
    records = get_records()
    agent = SupportAgent()
    session = {"thread": f"ui-{int(time.time())}"}

    with gr.Blocks(title="Meridian Support Agent", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            f"## Meridian Support Agent\n"
            f"Simulated present: **{records.today().isoformat()}** · "
            f"{records.customer['name']} ({records.customer['tier']}) · "
            f"{len(records.orders)} orders · model `{config.TOOL_MODEL}` · "
            f"retrieval `{config.RETRIEVAL_MODE}`")

        with gr.Tab("Support console"):
            with gr.Row():
                with gr.Column(scale=3):
                    customer = gr.Dropdown(_customer_choices(records),
                                           value=_customer_choices(records)[0],
                                           label="Signed in as")
                    chat = _chatbot(height=420, label="Conversation")
                    msg = gr.Textbox(placeholder="Ask the agent something…",
                                     label="Message", lines=2)
                    with gr.Row():
                        send = gr.Button("Send", variant="primary")
                        clear = gr.Button("New conversation")
                    gr.Examples(
                        label="Try one of these",
                        examples=[
                            ["Can I still return order MRD-700100?"],
                            ["Can I still return order MRD-700121?"],
                            ["Please cancel order MRD-700175."],
                            ["Please cancel order MRD-700184."],
                            ["What is error ERR-4021 and is my money gone?"],
                            ["The battery on MRD-700163 has swollen and smells burnt."],
                            ["I want a full refund of 34999 rupees on MRD-700136."],
                            ["I want to return my order."],
                            ["We need 20 units of the Meridian Slate 14 for our office."]],
                        inputs=msg)

                with gr.Column(scale=2):
                    gr.Markdown("### Agent trace")
                    route_box = gr.HTML()
                    cites = gr.Textbox(label="Citations", interactive=False)
                    actions = gr.Dataframe(
                        headers=["status", "tool", "args", "reason"],
                        col_count=(4, "fixed"), label="Tool calls", wrap=True, interactive=False)
                    with gr.Accordion("Pending human approval", open=False):
                        approval = gr.Markdown("No action is waiting for approval.")
                        with gr.Row():
                            approve = gr.Button("Approve", variant="primary", size="sm")
                            reject = gr.Button("Reject", size="sm")
                        approval_out = gr.Markdown()
                    with gr.Accordion("Retrieved context", open=False):
                        hits = gr.Dataframe(headers=["doc_id", "status", "score", "text"],
                                            col_count=(4, "fixed"), wrap=True, interactive=False)
                    with gr.Accordion("Raw trace (JSON)", open=False):
                        raw = gr.JSON()

        with gr.Tab("Retrieval lab"):
            gr.Markdown("Query the index directly — no generation, no cost. This is where "
                        "you find out whether a wrong answer was a retrieval failure or a "
                        "generation failure.")
            rq = gr.Textbox(label="Query", value="ERR-4021")
            rk = gr.Slider(1, 12, value=config.TOP_K, step=1, label="top k")
            rbtn = gr.Button("Search", variant="primary")
            rout = gr.Dataframe(headers=["doc_id", "status", "score", "text"],
                                col_count=(4, "fixed"), wrap=True, interactive=False)

        with gr.Tab("Evaluation"):
            gr.Markdown("Run the labelled dev set and score it exactly the way the grader "
                        "will. Start with 8 queries while you iterate; run all 24 before "
                        "you decide anything.")
            n_dev = gr.Slider(4, 24, value=8, step=2, label="how many dev queries")
            ebtn = gr.Button("Run evaluation", variant="primary")
            ereport = gr.Textbox(label="Scorecard", lines=22, interactive=False)

        # ------------------------------------------------------------ handlers --
        def on_send(message, history, customer_choice):
            message = (message or "").strip()
            if not message:
                return history, "", "", [], [], None, "No action is waiting for approval."
            history = list(history or [])
            # Gradio hands content back as a string most of the time, but as a list
            # of parts for some message kinds. Flatten it before it reaches the agent.
            prior = [{"role": m.get("role", "user"), "content": as_text(m.get("content"))}
                     for m in history]
            history.append({"role": "user", "content": message})

            record = {"query_id": session["thread"], "query": message,
                      "customer_id": _cid(customer_choice), "history": prior}
            result = agent.resolve(record, thread_id=session["thread"])
            debug = result.pop("_debug", {})
            history.append({"role": "assistant", "content": result["answer"]
                            or "(the agent produced no answer)"})

            waiting = [a for a in result["actions"] if a.get("status") == "blocked"]
            note = ("No action is waiting for approval." if not waiting else
                    "\n".join(f"- **{a['tool']}** `{json.dumps(a['args'])}` — "
                              f"blocked: _{a.get('reason', '')}_" for a in waiting))
            return (history, "", ", ".join(result["citations"]) or "(none)",
                    _actions_rows(result["actions"]), _hits_rows(debug.get("hits")),
                    result, note)

        def on_send_full(message, history, customer_choice):
            h, m, c, a, hh, r, note = on_send(message, history, customer_choice)
            meta = (r or {}).get("meta", {})
            return h, m, _route_html((r or {}).get("route", ""), meta), c, a, hh, r, note

        send.click(on_send_full, [msg, chat, customer],
                   [chat, msg, route_box, cites, actions, hits, raw, approval])
        msg.submit(on_send_full, [msg, chat, customer],
                   [chat, msg, route_box, cites, actions, hits, raw, approval])

        def on_clear():
            session["thread"] = f"ui-{int(time.time() * 1000)}"
            return [], "", "", [], [], None, "No action is waiting for approval."

        clear.click(on_clear, None,
                    [chat, route_box, cites, actions, hits, raw, approval])

        def on_decision(decide):
            def handler():
                try:
                    agent.resume(session["thread"], approved=decide)
                    return f"Resumed the graph with approved={decide}."
                except NotImplementedError:
                    return ("`SupportAgent.resume()` is not implemented yet. Compile the "
                            "graph with a checkpointer and `interrupt_before=[...]`, then "
                            "call `graph.invoke(None, cfg)` to continue from the interrupt "
                            "— see the TODO in `support_agent/agent.py`.")
                except Exception as e:                       # noqa: BLE001
                    return f"resume() raised {type(e).__name__}: {e}"
            return handler

        approve.click(on_decision(True), None, approval_out)
        reject.click(on_decision(False), None, approval_out)

        def on_search(query, k):
            return _hits_rows([{"doc_id": h.doc_id, "status": h.metadata.get("status", ""),
                                "score": h.score, "text": h.text}
                               for h in get_retriever().search(query, k=int(k))])

        rbtn.click(on_search, [rq, rk], rout)

        def on_eval(n):
            from concurrent.futures import ThreadPoolExecutor
            from evalkit import metrics
            queries = trace.read_jsonl(config.DATA / "dev_queries.jsonl")[:int(n)]
            golds = trace.read_jsonl(config.DATA / "dev_gold.jsonl")[:int(n)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                preds = list(pool.map(agent.resolve, queries))
            for p in preds:
                p.pop("_debug", None)
            return metrics.format_report(metrics.score_all(preds, golds), show_rows=6)

        ebtn.click(on_eval, n_dev, ereport)

    return demo


def main():
    build_ui().launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
