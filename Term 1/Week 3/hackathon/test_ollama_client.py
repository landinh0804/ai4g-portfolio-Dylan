"""The local backend: schema handling, context sizing, and the failures it names.

Nothing here touches the network or needs Ollama installed - the HTTP session is a
scripted stub. What is being tested is the part that is easy to get quietly wrong:
an over-long prompt must fail loudly rather than be truncated, a local run must be
reported as degraded, and each of the three first-run failures (server not running,
model not pulled, out of memory) must produce its own message.
"""

from __future__ import annotations

import copy
import json

import pytest
import requests
from pydantic import BaseModel

from contract_trap_finder import config
from contract_trap_finder.config import _normalise_ollama_host
from contract_trap_finder.llm import (
    GeminiClient,
    LLMInvalidOutput,
    LLMUnavailable,
    OllamaClient,
    UnknownProvider,
    build_client,
    resolve_provider,
)
from contract_trap_finder.llm.ollama_client import _strip_thinking, schema_for_ollama


class Answer(BaseModel):
    verdict: str


class Nested(BaseModel):
    """A model with a nested model in it, which is what makes Pydantic emit
    references rather than one flat schema - the case the inliner exists for."""

    answer: Answer
    note: str | None = None


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("no json", self.text, 0)
        return self._payload


class FakeSession:
    """Returns scripted responses in order, recording the payloads it was sent."""

    def __init__(self, *responses) -> None:
        self._responses = list(responses)
        self.sent: list[dict] = []

    def post(self, url, json=None, timeout=None):  # noqa: A002 - requests' signature
        # Copied, not referenced: the real client serialises the payload at send
        # time, and one retry mutates the dict it reuses.
        self.sent.append(copy.deepcopy(json))
        outcome = self._responses.pop(0) if self._responses else FakeResponse(500, {"error": "no script"})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok_response(obj: dict) -> FakeResponse:
    return FakeResponse(200, {"message": {"role": "assistant", "content": json.dumps(obj)}})


def make_client(session: FakeSession, **kwargs) -> OllamaClient:
    return OllamaClient(model="test-model", session=session, **kwargs)


# --- Schema ----------------------------------------------------------------


def test_schema_has_no_refs_left_in_it():
    schema = json.dumps(schema_for_ollama(Nested))
    assert "$ref" not in schema
    assert "$defs" not in schema
    assert "verdict" in schema


def test_schema_drops_documentation_only_keywords():
    schema = schema_for_ollama(Answer)
    assert "title" not in schema
    assert "title" not in schema["properties"]["verdict"]


# --- The happy path --------------------------------------------------------


def test_returns_a_validated_model():
    session = FakeSession(ok_response({"verdict": "yes"}))
    result = make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "yes"


def test_sends_the_schema_and_asks_for_one_shot_json():
    session = FakeSession(ok_response({"verdict": "yes"}))
    make_client(session).generate_json(prompt="x", schema_model=Answer, system_instruction="be brief")

    sent = session.sent[0]
    assert sent["stream"] is False
    assert sent["format"]["properties"]["verdict"]
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]


def test_a_role_chooses_the_model_and_an_explicit_id_overrides_it():
    session = FakeSession(ok_response({"verdict": "y"}), ok_response({"verdict": "y"}))
    client = OllamaClient(model="small", reasoning_model="big", session=session)

    client.generate_json(prompt="x", schema_model=Answer, role=config.ROLE_EXTRACTION)
    client.generate_json(prompt="x", schema_model=Answer, role=config.ROLE_REASONING)

    assert [s["model"] for s in session.sent] == ["small", "big"]


def test_a_model_chosen_in_the_ui_is_used_for_every_step(monkeypatch):
    """Picking one model must not leave the reasoning steps on the .env default."""
    monkeypatch.setattr(config, "OLLAMA_MODEL_REASONING", "from-dot-env")
    session = FakeSession(ok_response({"verdict": "y"}))

    client = OllamaClient(model="picked-in-ui", session=session)
    client.generate_json(prompt="x", schema_model=Answer, role=config.ROLE_COMPOSE)

    assert session.sent[0]["model"] == "picked-in-ui"


# --- Context sizing --------------------------------------------------------
#
# The important one. Ollama truncates an over-long prompt from the front instead of
# rejecting it, and the front of these prompts is the contract.


