#!/usr/bin/env python3
"""Build (or rebuild) the knowledge-base index.

    python scripts/build_index.py                 # build if missing
    python scripts/build_index.py --force         # wipe and rebuild
    python scripts/build_index.py --strategy recursive --chunk-size 600
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from support_agent import config, index  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strategy", default="fixed", choices=["fixed", "structured"])
    ap.add_argument("--chunk-size", type=int)
    ap.add_argument("--chunk-overlap", type=int)
    a = ap.parse_args()
    if a.chunk_size:
        config.CHUNK_SIZE = a.chunk_size
    if a.chunk_overlap:
        config.CHUNK_OVERLAP = a.chunk_overlap
    index.build(force=a.force, strategy=a.strategy)


if __name__ == "__main__":
    main()
