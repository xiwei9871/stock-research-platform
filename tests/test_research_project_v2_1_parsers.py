from __future__ import annotations

import errno
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

import stock_research.research_project_v2_1.normalize as normalize_module
from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import (
    normalize_artifact,
    normalize_text,
    validate_normalized_document,
    write_normalized_document,
)
from stock_research.research_project_v2_1.parsers import ParserLimits, parse_document_bytes
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


FIXTURES = Path("artifacts/research_projects/v2_1/fixtures/documents")


def _provenance(record: str = "record-1") -> dict:
    return {
        "created_by": "test",
        "actor_type": "automated_pipeline",
        "agent_run_id": record,
        "created_at": "2026-07-18T00:00:00Z",
        "created_in_version": "2.1.0",
        "review_status": "unreviewed",
    }


def _error_code(exc: pytest.ExceptionInfo[ResearchProjectV2Error]) -> str:
    return exc.value.code


def test_html_parser_keeps_visible_semantic_content_without_parent_duplicates() -> None:
    parsed = parse_document_bytes(
        (FIXTURES / "sample_engineering.html").read_bytes(), media_type="text/html"
    )
    assert parsed.title == "Engineering Capacity"
    assert [section.locator for section in parsed.sections] == [
        "html:h1:0001",
        "html:p:0001",
        "html:li:0001",
        "html:li:0002",
        "html:table:0001:row:0001:cell:0001",
        "html:table:0001:row:0001:cell:0002",
        "html:table:0001:row:0002:cell:0001",
        "html:table:0001:row:0002:cell:0002",
    ]
    combined = "\n".join(section.text for section in parsed.sections)
    assert "Navigation noise" not in combined
    assert "Hidden" not in combined
    assert "not evidence" not in combined


@pytest.mark.parametrize("payload", [b"\xff", b"<html><body></body></html>"])
def test_html_parser_wraps_invalid_or_empty_documents(payload: bytes) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(payload, media_type="text/html")
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_html_hidden_void_element_does_not_hide_following_content() -> None:
    parsed = parse_document_bytes(
        b"<html><body><input hidden><p>Visible after input</p></body></html>",
        media_type="text/html",
    )
    assert [section.text for section in parsed.sections] == ["Visible after input"]


def test_html_hidden_attributes_accept_html_and_css_whitespace() -> None:
    parsed = parse_document_bytes(
        b'<html><body><p style="display:\tnone">css hidden</p><p aria-hidden=" true ">aria hidden</p><p>visible</p></body></html>',
        media_type="text/html",
    )
    assert [section.text for section in parsed.sections] == ["visible"]


def test_html_malformed_void_end_tag_cannot_pop_hidden_ancestor() -> None:
    parsed = parse_document_bytes(
        b"<div hidden><br></br><p>hidden leak</p></div><p>visible</p>",
        media_type="text/html",
    )
    assert [section.text for section in parsed.sections] == ["visible"]


def test_html_nested_tables_restore_outer_context_with_element_evidence_text() -> None:
    parsed = parse_document_bytes(
        b"<table><tr><td>outer before<table><tr><td>inner</td></tr></table>outer after</td></tr><tr><td>outer row two</td></tr></table>",
        media_type="text/html",
    )
    assert [(section.locator, section.text) for section in parsed.sections] == [
        (
            "html:table:0001:row:0001:cell:0001",
            "outer before inner outer after",
        ),
        ("html:table:0002:row:0001:cell:0001", "inner"),
        ("html:table:0001:row:0002:cell:0001", "outer row two"),
    ]


def test_html_mixed_content_uses_dom_start_order_and_word_boundaries() -> None:
    parsed = parse_document_bytes(
        b"<div>before<p>inside</p>after</div>", media_type="text/html"
    )
    assert [(section.locator, section.text) for section in parsed.sections] == [
        ("html:div:0001", "before inside after"),
        ("html:p:0001", "inside"),
    ]


def test_html_inline_elements_do_not_insert_false_word_boundaries() -> None:
    parsed = parse_document_bytes(
        b"<p>inter<span>net</span> 12<code>34</code></p>",
        media_type="text/html",
    )
    assert parsed.sections[0].text == "internet 1234"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"<p>alpha<br>beta</p>", "alpha beta"),
        (b"<div>one<hr>two</div>", "one two"),
    ],
)
def test_html_break_void_tags_insert_budgeted_text_boundaries(
    payload: bytes, expected: str
) -> None:
    parsed = parse_document_bytes(payload, media_type="text/html")
    assert parsed.sections[0].text == expected


