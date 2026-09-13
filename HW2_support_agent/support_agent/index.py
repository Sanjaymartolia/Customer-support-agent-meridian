"""Stages 3-4: embed the chunks and store them.

Chroma's default embedding function is a MiniLM running on onnxruntime — CPU
only, no torch, no GPU, nothing to download beyond a small model file. It stands
in for a hosted embedding API and behaves the same way for our purposes.
"""

import json
import shutil

from . import config, kb

COLLECTION = "meridian_kb"


def _chroma_client():
    import chromadb
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.INDEX_DIR / "chroma"))


def build(force=False, strategy="fixed", verbose=True):
    """(Re)build the vector index and the chunk manifest. Returns the chunks."""
    chunks_path = config.INDEX_DIR / "chunks.json"
    if force and config.INDEX_DIR.exists():
        shutil.rmtree(config.INDEX_DIR)
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)

    sections = kb.load_sections()
    chunks = kb.chunk_documents(sections, strategy=strategy)

    client = _chroma_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:                                  # noqa: BLE001 — absent is fine
        pass
    collection = client.create_collection(COLLECTION)
    collection.add(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[c.metadata for c in chunks])

    chunks_path.write_text(json.dumps(
        [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "title": c.title,
          "text": c.text, "metadata": c.metadata} for c in chunks], indent=2))

    if verbose:
        print(f"indexed {len(chunks)} chunks from {len(sections)} handbook sections "
              f"(strategy={strategy}, size={config.CHUNK_SIZE}, "
              f"overlap={config.CHUNK_OVERLAP}) -> {config.INDEX_DIR}")
    return chunks


def load():
    """-> (chroma collection, list[Chunk]). Builds the index if it is missing."""
    chunks_path = config.INDEX_DIR / "chunks.json"
    if not chunks_path.exists():
        build()
    raw = json.loads(chunks_path.read_text())
    chunks = [kb.Chunk(**c) for c in raw]
    collection = _chroma_client().get_collection(COLLECTION)
    return collection, chunks
