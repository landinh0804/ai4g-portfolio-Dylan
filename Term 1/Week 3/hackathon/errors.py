"""The exception types every LLM backend raises.

They live in their own module because there is now more than one backend, and both
`client.py` (Gemini) and `ollama_client.py` (a model running on the user's own
machine) have to raise the *same* types: `pipeline.py` decides whether to degrade a
report or abandon a step by catching `LLMError`, and it must not have to know which
backend produced the failure.
"""

from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for every failure that comes out of an LLM backend."""


class MissingAPIKey(LLMError):
    """No API key in the environment, for a backend that needs one."""


class LLMUnavailable(LLMError):
    """The backend could not be reached, or kept failing after all retries."""


class LLMInvalidOutput(LLMError):
    """The backend answered, but not with something matching the requested schema."""


class UnknownProvider(LLMError):
    """`build_client` was asked for a backend that does not exist."""
