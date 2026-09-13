"""The ten things the agent can do.

A "tool" is just a Python function the model is allowed to ask for. The model
never runs code itself. It says "please call get_order with MRD-700121", your
program runs that, and you hand the result back.

Two kinds here:

  * Looking things up — these read `records.py` and return what they find.
  * Doing things — starting a return, refunding money, calling a human. These do
    not really change anything. They write a line into `ctx.actions` saying what
    would have happened, and that list becomes your submitted trace. Nothing on
    disk is ever modified, so you can run the same question twice and compare.

**Do not rename these functions or their arguments.** The marking script looks for
`{"tool": "create_return", "args": {"order_id": ...}}` exactly as written. If you
call it `orderId`, you lose the marks even though the agent did the right thing.
Adding new tools of your own is fine and encouraged.
"""

import json

from langchain_core.tools import tool

from . import policy, retrieval
from .records import get_records


class ToolContext:
    """Per-conversation scratchpad shared by every tool call."""

    def __init__(self, customer_id=None, records=None, retriever=None):
        self.records = records or get_records()
        self.retriever = retriever or retrieval.get_retriever()
        self.customer_id = customer_id
        self.actions = []        # [{tool, args, status, result?, reason?}]
        self.hits = []           # every Hit the KB tool returned, in order

    def log(self, tool_name, args, status, result=None, reason=""):
        entry = {"tool": tool_name, "args": args, "status": status}
        if result is not None:
            entry["result"] = result
        if reason:
            entry["reason"] = reason
        self.actions.append(entry)
        return entry

    def executed(self, tool_name=None):
        return [a for a in self.actions
                if a["status"] == "executed" and (tool_name is None or a["tool"] == tool_name)]


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def make_tools(ctx):
    """Build the tool objects bound to one ToolContext. Returns a list."""

    @tool
    def search_knowledge_base(query: str) -> str:
        """Search Meridian's policy, FAQ and troubleshooting documents. Use this
        for any question about policies, timelines, fees, eligibility rules or
        troubleshooting. Returns numbered passages with their doc_id."""
        hits = ctx.retriever.search(query)
        ctx.hits.extend(hits)
        ctx.log("search_knowledge_base", {"query": query}, "executed",
                result=[h.doc_id for h in hits])
        return policy.wrap_untrusted("knowledge_base", retrieval.format_context(hits))

    @tool
    def get_order(order_id: str) -> str:
        """Look up one order (format MRD-XXXXXX): status, items and their
        categories, totals, payment method, the delivery date, how many days ago
        that was, and the customer's membership tier. Call this before answering
        anything about a specific order."""
        o = ctx.records.get_order(order_id)
        if not o:
            ctx.log("get_order", {"order_id": order_id}, "failed", reason="not_found")
            return f"No order found with id {order_id!r}."
        ctx.log("get_order", {"order_id": o["order_id"]}, "executed", result=o["status"])
        view = dict(o)
        # everything the return-window rules need, in one call
        view["today"] = ctx.records.today().isoformat()
        view["days_since_delivery"] = ctx.records.days_since(o.get("delivered_at"))
        view["customer_tier"] = ctx.records.tier(o["customer_id"])
        view["belongs_to_this_customer"] = ctx.records.owns_order(ctx.customer_id, order_id)
        return _json(view)

    @tool
    def list_customer_orders(customer_id: str, status: str = "") -> str:
        """List a customer's orders, most recent first, optionally filtered by
        status. Use this when the customer says "my order" without saying which."""
        orders = ctx.records.orders_for_customer(
            customer_id, statuses=[status] if status else None)
        ctx.log("list_customer_orders", {"customer_id": customer_id, "status": status},
                "executed", result=len(orders))
        brief = [{"order_id": o["order_id"], "status": o["status"],
                  "delivered_at": o["delivered_at"], "total_inr": o["total_inr"],
                  "items": [i["name"] for i in o["items"]]} for o in orders[:10]]
        return _json(brief) if brief else "This customer has no orders."

    @tool
    def get_ticket_history(customer_id: str) -> str:
        """This customer's past support tickets. Check it before troubleshooting:
        someone who has raised the same issue three times must not get a fourth
        script."""
        ts = ctx.records.tickets_for_customer(customer_id)
        ctx.log("get_ticket_history", {"customer_id": customer_id}, "executed", result=len(ts))
        brief = [{"ticket_id": t["ticket_id"], "order_id": t["order_id"],
                  "issue_type": t["issue_type"], "status": t["status"],
                  "created_at": t["created_at"], "notes": t["notes"]} for t in ts]
        return policy.wrap_untrusted("ticket_notes", _json(brief)) if brief \
            else "No previous tickets for this customer."

    @tool
    def check_return_eligibility(order_id: str) -> str:
        """Can this order still be returned? Computes the window from the item
        category and the customer's tier and compares it with the delivery date."""
        o = ctx.records.get_order(order_id)
        if not o:
            ctx.log("check_return_eligibility", {"order_id": order_id}, "failed")
            return f"No order found with id {order_id!r}."
        tier = ctx.records.tier(o["customer_id"])
        lines, eligible_any = [], False
        for item in o["items"]:
            window = policy.return_window_days(item["category"], tier)
            if window == 0:
                lines.append({"sku": item["sku"], "eligible": False,
                              "reason": f"{item['category']} is non-returnable"})
                continue
            if o["status"] != "delivered" or not o["delivered_at"]:
                lines.append({"sku": item["sku"], "eligible": False,
                              "reason": f"order status is {o['status']}, not delivered"})
                continue
            elapsed = ctx.records.days_since(o["delivered_at"])
            deadline = policy.return_deadline(o["delivered_at"], item["category"], tier)
            ok = elapsed <= window
            eligible_any = eligible_any or ok
            lines.append({"sku": item["sku"], "eligible": ok, "window_days": window,
                          "days_since_delivery": elapsed, "deadline": deadline.isoformat(),
                          "reason": (f"{tier} customer, {item['category']}: {window}-day "
                                     f"window, delivered {elapsed} days ago")})
        ctx.log("check_return_eligibility", {"order_id": o["order_id"]}, "executed",
                result=eligible_any)
        return _json({"order_id": o["order_id"], "customer_tier": tier,
                      "today": ctx.records.today().isoformat(), "items": lines})

    def _guarded(tool_name, args, do):
        """Run a write action unless policy says a human must approve it first."""
        needs, reason = policy.requires_approval(tool_name, args, ctx)
        if needs:
            ctx.log(tool_name, args, "blocked", reason=reason)
            return (f"BLOCKED: {tool_name} requires human approval ({reason}). "
                    f"Do not tell the customer it is done. Escalate instead.")
        result = do()
        ctx.log(tool_name, args, "executed", result=result)
        return result

    @tool
    def create_return(order_id: str, sku: str = "", reason: str = "") -> str:
        """Raise a return request. Only after confirming the order is inside its
        return window."""
        return _guarded("create_return", {"order_id": order_id, "sku": sku, "reason": reason},
                        lambda: f"Return raised for {order_id}; pickup within 2 business days.")

    @tool
    def cancel_order(order_id: str, reason: str = "") -> str:
        """Cancel an order. Only valid while its status is 'placed' or 'packed'."""
        return _guarded("cancel_order", {"order_id": order_id, "reason": reason},
                        lambda: f"Order {order_id} cancelled. Refund initiated.")

    @tool
    def issue_refund(order_id: str, amount_inr: float, reason: str = "") -> str:
        """Refund money to the original payment method. Subject to the agent
        authority limit in the returns policy."""
        return _guarded("issue_refund",
                        {"order_id": order_id, "amount_inr": amount_inr, "reason": reason},
                        lambda: f"Refund of {amount_inr} INR issued on {order_id}.")

    @tool
    def issue_wallet_credit(customer_id: str, amount_inr: float, reason: str = "") -> str:
        """Credit the Meridian Wallet — goodwill gestures, missed-SLA
        compensation. Same authority limit as a refund."""
        return _guarded("issue_wallet_credit",
                        {"customer_id": customer_id, "amount_inr": amount_inr,
                         "reason": reason},
                        lambda: f"{amount_inr} INR credited to {customer_id}'s wallet.")

    @tool
    def escalate_to_human(priority: str, reason_code: str, summary: str) -> str:
        """Hand the conversation to a human. priority is P1 (safety, account
        compromise), P2 (money at risk, legal, privacy, repeat failure) or P3
        (everything else a human must do). The summary must let the human act
        without re-reading the transcript."""
        args = {"priority": priority, "reason_code": reason_code, "summary": summary}
        ctx.log("escalate_to_human", args, "executed")
        return (f"Escalated at {priority} ({reason_code}). A human will pick this up; "
                f"the queue is staffed 09:00-21:00 IST.")

    return [search_knowledge_base, get_order, list_customer_orders, get_ticket_history,
            check_return_eligibility, create_return, cancel_order, issue_refund,
            issue_wallet_credit, escalate_to_human]