@pytest.mark.parametrize(
    "attribute",
    ["hidden", 'aria-hidden="true"', 'style="display:none"', 'style="visibility: hidden"'],
)
def test_html_hidden_break_void_tags_do_not_insert_boundaries_or_spend_budget(
    attribute: str,
) -> None:
    payload = f"<p>alpha<br {attribute}>beta</p>".encode()
    parsed = parse_document_bytes(
        payload,
        media_type="text/html",
        limits=ParserLimits(max_text_chars=len("alphabeta")),
    )
    assert parsed.sections[0].text == "alphabeta"


def test_html_table_cell_aggregates_descendants_and_implicit_row_is_one_based() -> None:
    parsed = parse_document_bytes(
        b"<table><td>before<p>inside</p>after</td><tr><td>next</td></tr></table>",
        media_type="text/html",
    )
    assert [(section.locator, section.text) for section in parsed.sections] == [
        ("html:table:0001:row:0001:cell:0001", "before inside after"),
        ("html:p:0001", "inside"),
        ("html:table:0001:row:0002:cell:0001", "next"),
    ]
    assert all(":row:0000:" not in section.locator for section in parsed.sections)


def test_html_nested_list_parent_and_child_follow_element_evidence_order() -> None:
    parsed = parse_document_bytes(
        b"<ul><li>before<ul><li>inside</li></ul>after</li></ul>",
        media_type="text/html",
    )
    assert [(section.locator, section.text) for section in parsed.sections] == [
        ("html:li:0001", "before inside after"),
        ("html:li:0002", "inside"),
    ]


def test_html_implicitly_closes_table_cells_in_start_order_and_flushes_eof() -> None:
    table = parse_document_bytes(
        b"<table><tr><td>A<td>B</tr></table>", media_type="text/html"
    )
    assert [(section.locator, section.text) for section in table.sections] == [
        ("html:table:0001:row:0001:cell:0001", "A"),
        ("html:table:0001:row:0001:cell:0002", "B"),
    ]
    paragraph = parse_document_bytes(b"<p>visible", media_type="text/html")
    assert [section.text for section in paragraph.sections] == ["visible"]


def test_html_implicitly_closes_paragraphs_and_list_items_in_source_order() -> None:
    paragraphs = parse_document_bytes(b"<p>A<p>B", media_type="text/html")
    assert [section.text for section in paragraphs.sections] == ["A", "B"]
    items = parse_document_bytes(b"<ul><li>A<li>B</ul>", media_type="text/html")
    assert [section.text for section in items.sections] == ["A", "B"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"<p>A<h2>H</h2><p>B", ["A", "H", "B"]),
        (b"<p>A<div>D</div><p>B", ["A", "D", "B"]),
        (b"<h1>A<h2>B", ["A", "B"]),
        (b"<p>A<h1>H<h2>I", ["A", "H", "I"]),
    ],
)
def test_html_block_starts_close_paragraphs_and_headings_in_dom_order(
    payload: bytes, expected: list[str]
) -> None:
    parsed = parse_document_bytes(payload, media_type="text/html")
    assert [section.text for section in parsed.sections] == expected


def test_html_implicit_heading_close_cannot_cross_hidden_ancestor() -> None:
    parsed = parse_document_bytes(
        b"<h1>Visible<div hidden><h2>SECRET</h2></div><p>shown</p>",
        media_type="text/html",
    )
    combined = "\n".join(section.text for section in parsed.sections)
    assert "SECRET" not in combined
    assert "Visible" in combined
    assert "shown" in combined


