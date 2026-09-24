"""Central configuration. Everything tunable lives here, not scattered in the code."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
RULES_DIR = PACKAGE_ROOT / "rules"
PROMPTS_DIR = PACKAGE_ROOT / "llm" / "prompts"

# --- API -------------------------------------------------------------------
# The key is read from the environment only. It is never written to disk, never
# logged, and never sent anywhere except Google's API endpoint.
API_KEY_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

# Values that mean "nobody has filled this in yet". Without this guard, copying
# .env.example to .env verbatim reports a key as present and then fails at the API
# with an authentication error, which is a much harder thing to diagnose.
_PLACEHOLDER_KEYS = {"your-key-here", "your-api-key-here", "changeme", "todo", "xxx"}


def get_api_key() -> str | None:
    """The first usable key, or None. Kept for callers that only need one."""
    keys = get_api_keys()
    return keys[0] if keys else None


# Additional keys, checked in order after the primary one. Five slots covers a small
# team pooling personal keys; anything larger wants a paid key rather than a rota.
_EXTRA_KEY_SLOTS = 8


def get_api_keys() -> list[str]:
    """Every usable key, in the order they should be tried.

    Free-tier quota is metered per key per model per day, so a second key is a second
    independent allowance - the only way to raise a free-tier ceiling without paying.
    It does nothing for 503, which is Google's shared capacity and identical for
    everyone; see `llm/client.py`, which switches key for 429 and model for 503.

    Read from, in order: GEMINI_API_KEY / GOOGLE_API_KEY, then GEMINI_API_KEY_2 ..
    GEMINI_API_KEY_9, then a comma-separated GEMINI_API_KEYS.
    """
    names = [
        *API_KEY_ENV_VARS,
        *(f"GEMINI_API_KEY_{n}" for n in range(2, _EXTRA_KEY_SLOTS + 2)),
    ]

    found: list[str] = []
    for name in names:
        value = _clean_key(os.getenv(name))
        if value:
            found.append(value)

    for value in (os.getenv("GEMINI_API_KEYS") or "").split(","):
        cleaned = _clean_key(value)
        if cleaned:
            found.append(cleaned)

    # Dedupe while keeping order: the same key twice would double the wait before we
    # correctly conclude that its quota is gone.
    seen: set[str] = set()
    return [k for k in found if not (k in seen or seen.add(k))]


def _clean_key(value: str | None) -> str | None:
    """Strip quoting and whitespace, and reject the .env.example placeholders."""
    cleaned = (value or "").strip().strip("\"'")
    if not cleaned or cleaned.lower() in _PLACEHOLDER_KEYS:
        return None
    return cleaned


# --- Which backend answers -------------------------------------------------
# Two backends, chosen at run time rather than at install time:
#
#   gemini  - Google's API. What the hosted tool uses.
#   ollama  - a model running on the user's own machine, reached over localhost.
#
# The local backend is a development convenience - it makes the pipeline runnable
# without spending a metered request, which is most of what testing this tool costs.
# It is also the only configuration in which the documents never leave the computer
# they were opened on, which for a user who has been told that asking questions
# about their contract will cost them their job is not a footnote. That is why it is
# a choice in the UI rather than a hidden env var.
#
# It costs quality. A model that fits in consumer VRAM reads a Dutch employment
# contract less well than the hosted models do, so a local run is reported as a
# degraded run unless the model is named in OLLAMA_TRUSTED_MODELS - the same
# machinery already used for the `-lite` fallbacks below.
PROVIDERS = ("gemini", "ollama")
DEFAULT_PROVIDER = (os.getenv("CTF_PROVIDER", "gemini") or "gemini").strip().lower()

# Roles, not model ids. A pipeline step asks for "the model that does extraction",
# and each backend answers with its own id for that job. Before this existed every
# step named a Gemini id directly in the call, which pointed the local backend at a
# model it has never heard of.
ROLE_EXTRACTION = "extraction"
ROLE_REASONING = "reasoning"
ROLE_COMPOSE = "compose"

# Model IDs. Pinned rather than using a `-latest` alias, so a silent upstream
# model change cannot quietly alter what the tool tells a worker.
MODEL = os.getenv("CTF_MODEL", "gemini-3.8-flash")
MODEL_REASONING = os.getenv("CTF_MODEL_REASONING", "gemini-3.8-flash")

# Ordered fallbacks, tried left to right when the pinned model above will not serve.
#
# Pinning one model is right for reproducibility but wrong for availability: a model
# can be listed by `models.list()` and still answer 503 UNAVAILABLE ("experiencing
# high demand") or simply hang until the gateway returns 504. Observed within a
# single minute: 3.8-flash 504, 3.7-flash 503, 3.5-flash OK — then 3.5-flash 504 and
# 3.5-flash-lite OK. A worker waiting on a contract review should not see that.
#
# The pinned model is always tried first, so behaviour is unchanged whenever it is
# healthy; a fallback is only ever reached after the primary has exhausted its
# retries, and the report records which model actually answered.
#
# Two things govern the order, both measured rather than assumed:
#
# 1. Quota is metered per model per day on the free tier, so every extra id in this
#    list is an extra independent allowance. That is why a second non-lite id sits
#    here even though it overlaps in capability with its neighbours.
# 2. Quality drops sharply at the `-lite` tier, so the lites go last and answering
#    from one is treated as a degraded run (see DEGRADED_* below). During a
#    Flash-tier outage they are frequently the only ids still serving, which is a
#    reason to flag the result, not a reason to promote them.
#
# A Pro-tier fallback would be the obvious way to hold quality during an outage and
# is deliberately absent: on a free key `gemini-3.1-pro-preview` answers 429
# immediately, so it would only ever add latency.
MODEL_FALLBACKS: tuple[str, ...] = tuple(
    m.strip()
    for m in os.getenv(
        "CTF_MODEL_FALLBACKS",
        "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview,"
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite",
    ).split(",")
    if m.strip()
)

# Models we will use but do not trust to read a contract properly. Answering from one
# is not treated as a normal result: `pipeline.py` scales confidence by the factor
# below, which pushes a marginal report over CONFIDENCE_GATE and into a referral to a
# human rather than letting a weaker model quietly set the tone of the advice.
DEGRADED_MODEL_MARKERS: tuple[str, ...] = ("-lite",)
DEGRADED_CONFIDENCE_FACTOR = float(os.getenv("CTF_DEGRADED_FACTOR", "0.8"))


def is_degraded_model(model: str | None) -> bool:
    """True when `model` is one we would rather not have answered with."""
    return bool(model) and any(marker in model for marker in DEGRADED_MODEL_MARKERS)


# --- Local models (Ollama) -------------------------------------------------
# OLLAMA_HOST is Ollama's own environment variable, so a machine that already runs
# the server elsewhere needs no extra configuration here. It has to be normalised
# rather than used as given: Ollama writes it in *server* notation, which is not a
# URL a client can dial. See `_normalise_ollama_host`.
_OLLAMA_DEFAULT_PORT = 11434


def _normalise_ollama_host(value: str | None) -> str:
    """Turn whatever is in OLLAMA_HOST into a URL `requests` can use.

    Three shapes turn up in practice, and only the first is a working URL:

        http://localhost:11434      what we want
        0.0.0.0:11434               what Ollama itself writes into the variable
        192.168.1.5                 a host with the port left implied

    `0.0.0.0` is the address the server *listens on* - every interface - and is not
    a destination: as a client, dial the loopback instead. Without this the tool
    reports "Ollama is not running" on a machine where it is running perfectly well,
    which is a bad first five minutes for anyone testing the local option.
    """
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return f"http://localhost:{_OLLAMA_DEFAULT_PORT}"

    scheme, _, rest = raw.partition("://")
    if not rest:
        scheme, rest = "http", raw

    if rest.startswith("["):
        # IPv6 literal: the colons inside the brackets are part of the address.
        host, _, tail = rest.partition("]")
        host += "]"
        sep, _, port = tail.partition(":")
        sep, port = (":", port) if tail.startswith(":") else ("", "")
    else:
        host, sep, port = rest.partition(":")

    if host in ("0.0.0.0", "::", "[::]", "[::0]", ""):
        host = "127.0.0.1"
    if not sep:
        port = str(_OLLAMA_DEFAULT_PORT)

    return f"{scheme}://{host}:{port}"


OLLAMA_HOST = _normalise_ollama_host(os.getenv("OLLAMA_HOST"))

# No `-latest` tag, for the same reason the Gemini ids are pinned: a model that
# changes under the tool changes what it tells a worker.
OLLAMA_MODEL = os.getenv("CTF_OLLAMA_MODEL", "qwen3:8b").strip()
OLLAMA_MODEL_REASONING = (os.getenv("CTF_OLLAMA_MODEL_REASONING") or "").strip() or OLLAMA_MODEL

# Context window, in tokens, and the single most dangerous default in this file if
# it is left alone. Ollama's own default is small (4k on most builds), and a prompt
# that overruns it is not rejected - the front of it is silently dropped. For this
# pipeline the front of the prompt is the contract, so the model would answer
# confidently about a document it was never shown. `ollama_client.py` therefore
# sizes each request against the prompt it is about to send, raises num_ctx up to
# OLLAMA_MAX_CTX when it needs to, and fails loudly rather than letting a truncated
# bundle through.
OLLAMA_NUM_CTX = int(os.getenv("CTF_OLLAMA_NUM_CTX", "16384"))
OLLAMA_MAX_CTX = int(os.getenv("CTF_OLLAMA_MAX_CTX", "32768"))

# Generous, and deliberately not REQUEST_TIMEOUT_S: a 12GB card running a 14B model
# on a long bundle is slow rather than broken, and the machine may have to load the
# weights from disk first. Nothing is metered here, so patience is free.
OLLAMA_TIMEOUT_S = float(os.getenv("CTF_OLLAMA_TIMEOUT", "600"))

# How long Ollama keeps the weights in VRAM after a call. The pipeline makes several
# calls in a row; letting the model unload between them adds the load time to each.
OLLAMA_KEEP_ALIVE = os.getenv("CTF_OLLAMA_KEEP_ALIVE", "10m").strip()

# "auto" sends no thinking parameter at all, which is the only setting that works
# across both thinking and non-thinking models - Ollama answers 400 when asked to
# set `think` on a model that has no such mode. "off"/"on" force it for a model you
# know supports it; `ollama_client.py` falls back to "auto" if the server objects.
OLLAMA_THINK = (os.getenv("CTF_OLLAMA_THINK", "auto") or "auto").strip().lower()

# Local models we would trust to read a contract properly. Empty on purpose: the
# claim has to be earned per model, on this project's own sample bundles, and until
# someone has done that the honest position is that a local run is a degraded run.
# Names are matched exactly, as `ollama list` prints them.
OLLAMA_TRUSTED_MODELS: tuple[str, ...] = tuple(
    m.strip() for m in (os.getenv("CTF_OLLAMA_TRUSTED") or "").split(",") if m.strip()
)

# Extraction and legal reasoning are not creative tasks.
TEMPERATURE_EXTRACTION = 0.0
TEMPERATURE_REASONING = 0.1
TEMPERATURE_COMPOSE = 0.3

# Attempts per model, and only for the failures worth repeating on the same model
# (500 INTERNAL). 429 and 503 fail straight over instead: on the free tier every
# attempt costs one of ~20 daily requests for that model, so a retry and a failover
# are priced the same and the failover has the better odds. See llm/client.py.
MAX_RETRIES = int(os.getenv("CTF_MAX_RETRIES", "3"))

# Per-request deadline. This is NOT just a local socket timeout: the SDK sends the
# value to Google as the request deadline, and Google returns 504 DEADLINE_EXCEEDED
# when generation runs past it. Measured directly - a 10s deadline against a healthy
# `gemini-3.5-flash-lite` produced `504 DEADLINE_EXCEEDED` after 8.7s on nothing more
# exotic than a long essay. (The API also refuses anything under 10s outright, with
# 400 INVALID_ARGUMENT "Minimum allowed deadline is 10s".)
#
# That makes a too-low value actively harmful rather than merely impatient. Every 504
# it causes is read by `llm/client.py` as "this model is down", so the pipeline fails
# over to the next candidate - systematically preferring whichever model is *fastest*
# over whichever is *best*, and ending at the lite tier. The 45s that used to be here
# was under the time this pipeline's own structure-extraction step needs on a full
# bundle, so it was turning healthy models away.
#
# 120s is chosen to sit well clear of a slow-but-working generation. Failover then
# means what it is supposed to mean: the model will not serve us, not that we ran out
# of patience.
REQUEST_TIMEOUT_S = float(os.getenv("CTF_TIMEOUT", "120"))

# --- Safety thresholds -----------------------------------------------------
# A quote must match the source text at least this well or the finding is dropped.
# 1.0 would reject findings over trivial whitespace/hyphenation noise from PDFs.
GROUNDING_MIN_RATIO = float(os.getenv("CTF_GROUNDING_MIN_RATIO", "0.90"))

# Below this overall confidence the tool refuses to summarise and routes to a human.
CONFIDENCE_GATE = float(os.getenv("CTF_CONFIDENCE_GATE", "0.55"))

# Documents longer than this are truncated per-document before being sent.
MAX_CHARS_PER_DOCUMENT = int(os.getenv("CTF_MAX_CHARS_PER_DOC", "60000"))

# --- Languages -------------------------------------------------------------
# Reading languages we offer. Ordered by the user group in section 3 of the brief.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "pl": "Polski (Polish)",
    "ro": "Română (Romanian)",
    "bg": "Български (Bulgarian)",
    "en": "English",
    "nl": "Nederlands (Dutch)",
    "uk": "Українська (Ukrainian)",
    "hu": "Magyar (Hungarian)",
}
DEFAULT_LANGUAGE = "en"

# Language quality is not equal across these. See ETHICS.md — this is surfaced in
# the UI rather than hidden, because uneven quality across languages is itself an
# SDG 10 problem.
