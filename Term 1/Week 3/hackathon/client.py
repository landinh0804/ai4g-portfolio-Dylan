"""The one place in the codebase that talks to the Gemini API.

The hosted backend. Its peer is `ollama_client.py`, which runs a model on the user's
own machine; the two present the same `generate_json` contract and raise the same
exceptions, so nothing downstream knows or cares which one it was handed.

Everything else calls `generate_json(...)` and gets back a validated Pydantic object
or an exception. Nothing downstream ever sees raw model text, so a malformed or
truncated response cannot leak into a report as if it were a finding.

Three things this module is responsible for:

* Turning a Pydantic model into a schema Gemini will accept (`sanitise_schema`).
  Pydantic emits `$ref`/`$defs`, which the API does not support, so references are
  inlined and unsupported keywords are stripped.
* Choosing, per failure, between retrying the same model and failing over to the
  next candidate - a choice driven by the free tier's per-model daily request
  quota, since a retry and a failover cost the same one request. See
  `_call_with_retries`. Failing loudly rather than silently returning nothing.
* Never logging document text or the API key.
"""

from __future__ import annotations

import copy
import json
import logging
import random
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .. import config
from .errors import LLMError, LLMInvalidOutput, LLMUnavailable, MissingAPIKey

logger = logging.getLogger(__name__)

# Re-exported so `from .client import LLMError` keeps working. The definitions moved
# to `errors.py` when a second backend appeared: both must raise the same types,
# and neither should have to import the other to do it.
__all__ = [
    "GeminiClient",
    "LLMError",
    "LLMInvalidOutput",
    "LLMUnavailable",
    "MissingAPIKey",
    "sanitise_schema",
    "schema_for",
]

T = TypeVar("T", bound=BaseModel)

# Keywords Pydantic emits that the Gemini schema parser rejects or ignores.
_UNSUPPORTED_SCHEMA_KEYS = {
    "title",
    "default",
    "additionalProperties",
    "$schema",
    "$defs",
    "definitions",
    "examples",
    "discriminator",
    "exclusiveMinimum",
    "exclusiveMaximum",
}

_MAX_INLINE_DEPTH = 12


# --- Schema handling -------------------------------------------------------


def sanitise_schema(schema: dict[str, Any], defs: dict[str, Any] | None = None, depth: int = 0) -> dict[str, Any]:
    """Turn a Pydantic JSON schema into one Gemini accepts.

    Inlines `$ref` against `$defs`, drops unsupported keywords, and rewrites
    `const` as a single-value `enum`.
    """
    if depth > _MAX_INLINE_DEPTH:
        # Defensive: a self-referencing model would otherwise recurse forever.
        return {"type": "string"}

    if defs is None:
        defs = schema.get("$defs", {}) or schema.get("definitions", {}) or {}

    node = copy.deepcopy(schema)

    ref = node.pop("$ref", None)
    if ref:
        name = ref.rsplit("/", 1)[-1]
        target = defs.get(name)
        if target is None:
            return {"type": "string"}
        merged = sanitise_schema(target, defs, depth + 1)
        # Keep a sibling description if the reference carried one.
        if "description" in node:
            merged["description"] = node["description"]
        return merged

    for key in list(node):
        if key in _UNSUPPORTED_SCHEMA_KEYS:
            node.pop(key)

    if "const" in node:
        node["enum"] = [node.pop("const")]
        node.setdefault("type", "string")

    if "properties" in node:
        node["properties"] = {k: sanitise_schema(v, defs, depth + 1) for k, v in node["properties"].items()}

    if "items" in node and isinstance(node["items"], dict):
        node["items"] = sanitise_schema(node["items"], defs, depth + 1)

    for combinator in ("anyOf", "oneOf"):
        if combinator in node:
            branches = [sanitise_schema(b, defs, depth + 1) for b in node[combinator]]
            # `X | None` is far better expressed as a nullable X than as a union.
            non_null = [b for b in branches if b.get("type") != "null"]
            if len(non_null) == 1 and len(branches) > len(non_null):
                description = node.get("description")
                node = non_null[0]
                node["nullable"] = True
                if description:
                    node["description"] = description
            else:
                node[combinator] = branches

    return node


def schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Public helper: the Gemini-ready schema for a Pydantic model."""
    return sanitise_schema(model.model_json_schema())


# --- Client ----------------------------------------------------------------


class GeminiClient:
    """Thin, retrying wrapper around `client.models.generate_content`."""

    provider = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        # One explicit key overrides the environment; otherwise take every key the
        # environment offers. See `config.get_api_keys` for why more than one helps.
        self._keys = [api_key] if api_key else config.get_api_keys()
        if not self._keys:
            raise MissingAPIKey(
                "No Gemini API key found. Copy .env.example to .env and set GEMINI_API_KEY, "
                "or export it in your shell. Get a key at https://aistudio.google.com/apikey"
            )
        self.default_model = model or config.MODEL
        # An id passed in here means "use this for everything", and overrides the
        # per-role choice below - otherwise `GeminiClient(model=...)` would be
        # quietly ignored by every step that asks for a role instead of an id.
        self._explicit_model = model
        # Which model actually answered the most recent call. Not always
        # `default_model`: see `_call_with_retries`, which fails over.
        self.last_model_used: str | None = None
        # Which key answered it, as an index. Never the key itself - this object is
        # reachable from the UI layer and a key must not become something that can be
        # printed by accident.
        self.last_key_index: int | None = None
        # Token counts from the most recent answer, as a ready-made phrase. Shown
        # live by both front-ends; never contains prompt or document text.
        self.last_usage: str | None = None
        # Sticky for the life of this client: see `_candidate_models`.
        self._preferred_model: str | None = None
        self._preferred_key = 0
        # Keys that answered 401/403: broken rather than busy, so stop trying them.
        self._dead_keys: set[int] = set()
        # (key index, model) pairs that have spent their daily quota during this run.
        # Re-asking costs a request and the answer cannot have changed.
        self._exhausted: set[tuple[int, str]] = set()
        self._clients: dict[int, Any] = {}

    @property
    def key_count(self) -> int:
        """How many keys are in the rota. Shown in the UI banner, never the keys."""
        return len(self._keys)

    @property
    def answered_degraded(self) -> bool:
        """True when the last answer came from a model we do not trust for this work.

        Read by `pipeline.py`. The alternative - letting a `-lite` model's output
        through at full confidence because it was the only thing serving - is the
        failure mode this whole fallback chain risks introducing.
        """
        return config.is_degraded_model(self.last_model_used)

    @property
    def degraded_reason(self) -> str:
        """The sentence `pipeline.py` puts in the report when this run is degraded.

        Each backend words this itself, because the reasons are not the same thing:
        here it is an outage we fell back from, and locally it is a choice the user
        made. Telling a reader their confidence was lowered without saying why is
        the one version that helps nobody.
        """
        return (
            f"This report was produced by {self.last_model_used}, a smaller model used only "
            "because the usual ones were unavailable. It is less reliable at reading contracts, "
            "so we have lowered our confidence in this report accordingly."
        )

    @property
    def provider_label(self) -> str:
        """How the UI and the CLI banner name this backend in one short phrase."""
        return f"Gemini API · {self.default_model}"

    def model_for(self, role: str) -> str:
        """Which model does this job.

        Steps name a *role* rather than a model id, so that the same pipeline can be
        pointed at a backend whose model ids look nothing like these.
        """
        if self._explicit_model:
            return self._explicit_model
        return config.MODEL if role == config.ROLE_EXTRACTION else config.MODEL_REASONING

    def _client_for(self, key_index: int):
        """The SDK client for one key, built once and reused."""
        if key_index not in self._clients:
            self._clients[key_index] = self._build_client(self._keys[key_index])
        return self._clients[key_index]

    def _build_client(self, api_key: str):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - environment problem, not logic
            raise LLMUnavailable(
                "The google-genai package is not installed. Run: pip install -r requirements.txt"
            ) from exc

        # Two things the default client gets wrong for this tool:
        #
        # `timeout` — without it there is no deadline at all, so a model that has
        # stopped serving hangs the pipeline silently instead of raising. The SDK
        # takes milliseconds; config stores seconds. Note this is sent to Google as
        # the request deadline, not merely enforced locally — see config.
        #
        # `retry_options(attempts=1)` — the SDK retries 5xx internally via tenacity.
        # Left on, it multiplies against `_call_with_retries` below, so one logical
        # call becomes a dozen HTTP requests and minutes of wall clock. One retry
        # policy, owned here, is what we want.
        http_options = types.HttpOptions(
            timeout=int(config.REQUEST_TIMEOUT_S * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        return genai.Client(api_key=api_key, http_options=http_options)

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

        Raises `LLMUnavailable` if the API never answered, and `LLMInvalidOutput` if
        it answered with something that does not fit the schema. Callers are
        expected to handle both — see `pipeline.py`, where a failed step degrades
        the report rather than crashing it.
        """
        from google.genai import types

        model_id = model or self.model_for(role)
        response_schema = schema_for(schema_model)

        cfg_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_json_schema": response_schema,
        }
        if system_instruction:
            cfg_kwargs["system_instruction"] = system_instruction

        # Narration, not diagnostics: both front-ends surface these live, because a
        # run that spends ninety seconds inside one call should say which call.
        logger.info(
            "%s: asking %s for %s (~%s tokens of prompt)",
            role,
            model_id,
            schema_model.__name__,
            f"{_estimate_tokens(prompt, system_instruction):,}",
        )
        started = time.monotonic()

        raw_text = self._call_with_retries(
            model_id=model_id,
            prompt=prompt,
            config_obj=types.GenerateContentConfig(**cfg_kwargs),
        )

        # Name the model that actually answered, which after a failover is not
        # necessarily the one that was asked for.
        answered_by = self.last_model_used or model_id
        logger.info(
            "%s answered in %.1fs%s",
            answered_by,
            time.monotonic() - started,
            f" ({self.last_usage})" if self.last_usage else "",
        )

        if not raw_text or not raw_text.strip():
            raise LLMInvalidOutput(f"{answered_by} returned an empty response.")

        try:
            return schema_model.model_validate_json(raw_text)
        except ValidationError as exc:
            # A truncated response is the common cause. Try one repair pass on the
            # raw JSON before giving up, then fail rather than guess.
            repaired = _try_repair_json(raw_text)
            if repaired is not None:
                try:
                    return schema_model.model_validate(repaired)
                except ValidationError:
                    pass
            raise LLMInvalidOutput(
                f"{answered_by} returned JSON that does not match {schema_model.__name__}: {exc.error_count()} validation error(s)."
            ) from exc

    def _candidate_models(self, model_id: str) -> list[str]:
        """Candidates in the order we should try them.

        A model that has already answered this session goes first. Without that,
        every step of the pipeline re-discovers the same outage from scratch: the
        primary is down, so each call pays a full deadline per dead candidate before
        reaching a live one. Measured on a single call during the outage that
        prompted this, that rediscovery cost 111s — multiplied by every LLM step in
        `pipeline.py`, which is the difference between a slow report and no report.

        The preference lasts only as long as the process, so a fresh run always
        gives the pinned model another chance.
        """
        ordered: list[str] = []
        if self._preferred_model:
            ordered.append(self._preferred_model)
        for candidate in (model_id, *config.MODEL_FALLBACKS):
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _key_order(self) -> list[int]:
        """Key indices to try, the one that last worked first."""
        ordered = [self._preferred_key] if self._preferred_key < len(self._keys) else []
        ordered += [i for i in range(len(self._keys)) if i not in ordered]
        return [i for i in ordered if i not in self._dead_keys]

    def _attempt(self, key_index: int, model: str, prompt: str, config_obj: Any):
        """One (key, model) pair, with retries for the failures worth repeating.

        Returns `(text, outcome, error)`. `outcome` is one of `ok`, `bad_request`,
        `bad_key`, `quota`, `model_down`, `error` - the caller decides whether that
        means try another key or another model.
        """
        last_error: Exception | None = None
        for attempt in range(config.MAX_RETRIES):
            try:
                response = self._client_for(key_index).models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config_obj,
                )
                self.last_usage = _usage_phrase(response)
                return response.text or "", "ok", None
            except Exception as exc:  # noqa: BLE001 - the SDK raises several unrelated types
                last_error = exc
                if _is_bad_key(exc):
                    return None, "bad_key", exc
                if _is_bad_request(exc):
                    return None, "bad_request", exc
                if _is_quota_exhausted(exc):
                    return None, "quota", exc
                if _model_is_down(exc):
                    return None, "model_down", exc
                if not _is_retryable(exc) or attempt == config.MAX_RETRIES - 1:
                    return None, "error", exc
                delay = (2**attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Gemini call failed (attempt %s/%s on %s), retrying in %.1fs: %s",
                    attempt + 1,
                    config.MAX_RETRIES,
                    model,
                    delay,
                    _describe(exc),
                )
                time.sleep(delay)
        return None, "error", last_error

    def _call_with_retries(self, *, model_id: str, prompt: str, config_obj: Any) -> str:
        """Try each candidate model, and each key, until something answers.

        Two axes, because the failures they fix are different things:

        * **429, spent quota** - a fact about *this key on this model*. The free tier
          meters requests per key per model per day, so another key is another whole
          allowance: switch key, keep the model. This is the only way to raise a
          free-tier ceiling without paying, which is why pooling keys works.
        * **503, overloaded** - a fact about *the model*, shared by everyone on
          Google's infrastructure. Another key sees the identical 503, so trying one
          is a wasted request: switch model, keep the key.
        * **401/403** - a fact about *the key*: broken rather than busy. Drop it from
          the rota and carry on, rather than failing a run the other keys could
          finish.
        * **400** - a fact about *the request*, which no key and no model can fix.
          Abort, so the real error is not buried under a dozen identical failures.

        Nothing here retries an overloaded model. On a metered key each attempt costs
        one of ~20 daily requests for that model, and a failover costs the same one
        request with better odds. Only 500 INTERNAL - a server-side fault on this one
        request rather than a statement about capacity - is retried in place.
        """
        last_error: Exception | None = None
        outcomes: dict[str, str] = {}
        candidates = self._candidate_models(model_id)

        for position, candidate in enumerate(candidates):
            outcome = "no keys left"
            for key_index in self._key_order():
                if (key_index, candidate) in self._exhausted:
                    continue

                text, result, error = self._attempt(key_index, candidate, prompt, config_obj)
                if error is not None:
                    last_error = error

                if result == "ok":
                    if candidate != model_id and self._preferred_model != candidate:
                        logger.warning(
                            "Answered by fallback model %s (%s was unavailable).",
                            candidate,
                            model_id,
                        )
                    if key_index != self._preferred_key:
                        logger.warning(
                            "Switched to API key %s of %s.", key_index + 1, len(self._keys)
                        )
                    self.last_model_used = candidate
                    self.last_key_index = key_index
                    self._preferred_model = candidate
                    self._preferred_key = key_index
                    return text or ""

                if result == "bad_request":
                    raise LLMUnavailable(f"{candidate} rejected the request: {error}") from error

                if result == "bad_key":
                    # Not a reason to give up on the run: the other keys are fine.
                    logger.warning(
                        "API key %s of %s was rejected (%s); dropping it for this run.",
                        key_index + 1,
                        len(self._keys),
                        _describe(error) if error else "unknown",
                    )
                    self._dead_keys.add(key_index)
                    outcome = "key rejected"
                    continue

                if result == "quota":
                    self._exhausted.add((key_index, candidate))
                    outcome = "daily quota spent"
                    continue  # another key has its own allowance for this model

                # model_down / error: every key would see the same thing.
                outcome = _describe(error) if error else "no response"
                break

            outcomes[candidate] = outcome
            if position < len(candidates) - 1:
                # Name the actual status. `ServerError` alone cannot distinguish an
                # overloaded model from a hung one from a broken request.
                logger.warning(
                    "%s is not answering (%s). Falling back to %s.",
                    candidate,
                    outcome,
                    candidates[position + 1],
                )

        raise LLMUnavailable(
            _exhausted_message(candidates, outcomes, last_error, len(self._keys))
        ) from last_error