def test_pdf_parser_emits_one_section_per_page_and_rejects_encryption() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": "Metadata title"})
    plain = bytearray()
    from io import BytesIO

    handle = BytesIO()
    writer.write(handle)
    parsed = parse_document_bytes(
        handle.getvalue(), media_type="application/pdf", title_hint="Hint title"
    )
    assert parsed.title == "Hint title"
    assert [(s.locator, s.page_start, s.page_end) for s in parsed.sections] == [
        ("page:1", 1, 1),
        ("page:2", 2, 2),
    ]

    encrypted = PdfWriter()
    encrypted.add_blank_page(width=72, height=72)
    encrypted.encrypt("")
    encrypted_handle = BytesIO()
    encrypted.write(encrypted_handle)
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(encrypted_handle.getvalue(), media_type="application/pdf")
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_pdf_parser_wraps_corruption_and_limits_pages() -> None:
    with pytest.raises(ResearchProjectV2Error) as corrupt:
        parse_document_bytes(b"not a pdf", media_type="application/pdf")
    assert _error_code(corrupt) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    from io import BytesIO

    handle = BytesIO()
    writer.write(handle)
    with pytest.raises(ResearchProjectV2Error) as limited:
        parse_document_bytes(
            handle.getvalue(),
            media_type="application/pdf",
            limits=ParserLimits(max_sections=0),
        )
    assert _error_code(limited) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_pdf_text_limit_stops_real_text_extraction() -> None:
    from pypdf import PdfReader
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 10 100 Td (capacity expansion) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(contents)
    handle = BytesIO()
    writer.write(handle)
    assert "capacity expansion" in (
        PdfReader(BytesIO(handle.getvalue())).pages[0].extract_text() or ""
    )
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(
            handle.getvalue(),
            media_type="application/pdf",
            limits=ParserLimits(max_text_chars=5),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def _pdf_bytes(*, title: str | None = None, text: str | None = None) -> bytes:
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if title is not None:
        writer.add_metadata({"/Title": title})
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        contents = DecodedStreamObject()
        contents.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(contents)
    handle = BytesIO()
    writer.write(handle)
    return handle.getvalue()


def test_pdf_metadata_title_and_hint_share_only_effective_title_budget() -> None:
    with pytest.raises(ResearchProjectV2Error) as metadata_limit:
        parse_document_bytes(
            _pdf_bytes(title="metadata title too long"),
            media_type="application/pdf",
            limits=ParserLimits(max_text_chars=5),
        )
    assert metadata_limit.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"

    with pytest.raises(ResearchProjectV2Error) as hint_limit:
        parse_document_bytes(
            _pdf_bytes(title="short"),
            media_type="application/pdf",
            title_hint="hint title too long",
            limits=ParserLimits(max_text_chars=5),
        )
    assert hint_limit.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"

    parsed = parse_document_bytes(
        _pdf_bytes(title="metadata title too long"),
        media_type="application/pdf",
        title_hint="hint",
        limits=ParserLimits(max_text_chars=4),
    )
    assert parsed.title == "hint"


def test_pdf_short_title_plus_body_uses_combined_text_budget() -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(
            _pdf_bytes(title="title", text="body"),
            media_type="application/pdf",
            limits=ParserLimits(max_text_chars=8),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def test_csv_parser_preserves_headers_and_strings_deterministically() -> None:
    parsed = parse_document_bytes(
        (FIXTURES / "sample_capacity.csv").read_bytes(), media_type="text/csv"
    )
    assert [section.locator for section in parsed.sections] == ["csv:row:1", "csv:row:2"]
    assert json.loads(parsed.sections[0].text) == {
        "facility": "Shanghai",
        "product": "Module A",
        "annual_capacity": "120000",
    }


@pytest.mark.parametrize(
    "payload",
    [b"a,a\n1,2\n", b"a,\n1,2\n", b"a,b\n1\n", b'a,b\n"unterminated,2\n'],
)
def test_csv_parser_rejects_bad_headers_and_rows(payload: bytes) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(payload, media_type="text/csv")
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_csv_parser_enforces_cell_and_row_limits() -> None:
    with pytest.raises(ResearchProjectV2Error) as cell:
        parse_document_bytes(
            b"a,b\n123,4\n", media_type="text/csv", limits=ParserLimits(max_cell_chars=2)
        )
    assert _error_code(cell) == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    with pytest.raises(ResearchProjectV2Error) as rows:
        parse_document_bytes(
            b"a\n1\n2\n", media_type="text/csv", limits=ParserLimits(max_rows=1)
        )
    assert _error_code(rows) == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def test_json_parser_sorts_keys_and_uses_json_pointer_leaf_locators() -> None:
    parsed = parse_document_bytes(
        (FIXTURES / "sample_standard.json").read_bytes(), media_type="application/json"
    )
    assert [section.locator for section in parsed.sections] == [
        "/items/0/name",
        "/items/0/status",
        "/items/1/name",
        "/items/1/status",
        "/standard",
        "/version",
    ]
    escaped = parse_document_bytes(b'{"a/b":{"~key":1}}', media_type="application/json")
    assert escaped.sections[0].locator == "/a~1b/~0key"


def test_json_root_scalar_and_empty_key_have_distinct_rfc6901_pointers() -> None:
    root = parse_document_bytes(b"7", media_type="application/json")
    empty_key = parse_document_bytes(b'{"":7}', media_type="application/json")
    assert root.sections[0].locator == ""
    assert empty_key.sections[0].locator == "/"


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":1,"a":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":"\\ud800"}',
        b'{"\\ud800":1}',
        b'{"x":9007199254740992}',
        b"\xff",
    ],
)
def test_json_parser_rejects_duplicates_nonfinite_and_bad_utf8(payload: bytes) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(payload, media_type="application/json")
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_json_parser_enforces_depth_nodes_and_strings() -> None:
    cases = [
        (b'{"a":{"b":1}}', ParserLimits(max_depth=1)),
        (b'{"a":1,"b":2}', ParserLimits(max_nodes=2)),
        (b'{"a":"long"}', ParserLimits(max_string_chars=3)),
    ]
    for payload, limits in cases:
        with pytest.raises(ResearchProjectV2Error) as exc:
            parse_document_bytes(payload, media_type="application/json", limits=limits)
        assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def test_json_parser_wraps_decoder_recursion_as_depth_limit() -> None:
    payload = ("[" * 2_000 + "0" + "]" * 2_000).encode()
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(payload, media_type="application/json", limits=ParserLimits(max_depth=20))
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    quoted = parse_document_bytes(b'{"brackets":"[[[{{{"}', media_type="application/json", limits=ParserLimits(max_depth=1))
    assert quoted.sections[0].text == '"[[[{{{"'


