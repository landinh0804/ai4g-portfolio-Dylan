"""Step 1 (ingest) and the JSON schema translation in the LLM client."""

from __future__ import annotations

import pytest

from contract_trap_finder.llm.client import _try_repair_json, sanitise_schema, schema_for
from contract_trap_finder.models import (
    ComposedOutput,
    CrossReferenceResult,
    StructuredDocument,
)
from contract_trap_finder.steps import s1_ingest


# --- ingest ----------------------------------------------------------------


def test_pasted_text_becomes_a_document():
    doc = s1_ingest.from_text("Artikel 1. De werknemer treedt in dienst.", "contract.txt")
    assert doc.text.startswith("Artikel 1")
    assert doc.doc_id.startswith("doc1")


def test_empty_text_is_rejected():
    with pytest.raises(s1_ingest.IngestError):
        s1_ingest.from_text("   ", "empty.txt")


def test_photographs_are_refused_with_an_explanation():
    """The primary user photographs documents. Refusing must be explicit, not silent."""
    with pytest.raises(s1_ingest.UnsupportedFormat) as exc:
        s1_ingest.from_upload("contract.jpg", b"\xff\xd8\xff")
    assert "photograph" in str(exc.value).lower()
    assert "paste" in str(exc.value).lower()


def test_unknown_file_types_are_refused():
    with pytest.raises(s1_ingest.UnsupportedFormat):
        s1_ingest.from_upload("contract.docx", b"PK\x03\x04")


def test_long_documents_are_truncated_with_a_warning():
    from contract_trap_finder import config

    doc = s1_ingest.from_text("x" * (config.MAX_CHARS_PER_DOCUMENT + 500), "long.txt")
    assert len(doc.text) == config.MAX_CHARS_PER_DOCUMENT
    assert doc.warnings


def test_document_ids_are_stable_and_distinct():
    a = s1_ingest.from_text("aaa", "uitzendovereenkomst.txt", index=0)
    b = s1_ingest.from_text("bbb", "huisvesting.txt", index=1)
    assert a.doc_id != b.doc_id


def test_corpus_maps_ids_to_text():
    docs = [s1_ingest.from_text("aaa", "a.txt", 0), s1_ingest.from_text("bbb", "b.txt", 1)]
    corpus = s1_ingest.build_corpus(docs)
    assert set(corpus) == {d.doc_id for d in docs}


def test_samples_on_disk_can_be_ingested(tmp_path):
    from pathlib import Path

    samples = Path(__file__).parent.parent / "samples"
    files = list(samples.glob("*/*.txt"))
    assert files, "sample bundles are missing from the repository"
    for path in files:
        doc = s1_ingest.from_path(path)
        assert doc.char_count > 200


# --- schema translation ----------------------------------------------------


def _walk(node):
    """Yield every dict in a nested schema."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


@pytest.mark.parametrize("model", [StructuredDocument, CrossReferenceResult, ComposedOutput])
def test_schemas_contain_no_refs_after_sanitising(model):
    """Gemini rejects $ref/$defs, which Pydantic emits for every nested model."""
    schema = schema_for(model)
    assert all("$ref" not in node and "$defs" not in node for node in _walk(schema))


@pytest.mark.parametrize("model", [StructuredDocument, CrossReferenceResult, ComposedOutput])
def test_schemas_drop_unsupported_keywords(model):
    schema = schema_for(model)
    for node in _walk(schema):
        assert "additionalProperties" not in node
        assert "default" not in node


def test_optional_fields_become_nullable_rather_than_a_union():
    schema = sanitise_schema(
        {
            "type": "object",
            "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "d"}},
        }
    )
    field = schema["properties"]["x"]
    assert field["type"] == "string"
    assert field["nullable"] is True
    assert field["description"] == "d"


def test_nested_models_are_inlined():
    schema = schema_for(StructuredDocument)
    party_items = schema["properties"]["parties"]["items"]
    assert "properties" in party_items
    assert "name" in party_items["properties"]


def test_literal_enums_survive():
    schema = schema_for(StructuredDocument)
    assert "employment_contract" in schema["properties"]["doc_type"]["enum"]


def test_descriptions_are_preserved():
    """The field descriptions are load-bearing — they are instructions to the model."""
    schema = schema_for(StructuredDocument)
    assert schema["properties"]["extraction_confidence"]["description"]


def test_confidence_fields_are_required_of_the_model():
    """A confidence field the model may omit becomes its default, which is a lie.

    Pydantic leaves every field with a default out of `required`, so Gemini was free
    to skip these two and did. The default then stood in for an answer: 0.0, read
    downstream as "no confidence" and as "the step failed".
    """
    assert "extraction_confidence" in schema_for(StructuredDocument)["required"]
    assert "reasoning_confidence" in schema_for(CrossReferenceResult)["required"]


def test_adding_a_required_field_does_not_drop_the_others():
    """`json_schema_extra` as a dict would replace `required`, not extend it."""
    required = schema_for(StructuredDocument)["required"]
    for name in ("doc_id", "doc_type", "detected_language"):
        assert name in required


def test_every_confidence_field_explains_itself_to_the_model():
    assert schema_for(StructuredDocument)["properties"]["extraction_confidence"]["description"]
    assert schema_for(CrossReferenceResult)["properties"]["reasoning_confidence"]["description"]


# --- truncated JSON recovery ----------------------------------------------


def test_repair_handles_a_fenced_response():
    assert _try_repair_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_repair_closes_a_truncated_object():
    recovered = _try_repair_json('{"findings": [{"id": "A"}, {"id": "B"}')
    assert recovered is not None
    assert recovered["findings"][0]["id"] == "A"


def test_repair_gives_up_rather_than_inventing():
    assert _try_repair_json("not json at all, just prose") is None
