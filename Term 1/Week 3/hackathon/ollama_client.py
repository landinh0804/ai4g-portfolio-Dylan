"""The second LLM backend: a model running on the user's own machine, via Ollama.

It is a drop-in peer of `GeminiClient` - same `generate_json` contract, same
exceptions, same `answered_degraded` signal - so `pipeline.py` and every step under
`steps/` work unchanged whichever one they are handed.

Two reasons it exists.

*Testing.* Every run against the API costs one of a small number of metered daily
requests, and developing this pipeline means running it dozens of times a day. A
local model makes that free, which is the difference between testing the prompt
changes and guessing at them.

*Privacy.* This is the only configuration where the documents never leave the
machine they were opened on. The people this tool is built for are frequently told,
explicitly, that asking questions about their contract will cost them the job and
the room that comes with it. "Nothing was uploaded anywhere" is a real answer to
that, not a technicality - so the local option is offered in the UI and named there
in those terms.

What it costs, and what we do about it: a model that fits in consumer VRAM reads a
Dutch employment contract less well than the hosted models do. A local run is
therefore reported as a *degraded* run - confidence scaled down, and a note in the
report naming the model - unless the model has been explicitly vouched for in
`config.OLLAMA_TRUSTED_MODELS`. That is the same treatment the `-lite` Gemini
fallbacks get, for the same reason: a weaker reader must not quietly set the tone of
the advice.

Two things here are not optional detail:

* **Structured output.** Ollama takes a JSON schema in `format` and constrains
  decoding to it, so the same Pydantic models that guard the Gemini boundary guard
  this one. Nothing downstream ever sees raw model text.
* **Context sizing.** Ollama's default context is small, and a prompt that overruns
  it is *silently truncated from the front*. The front of these prompts is the
  contract. See `_context_for`.
"""

from __future__ import annotations

import copy
import json
import logging
import random
import re
import time
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .. import config
# Shared with the Gemini client rather than written twice: a response truncated
# mid-JSON looks the same whichever model produced it, and it happens more often
# here, where the context window is the thing that ran out.
from .client import _try_repair_json
from .errors import LLMInvalidOutput, LLMUnavailable

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Keywords that are either pure documentation or that llama.cpp's grammar converter
# does not act on. `title` is worth dropping rather than passing through: on a schema
# this size those strings are a real share of the work of building the grammar, and
# they change nothing about what is accepted.
_DROPPED_SCHEMA_KEYS = {
    "title",
    "default",
    "examples",
    "$schema",
    "discriminator",
    "format",
}

_MAX_INLINE_DEPTH = 12

# Rough chars-per-token for the languages in these documents. English runs nearer
# 4; Dutch compounds and Polish inflection run nearer 3, and undershooting here is
# the failure that silently truncates a contract, so 3 is what we assume.
_CHARS_PER_TOKEN = 3.0

# Context reserved for the answer. `num_ctx` covers prompt *and* generation, so a
# window sized to the prompt alone leaves no room to reply. A composed report in a
# second language is the longest thing this pipeline asks for.
_OUTPUT_RESERVE_TOKENS = 4096

# Round requested windows up to this, so a run does not re-allocate the KV cache for
# every slightly different prompt length.
_CTX_GRANULARITY = 2048


def schema_for_ollama(model: type[BaseModel], /) -> dict[str, Any]:
    """The JSON schema for a Pydantic model, in the shape Ollama wants.

    Ollama compiles `format` into a decoding grammar. It resolves `$ref` itself, but
    inlining here keeps the two backends' schema handling comparable and avoids
    depending on how a given Ollama build handles `$defs` at depth.
    """
    return _inline(model.model_json_schema())


def _inline(schema: dict[str, Any], defs: dict[str, Any] | None = None, depth: int = 0) -> dict[str, Any]:
    if depth > _MAX_INLINE_DEPTH:
        return {"type": "string"}

    if defs is None:
        defs = schema.get("$defs", {}) or schema.get("definitions", {}) or {}

    node = copy.deepcopy(schema)

    ref = node.pop("$ref", None)
    if ref:
        target = defs.get(ref.rsplit("/", 1)[-1])
        if target is None:
            return {"type": "string"}
        merged = _inline(target, defs, depth + 1)
        if "description" in node:
            merged["description"] = node["description"]
        return merged

    for key in list(node):
        if key in _DROPPED_SCHEMA_KEYS or key in ("$defs", "definitions"):
            node.pop(key)

    if "properties" in node:
        node["properties"] = {k: _inline(v, defs, depth + 1) for k, v in node["properties"].items()}
    if isinstance(node.get("items"), dict):
        node["items"] = _inline(node["items"], defs, depth + 1)
    for combinator in ("anyOf", "oneOf"):
        if combinator in node:
            node[combinator] = [_inline(b, defs, depth + 1) for b in node[combinator]]

    return node