def test_plain_text_and_unsupported_media_have_stable_behavior() -> None:
    parsed = parse_document_bytes(b"first\nline\n\nsecond", media_type="text/plain")
    assert [section.text for section in parsed.sections] == ["first line", "second"]
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(b"x", media_type="image/png")
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_UNSUPPORTED_MEDIA"


def _artifact(layout: LayeredResearchLayout, data: bytes, media_type: str, suffix: str) -> dict:
    digest = sha256(data).hexdigest()
    relative = f"evidence/raw/{digest[:2]}/{digest}.{suffix}"
    target = layout.root / relative
    target.parent.mkdir(parents=True, mode=0o700)
    target.write_bytes(data)
    return {
        "artifact_id": "evidence_artifact:test",
        "candidate_id": "source_candidate:test",
        "evidence_channel": "industry",
        "original_url": "https://example.com/a",
        "final_url": "https://example.com/a",
        "redirect_chain": [],
        "status_code": 200,
        "response_headers": {},
        "media_type": media_type,
        "byte_count": len(data),
        "content_sha256": digest,
        "fetched_at": "2026-07-18T00:00:00Z",
        "raw_path": relative,
        "provenance": _provenance(),
    }


def test_normalize_artifact_is_deterministic_schema_valid_and_does_not_mutate(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, "A\u030A  capacity\n\n  10".encode(), "text/plain", "txt")
    original = deepcopy(artifact)
    provenance = _provenance("run-1")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T01:02:03Z",
        provenance=provenance,
        warnings=["z", "a", "z"],
    )
    assert artifact == original
    assert normalize_text("A\u030A   capacity") == "Å capacity"
    assert document["warnings"] == ["a", "z"]
    assert document["sections"][0]["section_id"] == "section:evidence_artifact:test:0001"
    core = {
        key: value
        for key, value in document.items()
        if key not in {"document_id", "document_hash"}
    }
    assert document["document_hash"] == content_sha256(core)
    assert document["document_id"].startswith("normalized_document:")
    validate_v2_1_schema_payload(
        "normalized_document_v2_1",
        {"schema_version": "2.1.0", "artifact_kind": "normalized_document", "normalized_document": document},
    )
    assert validate_normalized_document(document) == document
    drifted = deepcopy(document)
    drifted["document_hash"] = "0" * 64
    with pytest.raises(ResearchProjectV2Error):
        validate_normalized_document(drifted)


def test_normalize_rejects_raw_path_hash_size_extension_and_symlink_without_output(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"valid", "text/plain", "txt")
    bad_cases = []
    wrong_hash = deepcopy(artifact)
    wrong_hash["content_sha256"] = "0" * 64
    bad_cases.append(wrong_hash)
    wrong_size = deepcopy(artifact)
    wrong_size["byte_count"] += 1
    bad_cases.append(wrong_size)
    wrong_ext = deepcopy(artifact)
    wrong_ext["raw_path"] = wrong_ext["raw_path"][:-3] + "csv"
    bad_cases.append(wrong_ext)
    for bad in bad_cases:
        with pytest.raises(ResearchProjectV2Error):
            normalize_artifact(bad, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("x"))
    raw = layout.root / artifact["raw_path"]
    original = raw.with_suffix(".original")
    raw.rename(original)
    raw.symlink_to(original)
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("x"))
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"
    assert not layout.evidence_normalized_dir.exists()


