"""Talking to the AI models, through OpenRouter.

Three things you will use:

    chat(...)         send a prompt, get text back
    chat_json(...)    same, but insists on a JSON object and parses it for you
    chat_model(...)   a LangChain model. Use this one when you need tool calling,
                      because it has `.bind_tools()` and the plain `chat()` does not

Every call is saved to disk in `.cache/llm/`. If you ask for exactly the same
thing again — same model, same messages, same temperature — you get the saved copy
instead of paying for it. This is why you can re-run the practice set all day for
almost nothing. Delete the `.cache` folder when you want genuinely fresh answers.
"""

import hashlib
import json
import os
import time

import requests
from dotenv import load_dotenv

from . import config

load_dotenv()

BASE_URL = "https://openrouter.ai/api/v1"
HEADERS_EXTRA = {
    "HTTP-Referer": "https://iitb.ac.in/agentic-ai",
    "X-Title": "Agentic AI HW2 - Meridian Support Agent",   # ASCII only: requests
                                                           # encodes headers as latin-1
}

USAGE = {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0}


class LLMError(RuntimeError):
    """Something went wrong talking to the model. Retried a few times first."""


class AuthError(LLMError):
    """Your API key was rejected. Retrying will not help, so we do not."""


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise AuthError(
            "OPENROUTER_API_KEY is not set.\n"
            "  Run: cp .env.example .env    then paste your real key into that file.\n"
            "  Get one at https://openrouter.ai -> Settings -> Keys.")
    return key


def reset_usage():
    for k in USAGE:
        USAGE[k] = 0


def usage_snapshot():
    return dict(USAGE)


# --------------------------------------------------------------------------- #

def _cache_path(request):
    digest = hashlib.sha256(
        json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    d = config.CACHE_DIR / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{digest}.json"


def _as_messages(prompt_or_messages, system=None):
    if isinstance(prompt_or_messages, str):
        msgs = [{"role": "user", "content": prompt_or_messages}]
    else:
        msgs = list(prompt_or_messages)
    if system:
        msgs = [{"role": "system", "content": system}] + msgs
    return msgs


def chat(prompt_or_messages, model=None, temperature=None, max_tokens=None,
         system=None, response_format=None, cache=None):
    """One chat-completions call. Returns the assistant's text.

    Accepts a bare string (becomes a user message) or a full messages list.
    """
    request = {
        "model": model or config.FAST_MODEL,
        "messages": _as_messages(prompt_or_messages, system),
        "temperature": config.TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens or config.MAX_TOKENS,
    }
    if response_format:
        request["response_format"] = response_format

    use_cache = config.LLM_CACHE if cache is None else cache
    path = _cache_path(request) if use_cache else None
    if path is not None and path.exists():
        USAGE["cached"] += 1
        return json.loads(path.read_text())["text"]

    last = None
    for attempt in range(config.MAX_RETRIES):
        try:
            r = requests.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key()}",
                         "Content-Type": "application/json", **HEADERS_EXTRA},
                json=request, timeout=config.REQUEST_TIMEOUT)
            if r.status_code in (401, 403):
                # Not worth retrying: the key is wrong, not the network.
                raise AuthError(
                    f"OpenRouter rejected your API key (HTTP {r.status_code}).\n"
                    f"  Common causes:\n"
                    f"    - .env still has the placeholder from .env.example\n"
                    f"      (it literally says sk-or-v1-... — replace the dots)\n"
                    f"    - the key was deleted or regenerated on openrouter.ai\n"
                    f"    - the account has no credit left\n"
                    f"  Check it with: python scripts/check_env.py")
            if r.status_code in (429, 500, 502, 503, 504):
                raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            body = r.json()
            if "choices" not in body:
                raise LLMError(f"unexpected response: {json.dumps(body)[:300]}")
            text = body["choices"][0]["message"]["content"] or ""
            usage = body.get("usage") or {}
            USAGE["calls"] += 1
            USAGE["prompt_tokens"] += usage.get("prompt_tokens", 0)
            USAGE["completion_tokens"] += usage.get("completion_tokens", 0)
            if path is not None:
                path.write_text(json.dumps({"text": text, "model": request["model"]}))
            return text
        except AuthError:
            raise                                   # no point retrying a bad key
        except Exception as e:                      # noqa: BLE001 — everything else, retry
            last = e
            time.sleep(1.5 * (2 ** attempt))
    raise LLMError(f"all {config.MAX_RETRIES} attempts failed: {last}")


def chat_json(prompt_or_messages, schema_hint="", **kw):
    """Like chat(), but insists the reply is a JSON object and parses it for you.

    Copes with the model wrapping its JSON in code fences or adding a sentence
    either side.

    Pass `schema_hint` to show the model the exact shape you want. Models are far
    more reliable when they can see an example than when you describe it.
    """
    system = kw.pop("system", "") or ""
    if schema_hint:
        system = (system + "\n\nReturn ONLY a JSON object with this shape, no markdown "
                           "fences, no commentary:\n" + schema_hint).strip()
    kw.setdefault("response_format", {"type": "json_object"})
    raw = chat(prompt_or_messages, system=system, **kw)
    return parse_json(raw)


def parse_json(raw):
    """Pull a JSON object out of a model reply, however it wrapped it."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise LLMError(f"no JSON object in reply: {raw[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise LLMError(f"unbalanced JSON in reply: {raw[:200]!r}")


# --------------------------------------------------------------------------- #

def chat_model(model=None, temperature=None, **kw):
    """A LangChain model. Use this one whenever you need tool calling.

    The plain `chat()` above cannot do tools. This can, because LangChain models
    have `.bind_tools(...)`, which is what TODO 4 needs. Same service underneath,
    different client library.
    """
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model or config.TOOL_MODEL,
        temperature=config.TEMPERATURE if temperature is None else temperature,
        base_url=BASE_URL,
        api_key=api_key(),
        default_headers=HEADERS_EXTRA,
        timeout=config.REQUEST_TIMEOUT,
        **kw)
