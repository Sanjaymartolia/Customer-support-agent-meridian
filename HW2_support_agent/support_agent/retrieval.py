"""Searching the handbook.

Given a customer's question, find the few pieces of the handbook most likely to
answer it. Whatever this returns is all your agent will know, so if the right
piece is missing, no amount of clever prompting later can save the answer.

One kind of search already works: `dense`, which searches by meaning. TODO 2 adds
the rest. You wrote all of it in the Lecture 6 notebook, so this is mostly copying
your own code across and then measuring whether it actually helps here.
"""

from collections import defaultdict
from dataclasses import dataclass

from . import config, index, llm


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float
    metadata: dict


class Retriever:
    def __init__(self, mode=None, top_k=None):
        self.mode = mode or config.RETRIEVAL_MODE
        self.top_k = top_k or config.TOP_K
        self.collection, self.chunks = index.load()
        self._bm25 = None

    def _hit(self, chunk, score):
        return Hit(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, title=chunk.title,
                   text=chunk.text, score=score, metadata=dict(chunk.metadata))

    # ---------------------------------------------------------------- dense --
    def dense(self, query, k=None):
        """Embedding search over the Chroma index."""
        k = k or config.CANDIDATE_K
        res = self.collection.query(query_texts=[query], n_results=min(k, len(self.chunks)))
        hits = []
        for cid, text, meta, dist in zip(res["ids"][0], res["documents"][0],
                                         res["metadatas"][0], res["distances"][0]):
            hits.append(Hit(chunk_id=cid, doc_id=meta.get("doc_id", cid.split("#")[0]),
                            title=meta.get("title", ""), text=text,
                            score=1.0 / (1.0 + float(dist)), metadata=dict(meta)))
        return hits

    # -------------------------------------------------------------- lexical --
    def lexical(self, query, k=None):
        """TODO 2a — keyword search. From Lecture 6, "Hybrid search".

        `dense` above searches by meaning, which is great for "get my money back"
        but weak on exact strings. A customer typing `ERR-4021` wants the piece
        containing exactly that, and meaning-based search has no idea it is a code
        rather than an odd-looking word.

        BM25 is plain keyword search and handles that case. `self.chunks` is
        already loaded and `rank_bm25` is already installed; this is section 5 of
        the Lecture 6 notebook.

        One thing to think about: you will probably split the text on spaces. Does
        that keep `ERR-4021` as one word? What if the customer types `ERR 4021`?

        Return a list of `Hit` objects, same as `dense`, so the two can be merged.
        """
        raise NotImplementedError("TODO 2a — see the docstring")

    def rrf(self, *rankings, k=None, top=None):
        """TODO 2b — merge two lists of results. From Lecture 6, "RRF".

        You now have two lists: one from meaning-based search, one from keyword
        search. You want a single list.

        You cannot just add the scores. The two kinds of search produce numbers
        that mean completely different things — one might give 0.4 for an excellent
        match and the other 12.7. Adding them is meaningless.

        So ignore the scores and use each result's *position* instead. A piece that
        came 1st in one list and 3rd in the other scores:

            1/(k + 1)  +  1/(k + 3)

        `k` is `config.RRF_K`, which is 60. It controls how much better 1st place
        is than 5th. Try changing it and see what happens.

        Accepts any number of ranked lists. Returns one merged list of `Hit`s.
        """
        raise NotImplementedError("TODO 2b — see the docstring")

    def hybrid(self, query, k=None):
        """TODO 2c — put 2a and 2b together: run both searches, merge with rrf().

        Then compare against meaning-based search on its own:

            RETRIEVAL_MODE=dense  python scripts/evaluate_dev.py --retrieval-only
            RETRIEVAL_MODE=hybrid python scripts/evaluate_dev.py --retrieval-only

        Be honest about the result. Our handbook is only 36 pieces long, and on
        something that small the gain may be tiny or even negative. "I measured it,
        it gained 0.02, so I did not use it" is a good answer and earns marks.
        Claiming it helped without a number does not.
        """
        raise NotImplementedError("TODO 2c — see the docstring")

    # ------------------------------------------------------------- optional --
    def rerank(self, query, candidates, top_n=None):
        """OPTIONAL — re-sort the results with an AI. Lecture 6, "Reranking".

        Search is fast but rough. So fetch more results than you need (8), ask a
        model to score each one out of 10 for how well it answers the question, and
        keep the best 4. Ask for just a number and set `max_tokens=5`.

        The catch is cost: one extra AI call per result per question. Work out what
        that costs in tokens and time, and say whether the gain was worth it.
        """
        raise NotImplementedError("reranking is optional — see the docstring")

    def translate_query(self, query):
        """OPTIONAL — rewrite the question before searching. Lecture 6.

        Customers do not use the handbook's words. They say "when do I get my
        money" and the handbook says "refund processing timeline".

        Two ways to close that gap:
          * ask a model for three rewordings, search with all of them, and merge
            the results with `rrf`;
          * ask a model to write a fake answer, then search using that fake answer
            as the query. Answers look like other answers, so this often matches
            better than the question does.

        Most useful on very short questions.
        """
        raise NotImplementedError("query translation is optional")

    # ----------------------------------------------------------------- entry --
    def search(self, query, k=None):
        k = k or self.top_k
        if self.mode == "dense":
            hits = self.dense(query, config.CANDIDATE_K)
        elif self.mode == "hybrid":
            hits = self.hybrid(query, config.CANDIDATE_K)
        elif self.mode == "hybrid_rerank":
            hits = self.rerank(query, self.hybrid(query, config.CANDIDATE_K), top_n=k)
        else:
            raise ValueError(f"unknown RETRIEVAL_MODE {self.mode!r}")
        return self.postprocess(hits)[:k]

    def postprocess(self, hits):
        """TODO 2d — deal with the two trap sections. Lecture 5, on metadata.

        Search has no idea that some text is untrustworthy. Two sections come back
        looking just as relevant as the real ones:

          `archive_returns_2024`  An old policy saying 15 days. It was replaced in
                                  January 2026 and applies to none of the orders
                                  you have. Quoting it is always wrong.

          `community`             Customer gossip, not policy. It also contains a
                                  fake instruction telling the AI to approve any
                                  refund.

        Three reasonable options. Any of them earns full marks as long as you
        explain your choice in the report:

          * remove them from the results completely;
          * keep them, but push them to the bottom;
          * keep them, so the agent can recognise a claim a customer quotes at it,
            but never list them as a source.

        Naming either one as your source scores zero for sources on that question.
        Every piece carries `status` and `trust` in `.metadata`, and the two names
        are in `config.UNTRUSTED_DOCS` and `config.SUPERSEDED_DOCS`.
        """
        return hits


_RETRIEVER = None


def get_retriever():
    """Process-wide singleton — loading the index per query is slow."""
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = Retriever()
    return _RETRIEVER


def format_context(hits):
    """Lay the retrieved passages out for the model.

    Each block is labelled with its section id, because that id is exactly what
    we ask the model to give back as its source. An earlier version numbered the
    blocks `[1] [2] [3]` as well, and the model dutifully cited "2" — if you show
    a model two identifiers it will sometimes pick the wrong one. One identifier,
    one meaning.
    """
    lines = []
    for h in hits:
        status = h.metadata.get("status", "current")
        flag = "" if status == "current" else f"  (WARNING: status={status})"
        lines.append(f"[section: {h.doc_id}]{flag}\n{h.title}\n{h.text.strip()}")
    return "\n\n".join(lines) if lines else "(nothing retrieved)"