def test_write_normalized_document_is_immutable_idempotent_and_concurrent(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"one paragraph", "text/plain", "txt")
    document = normalize_artifact(artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("x"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda _: write_normalized_document(document, layout=layout), range(8)))
    assert len(set(paths)) == 1
    wrapper = json.loads(paths[0].read_text(encoding="utf-8"))
    assert paths[0].read_bytes() == canonical_bytes(wrapper)
    changed = deepcopy(document)
    changed["title"] = "tampered"
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(changed, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_IMMUTABILITY_VIOLATION"
    assert not list(layout.evidence_normalized_dir.glob(".tmp-*"))
    retired = layout.evidence_normalized_dir / ".retired"
    assert retired.is_dir()
    assert stat.S_IMODE(retired.stat().st_mode) & 0o077 == 0
    assert not list(retired.iterdir())


@pytest.mark.parametrize("mode", [0o755, 0o777])
def test_write_rejects_group_or_other_accessible_normalized_directory(
    tmp_path: Path, mode: int
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"permissions", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("permissions"),
    )
    layout.evidence_normalized_dir.mkdir(parents=True, mode=0o700)
    layout.evidence_normalized_dir.chmod(mode)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"


def test_write_classifies_enospc_directory_creation_as_storage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"no space", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("no-space"),
    )
    monkeypatch.setattr(
        normalize_module.os,
        "mkdir",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOSPC, "injected no space")
        ),
    )

    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)

    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_STORAGE_FAILED"


def test_write_classifies_post_publish_unlink_as_path_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"unlink", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("unlink"),
    )
    original_open = normalize_module._open_absolute_directory
    calls = 0

    def unlink_before_live_read(directory):
        nonlocal calls
        calls += 1
        descriptors, names = original_open(directory)
        if calls == 2:
            os.unlink(f"{document['document_id']}.json", dir_fd=descriptors[-1])
        return descriptors, names

    monkeypatch.setattr(
        normalize_module, "_open_absolute_directory", unlink_before_live_read
    )
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"


@pytest.mark.parametrize("window", ["first_verification", "held_open"])
def test_write_classifies_earlier_post_link_unlink_windows_as_path_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"early unlink", "text/plain", "txt")
    document = normalize_artifact(
        artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("early-unlink"),
    )
    final_name = f"{document['document_id']}.json"
    if window == "first_verification":
        original_link = normalize_module.os.link

        def link_then_unlink(source, target, **kwargs):
            original_link(source, target, **kwargs)
            normalize_module.os.unlink(target, dir_fd=kwargs["dst_dir_fd"])

        monkeypatch.setattr(normalize_module.os, "link", link_then_unlink)
    else:
        original_cleanup = normalize_module._unlink_if_inode

        def cleanup_then_unlink(directory_fd, retired_fd, name, expected):
            result = original_cleanup(directory_fd, retired_fd, name, expected)
            normalize_module.os.unlink(final_name, dir_fd=directory_fd)
            return result

        monkeypatch.setattr(normalize_module, "_unlink_if_inode", cleanup_then_unlink)

    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"


def test_write_rejects_symlinked_retired_directory_before_publication(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"retired symlink", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("retired-symlink"),
    )
    layout.evidence_normalized_dir.mkdir(parents=True, mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    (layout.evidence_normalized_dir / ".retired").symlink_to(outside)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"
    assert not (layout.evidence_normalized_dir / f"{document['document_id']}.json").exists()


def _rehash_document(document: dict) -> None:
    payload = {
        key: deepcopy(document[key])
        for key in (
            "artifact_id",
            "parser",
            "parser_version",
            "media_type",
            "title",
            "sections",
            "warnings",
            "parsed_at",
            "provenance",
        )
    }
    document["document_hash"] = content_sha256(payload)
    identity = sha256(
        f"{document['artifact_id']}\n{document['document_hash']}".encode()
    ).hexdigest()[:24]
    document["document_id"] = f"normalized_document:{identity}"


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda section: section.__setitem__("section_hash", "0" * 64), "section_hash"),
        (lambda section: section.__setitem__("section_id", "section:wrong:0001"), "section_id"),
        (lambda section: section.__setitem__("text", "  noncanonical  text "), "text"),
        (lambda section: section.__setitem__("heading", "  noncanonical  heading "), "heading"),
    ],
)
def test_writer_rejects_invalid_derived_section_fields_even_with_rehashed_document(
    tmp_path: Path, mutation: object, field: str
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"section validation", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("sections"),
    )
    mutation(document["sections"][0])
    _rehash_document(document)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_INVALID"
    assert exc.value.details["section_index"] == 1
    assert exc.value.details["field"] == field