def list_models(host: str | None = None, timeout: float = 3.0) -> list[str]:
    """Model names installed on the Ollama server, or [] if it is not reachable.

    Used to populate the picker in the UI. Asking the server beats hard-coding a
    list of names that may not be installed on this machine.
    """
    url = f"{host or config.OLLAMA_HOST}/api/tags"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:  # noqa: BLE001 - any failure here means "cannot offer a list"
        return []
    names = [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
    return sorted(names)


def server_status(host: str | None = None, timeout: float = 3.0) -> tuple[bool, str]:
    """(reachable, message) for the Ollama server. Never raises."""
    host = host or config.OLLAMA_HOST
    try:
        response = requests.get(f"{host}/api/version", timeout=timeout)
        response.raise_for_status()
        version = response.json().get("version", "unknown")
        return True, f"Ollama {version} at {host}"
    except requests.ConnectionError:
        return False, f"Nothing is listening at {host}. Start Ollama, then try again."
    except Exception as exc:  # noqa: BLE001
        return False, f"{host} did not answer: {exc}"


class OllamaClient:
    """Talks to a local Ollama server. Same surface as `GeminiClient`."""

    provider = "ollama"

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        *,
        reasoning_model: str | None = None,
        num_ctx: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.default_model = model or config.OLLAMA_MODEL
        # One model for everything unless a second is named. Splitting them is
        # occasionally worth it on a small card: a 4B model is enough to pull fields
        # out of a contract, and the budget is better spent on the step that reasons.
        # An explicit `model` with no explicit reasoning model means "use this one
        # throughout" - otherwise picking a model in the UI would silently leave the
        # reasoning steps on whatever the .env happened to say.
        self.reasoning_model = reasoning_model or (
            config.OLLAMA_MODEL_REASONING if model is None else model
        )
        self._num_ctx = num_ctx or config.OLLAMA_NUM_CTX
        self._session = session or requests.Session()
        self._think = config.OLLAMA_THINK if config.OLLAMA_THINK in ("on", "off") else None
        self.last_model_used: str | None = None
        # Present so the UI and CLI can treat both backends the same way. There are
        # no keys here, which is rather the point.
        self.last_key_index: int | None = None
        # Counts and speed from the most recent answer, as a ready-made phrase.
        # Worth more here than on the hosted backend: tokens per second is how you
        # tell a model that fits in VRAM from one that has spilled into system RAM.
        self.last_usage: str | None = None

    # --- Things the UI and CLI ask of both backends ----------------------

    @property
    def key_count(self) -> int:
        """No API keys are involved in a local run."""
        return 0

    @property
    def provider_label(self) -> str:
        return f"local · {self.default_model}"

    @property
    def answered_degraded(self) -> bool:
        """True unless this model has been vouched for on this project's samples.

        Default-on. A local model is used here because it is available and private,
        not because anyone measured it against Dutch labour law, and the report
        should not imply otherwise.
        """
        model = self.last_model_used or self.default_model
        return model not in config.OLLAMA_TRUSTED_MODELS

    @property
    def degraded_reason(self) -> str:
        """The sentence `pipeline.py` puts in the report when this run is degraded.

        The Gemini wording ("used only because the usual ones were unavailable")
        would be false here: running locally was a deliberate choice, and the reader
        is owed the actual reason their confidence figure was lowered.
        """
        return (
            f"This report was produced by {self.last_model_used or self.default_model}, a model running "
            "on this computer rather than on a hosted service. Nothing was uploaded, which is the point "
            "of that choice, but a model this size reads a contract less accurately than the hosted "
            "ones do, so we have lowered our confidence in this report accordingly."
        )

    def model_for(self, role: str) -> str:
        """Which local model does this job."""
        return self.default_model if role == config.ROLE_EXTRACTION else self.reasoning_model

    # --- The call --------------------------------------------------------

    def generate_json(
        self,
        *,
        prompt: str,
        schema_model: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        model: str | None = None,
        role: str = config.ROLE_REASONING,
    ) -> T:
        """Send one prompt, get back a validated instance of `schema_model`.

        Raises the same two exceptions as the Gemini client, so callers that already
        handle a failed step need no new branch: `LLMUnavailable` when the server or
        the model would not answer, `LLMInvalidOutput` when it answered with
        something that does not fit the schema.
        """
        model_id = model or self.model_for(role)

        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "format": schema_for_ollama(schema_model),
            "stream": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": temperature,
                "num_ctx": self._context_for(prompt, system_instruction, model_id),
            },
        }
        if self._think is not None:
            payload["think"] = self._think == "on"

        logger.info(
            "%s: asking %s for %s (~%s tokens of prompt, %s token window)",
            role,
            model_id,
            schema_model.__name__,
            f"{int((len(prompt) + len(system_instruction or '')) / _CHARS_PER_TOKEN):,}",
            f"{payload['options']['num_ctx']:,}",
        )
        started = time.monotonic()

        raw_text = self._post_chat(payload, model_id)
        self.last_model_used = model_id
        logger.info(
            "%s answered in %.1fs%s",
            model_id,
            time.monotonic() - started,
            f" ({self.last_usage})" if self.last_usage else "",
        )

        # Belt and braces: a thinking model can prefix its answer with a reasoning
        # block. The grammar normally prevents that, but a build that emits thinking
        # outside the constraint would otherwise fail validation on valid output.
        raw_text = _strip_thinking(raw_text)

        if not raw_text.strip():
            raise LLMInvalidOutput(
                f"{model_id} returned an empty response. On a local model this usually means the "
                "context window was too small for the prompt, or the model spent its whole answer "
                "on reasoning."
            )

        try:
            return schema_model.model_validate_json(raw_text)
        except ValidationError as exc:
            repaired = _try_repair_json(raw_text)
            if repaired is not None:
                try:
                    return schema_model.model_validate(repaired)
                except ValidationError:
                    pass
            raise LLMInvalidOutput(
                f"{model_id} returned JSON that does not match {schema_model.__name__}: "
                f"{exc.error_count()} validation error(s). Smaller local models fail this way on "
                "deeply nested schemas; a larger model usually fixes it."
            ) from exc

    def _context_for(self, prompt: str, system_instruction: str | None, model_id: str) -> int:
        """How big a context window this one request needs.

        This is the guard that makes the backend safe to hand to a worker. Ollama
        does not reject an over-long prompt; it drops the front of it and answers
        anyway. The front of these prompts is the contract, so the failure mode is a
        fluent, confident report about a document the model never saw - and one that
        is nearly invisible downstream, because the invented quotes would then fail
        the grounding check and be dropped, leaving a report that merely looks thin.

        So: size the window to the prompt, raise it as far as the configured ceiling
        allows, and refuse loudly rather than quietly read half a contract.
        """
        chars = len(prompt) + len(system_instruction or "")
        estimated = int(chars / _CHARS_PER_TOKEN)
        needed = estimated + _OUTPUT_RESERVE_TOKENS
        rounded = -(-needed // _CTX_GRANULARITY) * _CTX_GRANULARITY

        if rounded <= self._num_ctx:
            return self._num_ctx

        if rounded <= config.OLLAMA_MAX_CTX:
            logger.warning(
                "Raising context for %s to %s tokens for this request (prompt is ~%s tokens).",
                model_id,
                rounded,
                estimated,
            )
            return rounded

        raise LLMUnavailable(
            f"This prompt needs about {rounded} tokens of context and the ceiling is "
            f"{config.OLLAMA_MAX_CTX} (CTF_OLLAMA_MAX_CTX). Ollama would silently drop the start of "
            "the document rather than refuse, so we refuse instead. Either raise CTF_OLLAMA_MAX_CTX "
            "if the machine has the memory for it, or lower CTF_MAX_CHARS_PER_DOC so each document "
            "is sent in a smaller piece."
        )

    def _post_chat(self, payload: dict[str, Any], model_id: str) -> str:
        """POST /api/chat, with retries for the failures worth repeating.

        Unlike the Gemini path there is no quota to protect and no second model to
        fail over to, so the rules are simpler: retry what looks transient, and turn
        everything else into a message that names the fix. Almost every first-run
        failure here is one of three things - the server is not running, the model is
        not pulled, or the machine ran out of memory - and each has a different next
        step, so they are reported as three different messages.
        """
        url = f"{self.host}/api/chat"
        last_error: str | None = None

        for attempt in range(config.MAX_RETRIES):
            try:
                response = self._session.post(url, json=payload, timeout=config.OLLAMA_TIMEOUT_S)
            except requests.ConnectionError as exc:
                raise LLMUnavailable(
                    f"Could not reach Ollama at {self.host}. Start it (the desktop app, or "
                    f"`ollama serve`), or switch back to the Gemini API."
                ) from exc
            except requests.Timeout as exc:
                logger.warning("Ollama timed out on %s (attempt %s).", model_id, attempt + 1)
                if attempt == config.MAX_RETRIES - 1:
                    raise LLMUnavailable(
                        f"{model_id} did not answer within {config.OLLAMA_TIMEOUT_S:.0f}s. A model too "
                        "large for this machine's VRAM runs partly from system memory and can be many "
                        "times slower; a smaller model, or a higher CTF_OLLAMA_TIMEOUT, is the fix."
                    ) from exc
                last_error = f"no answer within {config.OLLAMA_TIMEOUT_S:.0f}s"
                continue

            if response.status_code == 200:
                text, self.last_usage = _content_of(response, model_id)
                return text

            detail = _error_detail(response)

            if response.status_code == 404:
                raise LLMUnavailable(
                    f"Ollama does not have the model `{model_id}`. Install it with:  "
                    f"ollama pull {model_id}"
                )

            # Some builds reject `think` on a model with no thinking mode. Drop it
            # and try again rather than failing a run over an optional parameter.
            if response.status_code == 400 and "think" in detail.lower() and "think" in payload:
                logger.warning("%s does not support the thinking parameter; retrying without it.", model_id)
                payload.pop("think", None)
                self._think = None
                continue

            if _is_memory_error(detail):
                raise LLMUnavailable(
                    f"{model_id} does not fit in this machine's memory at the requested context size "
                    f"({payload['options']['num_ctx']} tokens). Use a smaller model, or lower "
                    f"CTF_OLLAMA_NUM_CTX. ({detail})"
                )

            if response.status_code == 400:
                raise LLMUnavailable(f"Ollama rejected the request for {model_id}: {detail}")

            last_error = f"{response.status_code} {detail}"
            if attempt == config.MAX_RETRIES - 1:
                break
            delay = (2**attempt) + random.uniform(0, 0.5)
            logger.warning("Ollama returned %s on %s, retrying in %.1fs.", response.status_code, model_id, delay)
            time.sleep(delay)

        raise LLMUnavailable(f"Ollama did not answer for {model_id}: {last_error}")


def _content_of(response: requests.Response, model_id: str) -> tuple[str, str | None]:
    """The assistant text out of a non-streaming /api/chat response, plus its stats."""
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"{model_id} returned something that is not JSON.") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise LLMUnavailable(f"{model_id}: {payload['error']}")

    message = payload.get("message") or {}
    return message.get("content") or "", _usage_phrase(payload)