def _exhausted_message(
    candidates: list[str],
    outcomes: dict[str, str],
    last_error: Exception | None,
    key_count: int,
) -> str:
    """The message shown when nothing answered.

    "No model answered" is true but useless: waiting ten minutes fixes an overload
    and does nothing at all for a spent daily quota, and the user cannot tell which
    they have unless we say so.
    """
    reasons = [outcomes.get(c, "no response") for c in candidates]
    detail = ", ".join(f"{c} ({outcomes.get(c, 'no response')})" for c in candidates)

    if reasons and all(r == "daily quota spent" for r in reasons):
        whose = "This key has" if key_count == 1 else f"All {key_count} keys have"
        extra = (
            " Adding a second key to .env as GEMINI_API_KEY_2 would give another allowance."
            if key_count == 1
            else ""
        )
        headline = (
            f"Every model has used up its free-tier daily request quota. {whose} run out, "
            f"and this resets on Google's schedule, not ours.{extra}"
        )
    elif any(r == "daily quota spent" for r in reasons):
        headline = (
            "No model answered: some are overloaded and the rest have spent their free-tier "
            "daily request quota."
        )
    else:
        headline = (
            "No model answered. Google is shedding load across these models, which is usually "
            "temporary - trying again in a few minutes often works."
        )
    return f"{headline} Tried: {detail}. Last error: {last_error}"


