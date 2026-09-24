"""Failover behaviour in the LLM client.

These exist because of a real outage: `gemini-3.8-flash` was listed by
`models.list()` and still would not serve, returning 504 after hanging, while
neighbouring models returned 503 "experiencing high demand" and others answered
normally. A worker waiting on a contract review should not be told nothing was
found because one model id was having a bad afternoon.

Nothing here touches the network. The SDK call is replaced with a scripted stub.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from contract_trap_finder import config
from contract_trap_finder.llm import client as client_module
from contract_trap_finder.llm.client import (
    GeminiClient,
    LLMUnavailable,
    _is_fatal,
    _is_quota_exhausted,
    _is_retryable,
    _model_is_down,
    _status_code,
)


class FakeAPIError(Exception):
    """Shaped like `google.genai.errors.APIError`, which carries `code`/`status`."""

    def __init__(self, code: int, status: str, message: str = "") -> None:
        super().__init__(f"{code} {status}. {message}")
        self.code = code
        self.status = status


class Answer(BaseModel):
    verdict: str


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    """Returns a scripted outcome per model id and records what was asked.

    Outcomes are looked up by `(key_index, model)` first and then by `model`, so a
    test can script one key differently from another without restating the rest.
    """

    def __init__(self, outcomes: dict, key_index: int, log: list) -> None:
        self.outcomes = outcomes
        self.key_index = key_index
        self.log = log

    def generate_content(self, *, model, contents, config):  # noqa: A002 - SDK signature
        self.log.append((self.key_index, model))
        outcome = self.outcomes.get((self.key_index, model))
        if outcome is None:
            outcome = self.outcomes.get(model)
        if outcome is None:
            raise RuntimeError("404 NOT_FOUND. This model is not available.")
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


class FakeSDK:
    """What `attach` hands back: the shared call log across every key."""

    def __init__(self, log: list) -> None:
        self.log = log

    @property
    def calls(self) -> list[str]:
        """Model ids in call order, for tests that do not care about keys."""
        return [model for _key, model in self.log]

    @property
    def pairs(self) -> list[tuple[int, str]]:
        """(key index, model) in call order."""
        return list(self.log)


def make_client(monkeypatch, keys: int = 1) -> GeminiClient:
    monkeypatch.setattr(config, "get_api_keys", lambda: [f"key-{i}" for i in range(keys)])
    monkeypatch.setattr(GeminiClient, "_build_client", lambda self, api_key: object())
    monkeypatch.setattr(config, "MODEL_FALLBACKS", ("model-b", "model-c"))
    # Backoff is real time; the tests assert call counts, not wall clock.
    monkeypatch.setattr(client_module.time, "sleep", lambda _s: None)
    return GeminiClient(model="model-a")


@pytest.fixture
def client(monkeypatch):
    """A single-key GeminiClient with the network replaced."""
    return make_client(monkeypatch, keys=1)


@pytest.fixture
def team_client(monkeypatch):
    """Three pooled keys, as four friends sharing free-tier allowances would have."""
    return make_client(monkeypatch, keys=3)


def attach(client: GeminiClient, outcomes: dict) -> FakeSDK:
    log: list = []
    for index in range(client.key_count):
        stub = type("Stub", (), {"models": FakeModels(outcomes, index, log)})()
        client._clients[index] = stub
    return FakeSDK(log)


# --- error classification# --- error classification --------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "503 UNAVAILABLE. This model is currently experiencing high demand.",
        "504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.",
        "404 NOT_FOUND. This model is not found.",
    ],
)
def test_outage_errors_mark_the_model_as_down(message):
    assert _model_is_down(RuntimeError(message))


def test_an_internal_error_is_retried_on_the_same_model():
    """500 is a fault in one request, not a statement about capacity."""
    exc = RuntimeError("500 INTERNAL")
    assert _is_retryable(exc)
    assert not _model_is_down(exc)
    assert not _is_quota_exhausted(exc)


def test_a_spent_quota_is_never_retried_on_the_same_model():
    """429 means this key is done with this model; a retry just spends another
    request from the twenty the free tier allows per model per day."""
    exc = RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota.")
    assert _is_quota_exhausted(exc)
    assert not _is_retryable(exc)


def test_status_is_read_from_the_sdk_error_not_the_message():
    """The 429 body contains "retry in 42.53s" and two doc URLs; a loose substring
    match over that text finds numbers that are not status codes."""
    exc = FakeAPIError(429, "RESOURCE_EXHAUSTED", "Please retry in 42.530313933s.")
    assert _status_code(exc) == 429
    assert _is_quota_exhausted(exc)
    assert not _model_is_down(exc)
    assert not _is_retryable(exc)


def test_overload_and_hang_are_told_apart_from_a_spent_quota():
    assert _model_is_down(FakeAPIError(503, "UNAVAILABLE", "high demand"))
    assert _model_is_down(FakeAPIError(504, "DEADLINE_EXCEEDED"))
    assert not _is_quota_exhausted(FakeAPIError(503, "UNAVAILABLE"))


def test_a_bad_key_is_fatal_not_retryable():
    exc = RuntimeError("400 INVALID_ARGUMENT. API key not valid.")
    assert _is_fatal(exc)
    assert not _is_retryable(exc)


# --- failover --------------------------------------------------------------


def test_falls_over_to_the_next_model_when_the_primary_is_down(client):
    models = attach(
        client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE. High demand."),
            "model-b": '{"verdict": "illegal"}',
        },
    )
    result = client.generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "illegal"
    assert client.last_model_used == "model-b"
    assert models.calls == ["model-a", "model-b"]


def test_a_down_model_is_not_retried_before_failing_over(client):
    """503 means "not now"; a second 45s deadline on it is latency, not resilience."""
    models = attach(
        client,
        {
            "model-a": RuntimeError("504 DEADLINE_EXCEEDED."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    client.generate_json(prompt="x", schema_model=Answer)
    assert models.calls.count("model-a") == 1


def test_a_spent_quota_fails_over_instead_of_retrying(client):
    """The old behaviour retried here. On a metered key that spends three requests
    to learn what the first response already said, and leaves less for the models
    that could still answer."""
    models = attach(
        client,
        {
            "model-a": RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    result = client.generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "ok"
    assert models.calls == ["model-a", "model-b"]


def test_an_internal_error_does_retry_before_failing_over(client):
    models = attach(
        client,
        {
            "model-a": RuntimeError("500 INTERNAL"),
            "model-b": '{"verdict": "ok"}',
        },
    )
    client.generate_json(prompt="x", schema_model=Answer)
    assert models.calls.count("model-a") == config.MAX_RETRIES


def test_exhausted_quota_everywhere_says_so_rather_than_blaming_capacity(client):
    """"Try again in a few minutes" is wrong advice for a quota that resets daily."""
    attach(
        client,
        {
            name: RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota.")
            for name in ("model-a", "model-b", "model-c")
        },
    )
    with pytest.raises(LLMUnavailable) as exc:
        client.generate_json(prompt="x", schema_model=Answer)
    assert "daily request quota" in str(exc.value)


def test_an_overload_everywhere_suggests_waiting(client):
    attach(
        client,
        {name: RuntimeError("503 UNAVAILABLE. High demand.") for name in ("model-a", "model-b", "model-c")},
    )
    with pytest.raises(LLMUnavailable) as exc:
        client.generate_json(prompt="x", schema_model=Answer)
    assert "shedding load" in str(exc.value)


def test_the_failover_log_names_the_status_not_the_exception_class(client, caplog):
    """`ServerError` covers 500, 503 and 504, which need three different responses."""
    attach(
        client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE. High demand."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    with caplog.at_level("WARNING"):
        client.generate_json(prompt="x", schema_model=Answer)
    fallback_logs = [r.getMessage() for r in caplog.records if "not answering" in r.getMessage()]
    assert fallback_logs and "503" in fallback_logs[0]


def test_answering_from_a_lite_model_is_marked_degraded(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_FALLBACKS", ("model-b-lite",))
    attach(
        client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE."),
            "model-b-lite": '{"verdict": "ok"}',
        },
    )
    client.generate_json(prompt="x", schema_model=Answer)
    assert client.last_model_used == "model-b-lite"
    assert client.answered_degraded


def test_a_rejected_key_ends_the_run_when_it_is_the_only_one(client):
    models = attach(client, {"model-a": RuntimeError("403 PERMISSION_DENIED. API key not valid.")})
    with pytest.raises(LLMUnavailable):
        client.generate_json(prompt="x", schema_model=Answer)
    # One call: the key is dropped, and with no other key there is nothing to try.
    assert models.calls == ["model-a"]


def test_a_malformed_request_aborts_without_churning_through_models(client):
    """400 is about the request, so every model and key would refuse it identically."""
    models = attach(client, {"model-a": RuntimeError("400 INVALID_ARGUMENT. Bad schema.")})
    with pytest.raises(LLMUnavailable):
        client.generate_json(prompt="x", schema_model=Answer)
    assert models.calls == ["model-a"]


def test_exhausting_every_candidate_raises_and_names_them(client):
    attach(client, {})
    with pytest.raises(LLMUnavailable) as exc:
        client.generate_json(prompt="x", schema_model=Answer)
    for name in ("model-a", "model-b", "model-c"):
        assert name in str(exc.value)


# --- stickiness ------------------------------------------------------------


def test_a_working_model_is_reused_so_later_steps_skip_the_dead_one(client):
    models = attach(
        client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    client.generate_json(prompt="x", schema_model=Answer)
    client.generate_json(prompt="y", schema_model=Answer)
    # The dead primary is probed once, not once per pipeline step.
    assert models.calls == ["model-a", "model-b", "model-b"]


def test_the_fallback_is_announced_once_not_once_per_call(client, caplog):
    """The pipeline makes several calls; one outage should produce one warning."""
    attach(
        client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    with caplog.at_level("WARNING"):
        for _ in range(3):
            client.generate_json(prompt="x", schema_model=Answer)

    announcements = [r for r in caplog.records if "Answered by fallback model" in r.getMessage()]
    assert len(announcements) == 1


# --- pooled keys -----------------------------------------------------------


def test_a_spent_quota_switches_key_and_keeps_the_model(team_client):
    """Quota is metered per key per model, so another key is another allowance -
    and the model we wanted is still the best one available."""
    models = attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    result = team_client.generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "ok"
    assert team_client.last_model_used == "model-a"
    assert team_client.last_key_index == 1
    assert models.pairs == [(0, "model-a"), (1, "model-a")]


def test_an_overloaded_model_switches_model_not_key(team_client):
    """503 is Google's shared capacity: every key sees the same thing, so trying the
    others would spend three requests to learn nothing."""
    models = attach(
        team_client,
        {
            "model-a": RuntimeError("503 UNAVAILABLE. High demand."),
            "model-b": '{"verdict": "ok"}',
        },
    )
    team_client.generate_json(prompt="x", schema_model=Answer)
    assert models.pairs == [(0, "model-a"), (0, "model-b")]


def test_a_rejected_key_is_dropped_and_the_run_continues(team_client):
    models = attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("401 UNAUTHENTICATED. API key not valid."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    result = team_client.generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "ok"
    assert models.pairs == [(0, "model-a"), (1, "model-a")]


def test_a_dead_key_is_not_tried_again_later_in_the_run(team_client):
    attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("403 PERMISSION_DENIED."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    team_client.generate_json(prompt="x", schema_model=Answer)
    models = attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("403 PERMISSION_DENIED."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    team_client.generate_json(prompt="y", schema_model=Answer)
    assert 0 not in [key for key, _model in models.pairs]


def test_a_spent_quota_is_remembered_so_later_steps_do_not_re_spend(team_client):
    """The pipeline makes several calls per run. Re-asking a key whose quota is gone
    costs a request and cannot produce a different answer."""
    attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("429 RESOURCE_EXHAUSTED."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    team_client.generate_json(prompt="x", schema_model=Answer)
    models = attach(
        team_client,
        {
            (0, "model-a"): RuntimeError("429 RESOURCE_EXHAUSTED."),
            (1, "model-a"): '{"verdict": "ok"}',
        },
    )
    team_client.generate_json(prompt="y", schema_model=Answer)
    assert models.pairs == [(1, "model-a")]


def test_every_key_exhausted_says_so_and_counts_them(team_client):
    attach(
        team_client,
        {name: RuntimeError("429 RESOURCE_EXHAUSTED.") for name in ("model-a", "model-b", "model-c")},
    )
    with pytest.raises(LLMUnavailable) as exc:
        team_client.generate_json(prompt="x", schema_model=Answer)
    assert "All 3 keys" in str(exc.value)


def test_a_single_key_running_dry_suggests_adding_another(client):
    attach(
        client,
        {name: RuntimeError("429 RESOURCE_EXHAUSTED.") for name in ("model-a", "model-b", "model-c")},
    )
    with pytest.raises(LLMUnavailable) as exc:
        client.generate_json(prompt="x", schema_model=Answer)
    assert "GEMINI_API_KEY_2" in str(exc.value)


def test_google_reports_an_invalid_key_as_400_not_401(team_client):
    """The live API answers an invalid key with 400 INVALID_ARGUMENT and
    `reason: API_KEY_INVALID`. Read as a malformed request, that would abort a run
    the rest of the rota could finish."""
    real = (
        "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. "
        "Please pass a valid API key.', 'status': 'INVALID_ARGUMENT', 'details': "
        "[{'reason': 'API_KEY_INVALID'}]}}"
    )
    assert client_module._is_bad_key(RuntimeError(real))
    assert not client_module._is_bad_request(RuntimeError(real))

    models = attach(
        team_client,
        {(0, "model-a"): RuntimeError(real), (1, "model-a"): '{"verdict": "ok"}'},
    )
    result = team_client.generate_json(prompt="x", schema_model=Answer)
    assert result.verdict == "ok"
    assert models.pairs == [(0, "model-a"), (1, "model-a")]