def _usage_phrase(payload: dict) -> str | None:
    """`1,204 in / 856 out at 63 tok/s, 4.1s to load` from Ollama's own counters.

    Ollama reports these on every non-streaming response and they answer the two
    questions a local run actually raises: is it using the GPU (tokens per second
    an order of magnitude apart), and did it have to load the weights again (a load
    time on every call means the model is being evicted between steps).
    """
    parts: list[str] = []

    sent = payload.get("prompt_eval_count")
    produced = payload.get("eval_count")
    if sent is not None or produced is not None:
        parts.append(f"{sent or 0:,} tokens in / {produced or 0:,} out")

    eval_ns = payload.get("eval_duration") or 0
    if produced and eval_ns:
        parts.append(f"{produced / (eval_ns / 1e9):.0f} tok/s")

    load_ns = payload.get("load_duration") or 0
    if load_ns > 1e9:
        parts.append(f"{load_ns / 1e9:.1f}s to load the model")

    return ", ".join(parts) or None


def _error_detail(response: requests.Response) -> str:
    """Ollama puts its message in `error`; fall back to the body."""
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])[:300]
    except Exception:  # noqa: BLE001
        pass
    return (response.text or "").strip()[:300] or f"HTTP {response.status_code}"


_MEMORY_MARKERS = (
    "out of memory",
    "insufficient memory",
    "cudamalloc",
    "vram",
    "requires more system memory",
)


def _is_memory_error(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in _MEMORY_MARKERS)


_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove a reasoning block a thinking model may have put before its answer."""
    cleaned = _THINK_BLOCK.sub("", text).strip()
    # An unterminated block means the whole answer was reasoning: nothing usable.
    if cleaned.lower().startswith("<think>"):
        return ""
    return cleaned