def _usage_phrase(response: Any) -> str | None:
    """`1,204 in / 856 out` from the response's usage metadata, if it carries any."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    sent = getattr(usage, "prompt_token_count", None)
    produced = getattr(usage, "candidates_token_count", None)
    if sent is None and produced is None:
        return None
    return f"{sent or 0:,} tokens in / {produced or 0:,} out"


def _estimate_tokens(prompt: str, system_instruction: str | None) -> int:
    """A rough token count for a log line. Never worth an API round trip."""
    return int((len(prompt) + len(system_instruction or "")) / 3.5)


def _status_code(exc: Exception) -> int | None:
    """The HTTP status behind an SDK exception, or None if it is not an API error.

    `google.genai` sets `.code` on every `APIError`, which is far more reliable than
    grepping the message: the 429 body alone contains a retry hint ("retry in
    42.53s") and two documentation URLs, all of which look like status codes to a
    loose substring match. The message is only consulted as a fallback, anchored to
    the front of the string where the SDK puts the code.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    match = re.match(r"\s*(\d{3})\b", str(exc))
    return int(match.group(1)) if match else None


def _status_name(exc: Exception) -> str:
    """`RESOURCE_EXHAUSTED`, `UNAVAILABLE`, ... - the SDK's `status`, or the message."""
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status:
        return status
    return str(exc)


def _describe(exc: Exception) -> str:
    """One short phrase for a log line. `ServerError` on its own says nothing: 500,
    503 and 504 arrive as the same class and call for three different responses."""
    code = _status_code(exc)
    if code is None:
        return type(exc).__name__
    # When `status` is absent we fall back to the message, which already opens with
    # the code - so drop it rather than logging "503 503 UNAVAILABLE".
    name = _status_name(exc).split(".")[0].strip()
    name = name.removeprefix(str(code)).strip()
    return f"{code} {name[:40]}" if name else str(code)


# What Google actually says when a key is wrong. It arrives as 400 INVALID_ARGUMENT
# rather than 401/403, so the status code alone cannot tell a bad key from a bad
# request - and the difference decides whether one person's expired key ends
# everybody's run.
_BAD_KEY_MARKERS = ("api_key_invalid", "api key not valid", "api key", "unauthenticated", "permission")


def _is_bad_key(exc: Exception) -> bool:
    """This key is broken rather than busy: drop it and carry on with the others.

    Checked before `_is_bad_request`, because Google reports an invalid key as
    400 INVALID_ARGUMENT with `reason: API_KEY_INVALID` in the body. Reading only the
    status would classify it as a malformed request and abort a run that the rest of
    the rota could finish - observed against the live API, not hypothesised.
    """
    if _status_code(exc) in (401, 403):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _BAD_KEY_MARKERS)


