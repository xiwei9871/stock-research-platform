from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from pypdf import PdfReader

from stock_research.research_project_v2.canonical import canonical_bytes
from stock_research.research_project_v2.errors import ResearchProjectV2Error


_SPACE = re.compile(r"\s+")
_SEMANTIC_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "th", "td"})
_ALWAYS_HIDDEN = frozenset({"script", "style", "nav", "noscript", "template", "svg"})
_VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})


@dataclass(frozen=True)
class ParsedSection:
    heading: str | None
    locator: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    parser: str
    media_type: str
    title: str | None
    sections: tuple[ParsedSection, ...]


@dataclass(frozen=True)
class ParserLimits:
    max_bytes: int = 25 * 1024 * 1024
    max_sections: int = 100_000
    max_rows: int = 100_000
    max_nodes: int = 100_000
    max_text_chars: int = 10_000_000
    max_cell_chars: int = 1_000_000
    max_string_chars: int = 1_000_000
    max_depth: int = 100


def _invalid(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Document parse failed: {reason}",
        code="RESEARCH_PROJECT_V2_1_PARSE_INVALID",
        details=details,
    )


def _limit(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Document parse limit exceeded: {reason}",
        code="RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED",
        details=details,
    )


def _clean(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _decode(data: bytes, *, allow_bom: bool = False) -> str:
    try:
        return data.decode("utf-8-sig" if allow_bom else "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _invalid("document is not valid UTF-8") from exc


def _check_totals(sections: list[ParsedSection], limits: ParserLimits) -> None:
    if len(sections) > limits.max_sections:
        raise _limit("section count", max_sections=limits.max_sections)
    total = sum(len(section.text) for section in sections)
    if total > limits.max_text_chars:
        raise _limit("text characters", max_text_chars=limits.max_text_chars)


@dataclass
class _HtmlCapture:
    tag: str
    locator: str
    heading: str | None
    chunks: list[str]


class _VisibleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []
        self.title_chunks: list[str] = []
        self._title_depth = 0
        self._hidden_stack: list[bool] = []
        self._captures: list[_HtmlCapture] = []
        self._counts: dict[str, int] = {}
        self._current_heading: str | None = None
        self._table = 0
        self._row = 0
        self._cell = 0

    @property
    def hidden(self) -> bool:
        return any(self._hidden_stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {key.lower(): value for key, value in attrs}
        style = _SPACE.sub("", attr.get("style") or "").lower()
        own_hidden = (
            tag in _ALWAYS_HIDDEN
            or "hidden" in attr
            or (attr.get("aria-hidden") or "").strip().lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        parent_hidden = self.hidden
        self._hidden_stack.append(parent_hidden or own_hidden)
        if self.hidden:
            if tag in _VOID_TAGS:
                self._hidden_stack.pop()
            return
        if tag == "title":
            self._title_depth += 1
        if tag == "table":
            self._table += 1
            self._row = 0
        elif tag == "tr":
            self._row += 1
            self._cell = 0
        if tag not in _SEMANTIC_TAGS:
            if tag in _VOID_TAGS:
                self._hidden_stack.pop()
            return
        if tag in {"th", "td"}:
            self._cell += 1
            locator = f"html:table:{self._table:04d}:row:{self._row:04d}:cell:{self._cell:04d}"
        else:
            self._counts[tag] = self._counts.get(tag, 0) + 1
            locator = f"html:{tag}:{self._counts[tag]:04d}"
        heading = None if tag.startswith("h") else self._current_heading
        self._captures.append(_HtmlCapture(tag, locator, heading, []))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if self._title_depth:
            self.title_chunks.append(data)
        if self._captures:
            self._captures[-1].chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        was_hidden = self.hidden
        if not was_hidden:
            if tag == "title" and self._title_depth:
                self._title_depth -= 1
            if self._captures and self._captures[-1].tag == tag:
                capture = self._captures.pop()
                text = _clean("".join(capture.chunks))
                if text:
                    if tag.startswith("h"):
                        self._current_heading = text
                    self.sections.append(ParsedSection(capture.heading, capture.locator, text))
        if self._hidden_stack:
            self._hidden_stack.pop()


def _parse_html(data: bytes, title_hint: str | None, limits: ParserLimits) -> ParsedDocument:
    parser = _VisibleHTMLParser()
    try:
        parser.feed(_decode(data))
        parser.close()
    except ResearchProjectV2Error:
        raise
    except Exception as exc:
        raise _invalid("unreadable HTML") from exc
    if not parser.sections:
        raise _invalid("HTML has no visible semantic content")
    _check_totals(parser.sections, limits)
    title = _clean(title_hint) if title_hint else _clean("".join(parser.title_chunks)) or None
    return ParsedDocument("stdlib.html.parser", "text/html", title, tuple(parser.sections))


def _parse_pdf(data: bytes, title_hint: str | None, limits: ParserLimits) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise _invalid("encrypted PDF is not accepted")
        if len(reader.pages) > limits.max_sections:
            raise _limit("PDF page count", max_sections=limits.max_sections)
        sections = []
        for index, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            sections.append(ParsedSection(None, f"page:{index}", _clean(extracted), index, index))
        metadata_title = None
        if reader.metadata is not None:
            raw_title = getattr(reader.metadata, "title", None)
            if isinstance(raw_title, str):
                metadata_title = _clean(raw_title) or None
    except ResearchProjectV2Error:
        raise
    except Exception as exc:
        raise _invalid("unreadable PDF") from exc
    _check_totals(sections, limits)
    title = _clean(title_hint) if title_hint else metadata_title
    return ParsedDocument("pypdf", "application/pdf", title or None, tuple(sections))


def _parse_csv(data: bytes, title_hint: str | None, limits: ParserLimits) -> ParsedDocument:
    text = _decode(data, allow_bom=True)
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows)
        if not header or any(not item.strip() for item in header) or len(header) != len(set(header)):
            raise _invalid("CSV headers must be non-blank and unique")
        if any(len(item) > limits.max_cell_chars for item in header):
            raise _limit("CSV cell characters", max_cell_chars=limits.max_cell_chars)
        sections: list[ParsedSection] = []
        for index, row in enumerate(rows, start=1):
            if index > limits.max_rows:
                raise _limit("CSV rows", max_rows=limits.max_rows)
            if len(row) != len(header):
                raise _invalid("CSV row width does not match header", row=index)
            if any(len(item) > limits.max_cell_chars for item in row):
                raise _limit("CSV cell characters", max_cell_chars=limits.max_cell_chars, row=index)
            record = dict(zip(header, row, strict=True))
            rendered = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            sections.append(ParsedSection(None, f"csv:row:{index}", rendered))
    except ResearchProjectV2Error:
        raise
    except (csv.Error, StopIteration) as exc:
        raise _invalid("malformed CSV") from exc
    if not sections:
        raise _invalid("CSV has no data rows")
    _check_totals(sections, limits)
    return ParsedDocument("stdlib.csv", "text/csv", _clean(title_hint) if title_hint else None, tuple(sections))


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("duplicate JSON object key")
        result[key] = value
    return result


def _json_constant(_: str) -> Any:
    raise _invalid("non-finite JSON number")


def _pointer_part(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _check_json_lexical_depth(text: str, limits: ParserLimits) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > limits.max_depth + 1:
                raise _limit("JSON depth", max_depth=limits.max_depth)
        elif character in "]}":
            depth -= 1


def _parse_json(data: bytes, title_hint: str | None, limits: ParserLimits) -> ParsedDocument:
    text = _decode(data)
    _check_json_lexical_depth(text, limits)
    try:
        root = json.loads(text, object_pairs_hook=_json_pairs, parse_constant=_json_constant)
    except ResearchProjectV2Error:
        raise
    except RecursionError as exc:
        raise _limit("JSON depth", max_depth=limits.max_depth) from exc
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise _invalid("malformed JSON") from exc
    sections: list[ParsedSection] = []
    nodes = 0

    def visit(value: Any, pointer: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes:
            raise _limit("JSON nodes", max_nodes=limits.max_nodes)
        if depth > limits.max_depth:
            raise _limit("JSON depth", max_depth=limits.max_depth)
        if isinstance(value, str) and len(value) > limits.max_string_chars:
            raise _limit("JSON string characters", max_string_chars=limits.max_string_chars)
        if isinstance(value, dict):
            for key in sorted(value):
                if len(key) > limits.max_string_chars:
                    raise _limit("JSON string characters", max_string_chars=limits.max_string_chars)
                visit(value[key], f"{pointer}/{_pointer_part(key)}", depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{pointer}/{index}", depth + 1)
        else:
            sections.append(ParsedSection(None, pointer or "/", canonical_bytes(value).decode("utf-8")))

    try:
        visit(root, "", 0)
    except ResearchProjectV2Error:
        raise
    except Exception as exc:
        raise _invalid("JSON scalar cannot be represented canonically") from exc
    if not sections:
        raise _invalid("JSON has no scalar values")
    _check_totals(sections, limits)
    return ParsedDocument("stdlib.json", "application/json", _clean(title_hint) if title_hint else None, tuple(sections))


def _parse_text(data: bytes, title_hint: str | None, limits: ParserLimits) -> ParsedDocument:
    text = _decode(data)
    paragraphs = [_clean(part) for part in re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", text)]
    sections = [
        ParsedSection(None, f"text:paragraph:{index:04d}", paragraph)
        for index, paragraph in enumerate((part for part in paragraphs if part), start=1)
    ]
    if not sections:
        raise _invalid("text document is empty")
    _check_totals(sections, limits)
    return ParsedDocument("stdlib.text", "text/plain", _clean(title_hint) if title_hint else None, tuple(sections))


def parse_document_bytes(
    data: bytes,
    *,
    media_type: str,
    title_hint: str | None = None,
    limits: ParserLimits | None = None,
) -> ParsedDocument:
    if not isinstance(data, bytes):
        raise _invalid("document data must be bytes")
    effective = ParserLimits() if limits is None else limits
    if len(data) > effective.max_bytes:
        raise _limit("document bytes", max_bytes=effective.max_bytes)
    parsers = {
        "text/html": _parse_html,
        "application/pdf": _parse_pdf,
        "text/csv": _parse_csv,
        "application/json": _parse_json,
        "text/plain": _parse_text,
    }
    try:
        parser = parsers[media_type]
    except KeyError as exc:
        raise ResearchProjectV2Error(
            f"Unsupported document media type: {media_type}",
            code="RESEARCH_PROJECT_V2_1_PARSE_UNSUPPORTED_MEDIA",
            details={"media_type": media_type},
        ) from exc
    return parser(data, title_hint, effective)
