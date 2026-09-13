"""What gets passed from step to step.

In LangGraph, each step is an ordinary function that takes this dictionary and
returns the bits it wants to change. LangGraph merges those changes back in.

How it merges depends on the field. By default a new value replaces the old one.
But if you mark a field with `operator.add`, as `messages` and `steps` are below,
new items get added to the end of the list instead of wiping it. That is what you
want for anything you are building up over several steps — otherwise each loop
around the tool cycle throws away what the last one found.
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage


class SupportState(TypedDict, total=False):
    # --- inputs ---------------------------------------------------------------
    query_id: str
    query: str
    customer_id: str | None
    history: list                       # prior turns, [{role, content}]

    # --- working memory -------------------------------------------------------
    messages: Annotated[list[AnyMessage], operator.add]
    hits: list                          # retrieval Hits, as dicts
    steps: Annotated[list[str], operator.add]   # node names, in order visited

    # --- outputs (these become the trace) -------------------------------------
    answer: str
    route: str                          # resolved | needs_info | escalated
    citations: list
    actions: list
    escalation: dict | None