def test_writer_rejects_duplicate_section_locator_after_all_hashes_are_recomputed(
    tmp_path: Path,
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"first\n\nsecond", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("duplicate-locator"),
    )
    second = document["sections"][1]
    second["locator"] = document["sections"][0]["locator"]
    second["section_hash"] = content_sha256(
        {"heading": second["heading"], "locator": second["locator"], "text": second["text"]}
    )
    _rehash_document(document)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_INVALID"
    assert exc.value.details["field"] == "locator"


@pytest.mark.parametrize(
    ("page_start", "page_end", "field"),
    [(True, True, "page_start"), (1, None, "page_start"), (2, 1, "page_end")],
)
def test_writer_rejects_invalid_section_page_ranges(
    tmp_path: Path, page_start: object, page_end: object, field: str
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"page range", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("page-range"),
    )
    section = document["sections"][0]
    section["page_start"] = page_start
    section["page_end"] = page_end
    _rehash_document(document)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_normalized_document(document, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_INVALID"
    assert exc.value.details["field"] == field


def test_parse_byte_limit_is_checked_before_decoding() -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(b"123", media_type="text/plain", limits=ParserLimits(max_bytes=2))
    assert _error_code(exc) == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "limits",
    [
        ParserLimits(max_bytes=0),
        ParserLimits(max_sections=-1),
        ParserLimits(max_text_chars=True),
        ParserLimits(max_depth="10"),
    ],
)
def test_parser_limits_reject_nonpositive_bool_and_noninteger_values(limits: ParserLimits) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(b"text", media_type="text/plain", limits=limits)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_INVALID"