def _is_bad_request(exc: Exception) -> bool:
    """400 - the request itself is wrong, so no key and no model will accept it."""
    if _is_bad_key(exc):
        return False
    code = _status_code(exc)
    if code is not None:
        return code == 400
    text = f"{type(exc).__name__} {exc}".lower()
    return "invalid_argument" in text


def _is_fatal(exc: Exception) -> bool:
    """Errors no retry can fix. Kept for callers not interested in which kind."""
    return _is_bad_request(exc) or _is_bad_key(exc)


def _is_quota_exhausted(exc: Exception) -> bool:
    """429 - this key has spent its allowance for this model.

    Kept separate from `_model_is_down` because the remedy differs for the user
    (wait, or use a different key) even though the immediate handling is the same:
    move to the next model, which is metered separately.
    """
    if _status_code(exc) == 429:
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return "resource_exhausted" in text or "rate limit" in text


def _model_is_down(exc: Exception) -> bool:
    """This particular model will not serve us - try a different one, now.

    Observed in practice, all on models that `models.list()` happily reports:
    503 UNAVAILABLE ("currently experiencing high demand"), 504 DEADLINE_EXCEEDED
    after the request simply hangs, and 404 NOT_FOUND for a retired id.
    """
    code = _status_code(exc)
    if code in (404, 503, 504):
        return True
    if code is not None:
        return False
    text = f"{type(exc).__name__} {exc}".lower()
    return any(m in text for m in ("unavailable", "deadline", "timeout", "timedout", "not_found"))


