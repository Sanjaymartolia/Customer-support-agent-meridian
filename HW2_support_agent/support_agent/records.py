"""The company's database: one customer, her orders, her support tickets.

Nothing here is ever written to. The action tools in `tools.py` only pretend to
change things, and write a note into the trace instead, so running the same
question twice always gives you a comparable result.

**Always use `today()` for dates, never Python's `date.today()`.** Time in this
homework is frozen at 15 September 2026, which is stored in
`data/records/meta.json`. If you use the real date, every answer about return
deadlines will be wrong, and it will drift one day further wrong every day.
"""

import json
from datetime import date

from . import config


class Records:
    def __init__(self, directory=None):
        d = directory or config.RECORDS_DIR
        load = lambda name: json.loads((d / name).read_text(encoding="utf-8"))  # noqa: E731
        self.meta = load("meta.json")
        self.customer = load("customer.json")
        self.orders = {o["order_id"]: o for o in load("orders.json")}
        self.tickets = load("tickets.json")

    # ------------------------------------------------------------------ time --
    def today(self):
        """The simulated present. Never use date.today() instead of this."""
        return date.fromisoformat(self.meta["as_of"])

    def days_since(self, iso_date):
        return None if not iso_date else (self.today() - date.fromisoformat(iso_date)).days

    # --------------------------------------------------------------- lookups --
    def get_order(self, order_id):
        return self.orders.get((order_id or "").strip().upper())

    def get_customer(self, customer_id=None):
        if customer_id and customer_id.strip().upper() != self.customer["customer_id"]:
            return None
        return self.customer

    def orders_for_customer(self, customer_id=None, statuses=None):
        out = [o for o in self.orders.values()
               if self.get_customer(customer_id) is not None]
        if statuses:
            out = [o for o in out if o["status"] in statuses]
        return sorted(out, key=lambda o: o["placed_at"], reverse=True)

    def tier(self, customer_id=None):
        """'plus' or 'standard' — decides the return window on everything except
        large appliances."""
        c = self.get_customer(customer_id)
        return c["tier"] if c else "standard"

    def tickets_for_customer(self, customer_id=None):
        if self.get_customer(customer_id) is None:
            return []
        return sorted(self.tickets, key=lambda t: t["created_at"], reverse=True)

    def owns_order(self, customer_id, order_id):
        """Authorisation check — an agent that skips it leaks other people's data."""
        o = self.get_order(order_id)
        return bool(o and customer_id
                    and o["customer_id"] == (customer_id or "").strip().upper())


_RECORDS = None


def get_records():
    global _RECORDS
    if _RECORDS is None:
        _RECORDS = Records()
    return _RECORDS
