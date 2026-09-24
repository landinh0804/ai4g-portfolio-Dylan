"""LLM access. Prompts live as markdown files, not as string literals in the code.

Keeping them as separate files means a prompt change is a readable diff, and the
person tuning the wording does not have to edit Python to do it.

There are two backends behind `build_client`: the Gemini API, and a model running on
the user's own machine through Ollama. They are interchangeable on purpose - the
same `generate_json` contract, the same exceptions, the same degraded-run signal -
so the pipeline never branches on which one it was given. See `ollama_client.py` for
why the local one is worth having.
"""

from __future__ import annotations

import functools
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from .. import config
from .client import GeminiClient, schema_for
from .errors import (
    LLMError,
    LLMInvalidOutput,
    LLMUnavailable,
    MissingAPIKey,
    UnknownProvider,
)
from .ollama_client import OllamaClient

__all__ = [
    "GeminiClient",
    "LLMClient",
    "LLMError",
    "LLMInvalidOutput",
    "LLMUnavailable",
    "MissingAPIKey",
    "OllamaClient",
    "UnknownProvider",
    "build_client",
    "load_prompt",
    "resolve_provider",
    "schema_for",
]

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """What the pipeline needs from a backend, and nothing else.

    Written as a Protocol rather than a base class so the test doubles in
    `tests/` and `scripts/demo_offline.py` keep satisfying it without inheriting
    from anything.
    """

    provider: str
    last_model_used: str | None

    @property
    def answered_degraded(self) -> bool: ...

    def generate_json(
        self,
        *,
        prompt: str,
        schema_model: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        model: str | None = None,
        role: str = ...,
    ) -> T: ...


def resolve_provider(name: str | None = None) -> str:
    """Normalise a provider name, falling back to the configured default."""
    chosen = (name or config.DEFAULT_PROVIDER or "gemini").strip().lower()
    if chosen not in config.PROVIDERS:
        raise UnknownProvider(
            f"Unknown provider {chosen!r}. Choose one of: {', '.join(config.PROVIDERS)}."
        )
    return chosen


def build_client(provider: str | None = None, model: str | None = None, **kwargs: Any) -> LLMClient:
    """The one place that decides which backend a run uses.

    `provider` comes from the UI selector or `--provider`; with nothing passed it
    follows CTF_PROVIDER, and with that unset it is the Gemini API, which is what
    the hosted tool serves.
    """
    chosen = resolve_provider(provider)
    if chosen == "ollama":
        return OllamaClient(model=model, **kwargs)
    return GeminiClient(model=model, **kwargs)


class PromptNotFound(LLMError):
    pass


@functools.lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a system prompt by name, e.g. `load_prompt("structure")`."""
    path = config.PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptNotFound(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
