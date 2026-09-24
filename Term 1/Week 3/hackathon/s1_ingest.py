"""Step 1 — Ingest. Plain Python, no LLM.

Turns whatever the user has into raw text: pasted text, .txt files, and PDFs with a
text layer.

**Current limitation, stated plainly:** photographs of paper are not yet supported.
The brief's primary user photographs documents on a phone, so this is the single
biggest gap between this prototype and the tool described in section 4. Rather than
silently producing an empty analysis, an image upload raises `UnsupportedFormat`
with a message the UI shows the user. A scanned PDF with no text layer is detected
the same way. It is a stated limitation rather than an open task: see *Current status
and limitations* in the README for the design it would take and what it would cost
the grounding guarantee.
"""

from __future__ import annotations

import io
from pathlib import Path

from pydantic import BaseModel, Field

from .. import config

TEXT_SUFFIXES = {".txt", ".md", ".text"}
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp"}

# Below this many characters, a "successfully read" PDF is almost certainly a scan.
MIN_PLAUSIBLE_TEXT_CHARS = 200


class IngestError(RuntimeError):
    """A document could not be read at all."""


class UnsupportedFormat(IngestError):
    """The format is understood but not handled yet. Message is shown to the user."""


class RawDocument(BaseModel):
    """One document as plain text, before the model has seen it."""

    doc_id: str
    filename: str
    text: str
    source_type: str = Field(description="text, pdf or pasted")
    warnings: list[str] = Field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _make_doc_id(index: int, filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_")[:32]
    return f"doc{index + 1}_{slug}" if slug else f"doc{index + 1}"


def _truncate(text: str, warnings: list[str]) -> str:
    if len(text) <= config.MAX_CHARS_PER_DOCUMENT:
        return text
    warnings.append(
        f"This document is longer than {config.MAX_CHARS_PER_DOCUMENT:,} characters and was shortened "
        "before analysis. Terms near the end may not have been read."
    )
    return text[: config.MAX_CHARS_PER_DOCUMENT]


def from_text(text: str, filename: str = "pasted text", index: int = 0) -> RawDocument:
    """Ingest pasted text or a .txt file."""
    if not text or not text.strip():
        raise IngestError(f"{filename} contains no text.")
    warnings: list[str] = []
    return RawDocument(
        doc_id=_make_doc_id(index, filename),
        filename=filename,
        text=_truncate(text.strip(), warnings),
        source_type="pasted" if filename == "pasted text" else "text",
        warnings=warnings,
    )


def from_pdf_bytes(data: bytes, filename: str, index: int = 0) -> RawDocument:
    """Extract the text layer of a PDF.

    Raises `UnsupportedFormat` when the PDF turns out to be a scan, because an
    almost-empty extraction would otherwise be analysed as if it were the whole
    contract, and "we found no problems" is exactly the wrong answer to give someone
    whose contract we could not actually read.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment problem
        raise IngestError("The pypdf package is not installed. Run: pip install -r requirements.txt") from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise IngestError(f"{filename} is password-protected and cannot be opened.") from exc

        pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page should not lose the document
                warnings.append(f"Page {page_number} of {filename} could not be read.")
                pages.append("")
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"{filename} could not be opened as a PDF: {exc}") from exc

    text = "\n\n".join(p.strip() for p in pages if p.strip())

    if len(text) < MIN_PLAUSIBLE_TEXT_CHARS:
        raise UnsupportedFormat(
            f"{filename} appears to be a scan or photograph rather than a text PDF — we could only "
            f"read {len(text)} characters from it. This prototype cannot read documents from images "
            "yet. Please paste the text, or upload a PDF that you can select text in."
        )

    if any("could not be read" in w for w in warnings):
        warnings.append("Some pages were unreadable, so this analysis may be based on an incomplete document.")

    return RawDocument(
        doc_id=_make_doc_id(index, filename),
        filename=filename,
        text=_truncate(text, warnings),
        source_type="pdf",
        warnings=warnings,
    )


def from_upload(filename: str, data: bytes, index: int = 0) -> RawDocument:
    """Dispatch on file extension. The entry point the Streamlit app uses."""
    suffix = Path(filename).suffix.lower()

    if suffix in PDF_SUFFIXES:
        return from_pdf_bytes(data, filename, index)

    if suffix in TEXT_SUFFIXES:
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return from_text(data.decode(encoding), filename, index)
            except UnicodeDecodeError:
                continue
        raise IngestError(f"{filename} is not readable as text in any encoding we tried.")

    if suffix in IMAGE_SUFFIXES:
        raise UnsupportedFormat(
            f"{filename} is a photograph. This prototype reads text and PDFs only — reading "
            "photographed documents is the next thing we are building. For now, please paste the "
            "text of the document instead."
        )

    raise UnsupportedFormat(
        f"We cannot read {suffix or 'this file type'} files. Supported: .txt and .pdf, or paste the text directly."
    )


def from_path(path: str | Path, index: int = 0) -> RawDocument:
    """Ingest from disk. Used by the CLI and the tests."""
    path = Path(path)
    if not path.exists():
        raise IngestError(f"File not found: {path}")
    return from_upload(path.name, path.read_bytes(), index)


def build_corpus(documents: list[RawDocument]) -> dict[str, str]:
    """`{doc_id: text}` — what `safety.verify_quote` checks every quote against."""
    return {doc.doc_id: doc.text for doc in documents}
