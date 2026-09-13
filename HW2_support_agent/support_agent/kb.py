"""Reading the handbook and cutting it into pieces.

This is the first half of RAG: before you can search the handbook, you have to
load it and chop it up.

The whole knowledge base is one file, `data/kb/handbook.md`. It is divided into
sections that start with `##`. Right under each heading there is a comment line
saying what that section is:

    ## Returns and Refunds
    <!-- id: returns | status: current -->

`id` is the short name your agent uses when it says where an answer came from.
`status` and `trust` tell you whether a section can be trusted: one section is an
out-of-date policy, and one is unverified customer gossip. Two things use these
markers, so do not throw them away.
"""

import re
from dataclasses import dataclass, field

from . import config

HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
META = re.compile(r"<!--(?P<body>[^>]*?)-->")


@dataclass
class Section:
    id: str
    title: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str            # the section id — this is what citations use
    title: str
    text: str
    metadata: dict = field(default_factory=dict)


def _slug(title):
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def load_sections(kb_dir=None):
    """Read every .md in the knowledge base and split it into `##` sections."""
    kb_dir = kb_dir or config.KB_DIR
    sections = []
    for path in sorted(kb_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        marks = list(HEADING.finditer(raw))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
            body = raw[m.end():end].strip()
            title = m.group("title")

            meta = {"status": "current", "trust": "official", "source_file": path.name}
            first = META.search(body[:300])
            if first:
                for pair in first.group("body").split("|"):
                    if ":" in pair:
                        k, v = pair.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = body.replace(first.group(0), "", 1).strip()

            sections.append(Section(id=meta.pop("id", _slug(title)), title=title,
                                    text=body, metadata=meta))
    if not sections:
        raise FileNotFoundError(f"no '## ' sections found under {kb_dir}")
    return sections


# --------------------------------------------------------------------------- #
# splitting
# --------------------------------------------------------------------------- #

def split_fixed(sections, size, overlap):
    """The simple way: glue the handbook together and cut every `size` letters.

    This ignores the headings completely. A piece that starts near the end of the
    refunds section will run on into the cancellation section, and we label that
    piece "refunds" because that is where it started. So some pieces are labelled
    wrongly, and some pieces are half one topic and half another.

    You can see this for yourself in the web app's "Retrieval lab" tab. Fixing it
    is TODO 1.

    Returns a list of (section, text-of-one-piece) pairs.
    """
    if size <= overlap:
        raise ValueError("CHUNK_SIZE must exceed CHUNK_OVERLAP")
    full, bounds = "", []
    for s in sections:
        bounds.append((len(full), s))
        full += s.text + "\n\n"

    out, pos = [], 0
    while pos < len(full):
        piece = full[pos:pos + size]
        owner = bounds[0][1]
        for start, sec in bounds:
            if start <= pos:
                owner = sec
            else:
                break
        if piece.strip():
            out.append((owner, piece))
        pos += size - overlap
    return out


def split_structured(sections, size, overlap):
    """TODO 1 — cut at the headings instead. From Lecture 5, "Splitting Documents".

    The goal: every piece belongs to exactly one section, so nothing is mislabelled.

    Start simple. Make one piece per section. Some sections are longer than `size`
    and still need cutting, and when that happens, cut at a sensible place instead
    of mid-sentence. Try these boundaries in order, and only fall back to a hard
    cut if none of them work:

        1. a `###` sub-heading
        2. a blank line between paragraphs
        3. the end of a sentence

    That order is the "recursive splitter" from the lecture.

    Second idea, worth trying separately: paste the section title onto the front of
    each piece before it gets turned into numbers. A piece that is just a table row
    does not say which policy it belongs to; adding "Returns and Refunds" to the
    top of it does.

    To see whether either change helped:

        python scripts/build_index.py --force --strategy structured
        python scripts/evaluate_dev.py --retrieval-only

    That second command scores search on its own and costs nothing to run, because
    it makes no AI calls. Measure the two ideas one at a time, or you will not know
    which one did the work.

    Return the same thing split_fixed returns: a list of (section, text) pairs.
    """
    raise NotImplementedError("TODO 1 — see the docstring")


def chunk_documents(sections, size=None, overlap=None, strategy="fixed"):
    size = size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP
    splitter = {"fixed": split_fixed, "structured": split_structured}[strategy]

    chunks = []
    for i, (section, text) in enumerate(splitter(sections, size, overlap)):
        chunks.append(Chunk(
            chunk_id=f"{section.id}#{i}",
            doc_id=section.id,
            title=section.title,
            text=text,
            metadata={"doc_id": section.id, "title": section.title,
                      "status": section.metadata.get("status", "current"),
                      "trust": section.metadata.get("trust", "official"),
                      "chunk_index": i}))
    return chunks
