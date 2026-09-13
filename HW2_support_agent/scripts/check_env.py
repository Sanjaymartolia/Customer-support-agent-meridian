#!/usr/bin/env python3
"""Preflight: is this environment ready for HW2?

    python scripts/check_env.py

Run this FIRST, before `pip install -r requirements.txt`. Deliberately written in
old-style Python with no dependencies, so it runs on whatever interpreter you
happen to have and can tell you it is the wrong one.
"""

import os
import sys

MIN_PY = (3, 10)
PACKAGES = [("requests", "requests"), ("dotenv", "python-dotenv"),
            ("chromadb", "chromadb"), ("rank_bm25", "rank-bm25"),
            ("langgraph", "langgraph"), ("langchain_core", "langchain-core"),
            ("langchain_openai", "langchain-openai"), ("gradio", "gradio")]

OK, BAD, WARN = "  ok  ", " FAIL ", " warn "


def check_live(key):
    """Actually ask OpenRouter whether the key works. -> True / False / None."""
    import json as _json
    import urllib.error
    import urllib.request
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = _json.loads(resp.read()).get("data", {})
        limit, used = body.get("limit"), body.get("usage")
        if limit is not None and used is not None and used >= limit:
            print("%s the key works but the credit limit is used up — top up at "
                  "openrouter.ai" % WARN)
        else:
            print("%s OpenRouter accepted the key" % OK)
        return True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print("%s OpenRouter rejected the key (HTTP %d). It may have been deleted "
                  "or regenerated — make a new one at openrouter.ai -> Settings -> Keys"
                  % (BAD, e.code))
            return False
        print("%s could not verify the key (HTTP %d); carrying on" % (WARN, e.code))
    except Exception:                       # offline, proxy, DNS — not the key's fault
        print("%s could not reach OpenRouter to verify the key; carrying on" % WARN)
    return None


def main():
    problems = []
    v = sys.version_info
    print("")

    if v[:2] < MIN_PY:
        print("%s python %d.%d.%d  -> HW2 needs Python %d.%d or newer" %
              (BAD, v[0], v[1], v[2], MIN_PY[0], MIN_PY[1]))
        print("""
        gradio, langgraph, langchain-core and langchain-openai all require
        Python 3.10+. On 3.9, pip either refuses to install (the error you get
        is "Could not find a version that satisfies the requirement gradio")
        or silently installs an old langgraph whose API does not match the
        starter code — so fix the interpreter, do not loosen the pins.

        Get a newer interpreter, then make the virtualenv with it:

            conda create -n hw2 python=3.11 -y
            conda activate hw2
            pip install -r requirements.txt

        or, if you are not using conda and have a 3.11 on your PATH:

            python3.11 -m venv .venv && source .venv/bin/activate
            pip install -r requirements.txt

        Note that `python3 -m venv` copies whatever `python3` currently is.
        Check with `python3 -V` before you trust it.
        """)
        raise SystemExit(1)

    print("%s python %d.%d.%d" % (OK, v[0], v[1], v[2]))
    print("%s interpreter %s" % (OK, sys.executable))
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        print("%s not inside a virtualenv or conda env — that is allowed, but a "
              "fresh env avoids version clashes" % WARN)

    for module, dist in PACKAGES:
        try:
            __import__(module)
        except ImportError:
            print("%s %-18s not installed" % (BAD, dist))
            problems.append("pip install -r requirements.txt")
            continue
        try:                                  # not every module exposes __version__
            from importlib.metadata import version
            found = version(dist)
        except Exception:
            found = ""
        print("%s %-18s %s" % (OK, dist, found))

    # the key may come from the shell or from .env; either is fine
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(here, ".env")
    key, source = os.environ.get("OPENROUTER_API_KEY", ""), "environment"
    if not key and os.path.exists(env_file):
        for line in open(env_file):
            if line.strip().startswith("OPENROUTER_API_KEY="):
                key, source = line.split("=", 1)[1].strip().strip('"').strip("'"), ".env"

    placeholder = key.rstrip(".").rstrip("-") in ("sk-or-v1", "sk-or") or key.endswith("...")
    if placeholder:
        print("%s OPENROUTER_API_KEY is still the example value from .env.example. "
              "Paste your real key over it." % BAD)
        problems.append("put your real OpenRouter key in .env")
    elif key.startswith("sk-or-") and len(key) > 40:
        print("%s OPENROUTER_API_KEY from %s (%s...%s)" % (OK, source, key[:9], key[-4:]))
        if check_live(key) is False:
            problems.append("get a working key from https://openrouter.ai -> Settings -> Keys")
    elif key:
        print("%s OPENROUTER_API_KEY from %s does not look like an OpenRouter key "
              "(expected it to start with sk-or-)" % (WARN, source))
    elif os.path.exists(env_file):
        print("%s .env exists but has no OPENROUTER_API_KEY line" % BAD)
        problems.append("add OPENROUTER_API_KEY=sk-or-... to .env")
    else:
        print("%s no API key: .env missing and OPENROUTER_API_KEY unset" % BAD)
        problems.append("cp .env.example .env, then add your key")

    if os.path.exists(os.path.join(here, ".index", "chunks.json")):
        print("%s knowledge-base index built" % OK)
    else:
        print("%s index not built yet -> python scripts/build_index.py --force" % WARN)

    print("")
    if problems:
        print("Not ready. Next:")
        for p in dict.fromkeys(problems):
            print("    " + p)
        raise SystemExit(1)
    print("Ready. Next:  python scripts/evaluate_dev.py")


if __name__ == "__main__":
    main()