def test_html_limits_stop_before_later_text_and_section_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    from stock_research.research_project_v2_1 import parsers as parsers_module

    original_handle_data = parsers_module._VisibleHTMLParser.handle_data

    def record(self: object, data: str) -> None:
        seen.append(data)
        original_handle_data(self, data)

    monkeypatch.setattr(parsers_module._VisibleHTMLParser, "handle_data", record)
    with pytest.raises(ResearchProjectV2Error) as text_limit:
        parse_document_bytes(
            b"<p>12345</p><p>SENTINEL</p>",
            media_type="text/html",
            limits=ParserLimits(max_text_chars=3),
        )
    assert text_limit.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    assert "SENTINEL" not in seen
    with pytest.raises(ResearchProjectV2Error) as section_limit:
        parse_document_bytes(
            b"<p>one</p><p>two</p>",
            media_type="text/html",
            limits=ParserLimits(max_sections=1),
        )
    assert section_limit.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def test_html_aggregation_writes_are_incrementally_budgeted_before_later_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stock_research.research_project_v2_1 import parsers as parsers_module

    seen: list[str] = []
    original_handle_data = parsers_module._VisibleHTMLParser.handle_data

    def record(self: object, data: str) -> None:
        seen.append(data)
        original_handle_data(self, data)

    monkeypatch.setattr(parsers_module._VisibleHTMLParser, "handle_data", record)
    payload = b"<div><div><div><div>x</div></div></div></div><p>SENTINEL</p>"
    with pytest.raises(ResearchProjectV2Error) as exc:
        parse_document_bytes(
            payload,
            media_type="text/html",
            limits=ParserLimits(max_text_chars=5),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    assert "SENTINEL" not in seen


def test_normalize_preserves_parse_limit_error_and_publishes_nothing(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"a\n123\n", "text/csv", "csv")
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(
            artifact,
            layout=layout,
            parsed_at="2026-07-18T00:00:00Z",
            provenance=_provenance("limit"),
            limits=ParserLimits(max_bytes=2, max_cell_chars=2),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    assert not layout.evidence_normalized_dir.exists()


def test_normalize_rejects_oversized_raw_before_reading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"large", "text/plain", "txt")

    def forbidden_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("oversized raw must not be read")

    monkeypatch.setattr(normalize_module.os, "read", forbidden_read)
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(
            artifact,
            layout=layout,
            parsed_at="2026-07-18T00:00:00Z",
            provenance=_provenance("oversized"),
            limits=ParserLimits(max_bytes=2),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"


def test_normalize_rejects_raw_intermediate_directory_rebind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"bound raw", "text/plain", "txt")
    raw_dir = layout.evidence_raw_dir
    moved = layout.root / "evidence/raw-old"
    original_read = normalize_module._read_fd

    def rebind_after_read(
        descriptor: int, *, max_bytes: int | None = None, digest: object | None = None
    ) -> bytes:
        data = original_read(descriptor, max_bytes=max_bytes, digest=digest)
        raw_dir.rename(moved)
        raw_dir.mkdir(mode=0o700)
        return data

    monkeypatch.setattr(normalize_module, "_read_fd", rebind_after_read)
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(
            artifact,
            layout=layout,
            parsed_at="2026-07-18T00:00:00Z",
            provenance=_provenance("rebind"),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"


def test_normalize_caps_raw_that_grows_during_streaming(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    data = b"x" * 70_000
    artifact = _artifact(layout, data, "text/plain", "txt")
    raw = layout.root / artifact["raw_path"]
    original_read = normalize_module.os.read
    grew = False

    def growing_read(descriptor: int, amount: int) -> bytes:
        nonlocal grew
        chunk = original_read(descriptor, amount)
        if chunk and not grew:
            grew = True
            with raw.open("ab") as handle:
                handle.write(b"growth")
        return chunk

    monkeypatch.setattr(normalize_module.os, "read", growing_read)
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(
            artifact,
            layout=layout,
            parsed_at="2026-07-18T00:00:00Z",
            provenance=_provenance("growth"),
            limits=ParserLimits(max_bytes=len(data)),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED"
    assert not layout.evidence_normalized_dir.exists()


def test_normalize_rejects_raw_final_replacement_during_live_reread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"live raw", "text/plain", "txt")
    raw = layout.root / artifact["raw_path"]
    original_read = normalize_module._read_fd
    calls = 0

    def replace_during_live_read(
        descriptor: int, *, max_bytes: int | None = None, digest: object | None = None
    ) -> bytes:
        nonlocal calls
        calls += 1
        data = original_read(descriptor, max_bytes=max_bytes, digest=digest)
        if calls == 2:
            old = raw.with_suffix(".old")
            raw.rename(old)
            raw.write_bytes(b"replacement")
        return data

    monkeypatch.setattr(normalize_module, "_read_fd", replace_during_live_read)
    with pytest.raises(ResearchProjectV2Error) as exc:
        normalize_artifact(
            artifact,
            layout=layout,
            parsed_at="2026-07-18T00:00:00Z",
            provenance=_provenance("live-final"),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION"
    assert not layout.evidence_normalized_dir.exists()


def test_normalize_preserves_exact_json_pointer_locators(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b'{"a b":1,"a\\tb":2}', "application/json", "json")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("pointers"),
    )
    assert [section["locator"] for section in document["sections"]] == ["/a\tb", "/a b"]


def test_normalize_accepts_exact_empty_root_locator_and_hashes_it(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"7", "application/json", "json")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("root-scalar"),
    )
    section = document["sections"][0]
    assert section["locator"] == ""
    assert section["section_hash"] == content_sha256(
        {"heading": None, "locator": "", "text": "7"}
    )


def test_write_rejects_replaced_temp_without_publishing_or_deleting_attacker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"one paragraph", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("temp-race"),
    )
    original_write = normalize_module._write_all
    attacker_path: Path | None = None

    def replace_temp(descriptor: int, data: bytes) -> None:
        nonlocal attacker_path
        original_write(descriptor, data)
        temp_names = list(layout.evidence_normalized_dir.glob(".tmp-*"))
        assert len(temp_names) == 1
        attacker_path = temp_names[0]
        attacker_path.unlink()
        attacker_path.write_bytes(b"attacker")

    monkeypatch.setattr(normalize_module, "_write_all", replace_temp)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    assert not (layout.evidence_normalized_dir / f"{document['document_id']}.json").exists()
    assert attacker_path is not None and attacker_path.read_bytes() == b"attacker"


def test_write_detects_temp_replacement_at_link_boundary_without_name_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"link race", "text/plain", "txt")
    document = normalize_artifact(
        artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("link-race")
    )
    original_link = normalize_module.os.link
    attacker_temp: Path | None = None

    def replace_inside_link(src: str, dst: str, **kwargs: object) -> None:
        nonlocal attacker_temp
        attacker_temp = layout.evidence_normalized_dir / src
        attacker_temp.unlink()
        attacker_temp.write_bytes(b"link-boundary-attacker")
        original_link(src, dst, **kwargs)

    monkeypatch.setattr(normalize_module.os, "link", replace_inside_link)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    final = layout.evidence_normalized_dir / f"{document['document_id']}.json"
    assert final.read_bytes() == b"link-boundary-attacker"
    assert attacker_temp is not None and attacker_temp.read_bytes() == b"link-boundary-attacker"