def _is_retryable(exc: Exception) -> bool:
    """Worth another go at the *same* model.

    Only 500 INTERNAL qualifies. A 500 is a genuine server-side fault specific to
    one request, so the same request may well succeed on a second attempt. Every
    other transient-looking failure is handled by failing over instead - see
    `_call_with_retries` for why that distinction matters on a metered key.
    """
    if _is_fatal(exc) or _is_quota_exhausted(exc) or _model_is_down(exc):
        return False
    code = _status_code(exc)
    if code is not None:
        return code == 500
    text = f"{type(exc).__name__} {exc}".lower()
    return "internal" in text


def _try_repair_json(text: str) -> Any | None:
    """Best-effort recovery of a truncated JSON object.

    Only used as a second chance before raising. It never invents values; it just
    closes brackets the model did not get to.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        cleaned = cleaned.removeprefix("json").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Truncated response: trim back to a plausible boundary and close what is open.
    # Each candidate is closed using its own bracket stack, so the suffix always
    # matches the text it is appended to.
    for candidate in _truncation_candidates(cleaned):
        closed = _close_brackets(candidate)
        if closed is None:
            continue
        try:
            return json.loads(closed)
        except json.JSONDecodeError:
            continue
    return None


def _truncation_candidates(text: str) -> list[str]:
    """Progressively shorter prefixes to try, longest first."""
    candidates = [text]
    for boundary in ("}", "]", ","):
        idx = text.rfind(boundary)
        while idx > 0 and len(candidates) < 8:
            candidates.append(text[: idx + 1] if boundary != "," else text[:idx])
            idx = text.rfind(boundary, 0, idx)
    # Longest first, de-duplicated.
    seen: set[str] = set()
    ordered: list[str] = []
    for c in sorted(candidates, key=len, reverse=True):
        stripped = c.rstrip().rstrip(",")
        if stripped and stripped not in seen:
            seen.add(stripped)
            ordered.append(stripped)
    return ordered[:8]


def _close_brackets(text: str) -> str | None:
    """Append the closing brackets `text` is missing, or None if it ends mid-string."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()
    if in_string:
        return None
    return text + "".join(reversed(stack))