def test_context_is_raised_to_fit_a_long_prompt(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_MAX_CTX", 65536)
    session = FakeSession(ok_response({"verdict": "y"}))

    client = make_client(session, num_ctx=4096)
    client.generate_json(prompt="x" * 60_000, schema_model=Answer)

    # ~20k tokens of prompt plus the reserved output, well past the 4096 asked for.
    assert session.sent[0]["options"]["num_ctx"] > 20_000


def test_a_prompt_past_the_ceiling_is_refused_rather_than_truncated(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_MAX_CTX", 8192)
    session = FakeSession(ok_response({"verdict": "y"}))

    with pytest.raises(LLMUnavailable) as exc:
        make_client(session, num_ctx=4096).generate_json(prompt="x" * 200_000, schema_model=Answer)

    assert "CTF_OLLAMA_MAX_CTX" in str(exc.value)
    assert not session.sent, "nothing should have been sent"


def test_a_short_prompt_keeps_the_configured_window():
    session = FakeSession(ok_response({"verdict": "y"}))
    make_client(session, num_ctx=8192).generate_json(prompt="short", schema_model=Answer)
    assert session.sent[0]["options"]["num_ctx"] == 8192


# --- The failures worth naming separately ----------------------------------


def test_server_not_running_says_so():
    session = FakeSession(requests.ConnectionError("refused"))
    with pytest.raises(LLMUnavailable) as exc:
        make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert "Could not reach Ollama" in str(exc.value)


def test_a_missing_model_gives_the_pull_command():
    session = FakeSession(FakeResponse(404, {"error": 'model "test-model" not found'}))
    with pytest.raises(LLMUnavailable) as exc:
        make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert "ollama pull test-model" in str(exc.value)


def test_running_out_of_memory_points_at_the_model_size():
    session = FakeSession(FakeResponse(500, {"error": "model requires more system memory than is available"}))
    with pytest.raises(LLMUnavailable) as exc:
        make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert "smaller model" in str(exc.value)


def test_a_timeout_is_retried_then_reported(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRIES", 2)
    session = FakeSession(requests.Timeout("slow"), requests.Timeout("slow"))
    with pytest.raises(LLMUnavailable) as exc:
        make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert "did not answer within" in str(exc.value)
    assert len(session.sent) == 2


def test_output_that_does_not_fit_the_schema_is_rejected():
    session = FakeSession(ok_response({"not_the_field": 1}))
    with pytest.raises(LLMInvalidOutput):
        make_client(session).generate_json(prompt="x", schema_model=Answer)


def test_an_empty_answer_is_rejected_rather_than_returned():
    session = FakeSession(FakeResponse(200, {"message": {"content": "   "}}))
    with pytest.raises(LLMInvalidOutput) as exc:
        make_client(session).generate_json(prompt="x", schema_model=Answer)
    assert "empty response" in str(exc.value)


def test_truncated_json_is_repaired_before_giving_up():
    session = FakeSession(FakeResponse(200, {"message": {"content": '{"verdict": "yes"'}}))
    assert make_client(session).generate_json(prompt="x", schema_model=Answer).verdict == "yes"


def test_the_thinking_parameter_is_dropped_if_the_model_rejects_it(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_THINK", "off")
    session = FakeSession(
        FakeResponse(400, {"error": 'model "test-model" does not support think'}),
        ok_response({"verdict": "yes"}),
    )
    client = make_client(session)

    assert client.generate_json(prompt="x", schema_model=Answer).verdict == "yes"
    assert "think" in session.sent[0]
    assert "think" not in session.sent[1]


def test_a_reasoning_block_before_the_answer_is_stripped():
    session = FakeSession(
        FakeResponse(200, {"message": {"content": '<think>hmm</think>{"verdict": "yes"}'}})
    )
    assert make_client(session).generate_json(prompt="x", schema_model=Answer).verdict == "yes"


def test_an_unterminated_reasoning_block_leaves_nothing_usable():
    assert _strip_thinking("<think>still going") == ""


# --- How a local run is reported -------------------------------------------


def test_a_local_run_is_degraded_by_default(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_TRUSTED_MODELS", ())
    client = OllamaClient(model="test-model", session=FakeSession())
    assert client.answered_degraded
    assert "on this computer" in client.degraded_reason


def test_a_vouched_for_model_is_not_degraded(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_TRUSTED_MODELS", ("test-model",))
    assert not OllamaClient(model="test-model", session=FakeSession()).answered_degraded


def test_the_degraded_note_says_it_was_a_choice_not_an_outage(monkeypatch):
    """The Gemini wording would tell the reader something untrue about a local run."""
    monkeypatch.setattr(config, "OLLAMA_TRUSTED_MODELS", ())
    reason = OllamaClient(model="test-model", session=FakeSession()).degraded_reason
    assert "unavailable" not in reason
    assert "Nothing was uploaded" in reason


# --- Choosing a backend ----------------------------------------------------


def test_build_client_dispatches_on_provider(monkeypatch):
    monkeypatch.setattr(config, "get_api_keys", lambda: ["key"])
    monkeypatch.setattr(GeminiClient, "_build_client", lambda self, api_key: object())

    assert isinstance(build_client("ollama"), OllamaClient)
    assert isinstance(build_client("gemini"), GeminiClient)


def test_an_unknown_provider_is_refused():
    with pytest.raises(UnknownProvider):
        resolve_provider("llamafile")


def test_the_provider_falls_back_to_the_configured_default(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_PROVIDER", "ollama")
    assert resolve_provider(None) == "ollama"


# --- OLLAMA_HOST -----------------------------------------------------------
#
# Ollama writes this variable in server notation. `0.0.0.0` is where it listens,
# not somewhere a client can dial, and reading it back verbatim makes a working
# install look like a stopped one.


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (None, "http://localhost:11434"),
        ("", "http://localhost:11434"),
        ("0.0.0.0:11434", "http://127.0.0.1:11434"),
        ("localhost", "http://localhost:11434"),
        ("192.168.1.5", "http://192.168.1.5:11434"),
        ("http://localhost:11434/", "http://localhost:11434"),
        ("https://box.lan:8443", "https://box.lan:8443"),
        ("[::]:11434", "http://127.0.0.1:11434"),
        ("[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_host_normalisation(given, expected):
    assert _normalise_ollama_host(given) == expected