def test_temp_cleanup_isolates_name_replacement_before_deletion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"cleanup race", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("cleanup-race"),
    )
    original_rename = normalize_module.os.rename
    attacked = False

    def replace_during_isolation(src: str, dst: str, **kwargs: object) -> None:
        nonlocal attacked
        if isinstance(src, str) and src.startswith(".tmp-") and not attacked:
            attacked = True
            directory_fd = kwargs["src_dir_fd"]
            os.unlink(src, dir_fd=directory_fd)
            attacker_fd = os.open(
                src,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            os.write(attacker_fd, b"cleanup-attacker")
            os.close(attacker_fd)
        original_rename(src, dst, **kwargs)

    monkeypatch.setattr(normalize_module.os, "rename", replace_during_isolation)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    retired = list((layout.evidence_normalized_dir / ".retired").iterdir())
    assert len(retired) == 1
    assert retired[0].read_bytes() == b"cleanup-attacker"


def test_write_detects_final_replacement_without_deleting_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"final race", "text/plain", "txt")
    document = normalize_artifact(
        artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("final-race")
    )
    original_link = normalize_module.os.link

    def replace_final(*args: object, **kwargs: object) -> None:
        original_link(*args, **kwargs)
        final = layout.evidence_normalized_dir / f"{document['document_id']}.json"
        final.unlink()
        final.write_bytes(b"replacement")

    monkeypatch.setattr(normalize_module.os, "link", replace_final)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    final = layout.evidence_normalized_dir / f"{document['document_id']}.json"
    assert final.read_bytes() == b"replacement"


def test_write_detects_replacement_during_last_live_final_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"last read race", "text/plain", "txt")
    document = normalize_artifact(
        artifact,
        layout=layout,
        parsed_at="2026-07-18T00:00:00Z",
        provenance=_provenance("last-read-race"),
    )
    final = layout.evidence_normalized_dir / f"{document['document_id']}.json"
    original_read = normalize_module._read_fd
    calls = 0

    def replace_after_last_read(
        descriptor: int, *, max_bytes: int | None = None, digest: object | None = None
    ) -> bytes:
        nonlocal calls
        calls += 1
        data = original_read(descriptor, max_bytes=max_bytes, digest=digest)
        if calls == 3:
            old = final.with_suffix(".old")
            final.rename(old)
            final.write_bytes(b"last-read-replacement")
        return data

    monkeypatch.setattr(normalize_module, "_read_fd", replace_after_last_read)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    assert final.read_bytes() == b"last-read-replacement"


def test_write_detects_normalized_directory_rebind_without_deleting_published_inode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"directory race", "text/plain", "txt")
    document = normalize_artifact(
        artifact, layout=layout, parsed_at="2026-07-18T00:00:00Z", provenance=_provenance("dir-race")
    )
    moved = layout.root / "evidence/normalized-old"
    original_link = normalize_module.os.link

    def rebind_directory(*args: object, **kwargs: object) -> None:
        original_link(*args, **kwargs)
        layout.evidence_normalized_dir.rename(moved)
        layout.evidence_normalized_dir.mkdir(mode=0o700)

    monkeypatch.setattr(normalize_module.os, "link", rebind_directory)
    with pytest.raises(ResearchProjectV2Error):
        write_normalized_document(document, layout=layout)
    assert not (layout.evidence_normalized_dir / f"{document['document_id']}.json").exists()
    assert (moved / f"{document['document_id']}.json").is_file()


def test_document_identity_includes_parsed_at_and_full_provenance(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact(layout, b"identity", "text/plain", "txt")
    common = {
        "artifact": artifact,
        "layout": layout,
        "parsed_at": "2026-07-18T00:00:00Z",
        "provenance": _provenance("identity-a"),
        "warnings": ["warning"],
    }
    first = normalize_artifact(**common)
    same = normalize_artifact(**deepcopy(common))
    later = normalize_artifact(**{**common, "parsed_at": "2026-07-18T00:00:01Z"})
    other_provenance = normalize_artifact(
        **{**common, "provenance": _provenance("identity-b")}
    )
    assert (first["document_hash"], first["document_id"]) == (
        same["document_hash"],
        same["document_id"],
    )
    assert len(
        {
            first["document_id"],
            later["document_id"],
            other_provenance["document_id"],
        }
    ) == 3
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(
            pool.map(
                lambda document: write_normalized_document(document, layout=layout),
                (later, other_provenance),
            )
        )
    assert len(set(paths)) == 2
