from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver
import pytest

import stock_research.research_project_v2_1.discovery as discovery_module
from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import (
    DirectUrlDiscoveryProvider,
    DiscoveryProvider,
    DiscoveryResult,
    ImportedJsonDiscoveryProvider,
    discover_sources,
    normalize_url,
    source_candidate_id,
    write_discovery_batch,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


FIXTURE_PATH = Path(
    "artifacts/research_projects/v2_1/fixtures/discovery/imported_results.json"
)
DISCOVERED_AT = "2026-07-18T10:30:00+08:00"
PROVENANCE = {
    "created_by": "fixture-importer",
    "actor_type": "imported",
    "agent_run_id": None,
    "created_at": "2026-07-18T02:30:00Z",
    "created_in_version": "research_version:pcb:0.1.0",
    "review_status": "unreviewed",
}


def search_plan() -> dict[str, Any]:
    return {
        "search_plan_id": "search_plan:pcb-industry",
        "project_id": "research_project:pcb",
        "version_id": "research_version:pcb:0.1.0",
        "evidence_channel": "industry",
        "requirement_ids": ["requirement:industry:pcb"],
        "queries": [
            {
                "query_id": "query:mechanism",
                "query_role": "mechanism",
                "query_text": "mechanism",
                "required_terms": ["PCB"],
                "excluded_terms": [],
                "source_classes": [
                    "technical_standard",
                    "primary_standard",
                    "stock_opinion",
                    "equity_research",
                    "independent_secondary",
                    "direct_url",
                ],
                "priority": 1,
            },
            {
                "query_id": "query:quantification",
                "query_role": "quantification",
                "priority": 2,
                "query_text": "quantification",
                "required_terms": ["PCB"],
                "excluded_terms": [],
                "source_classes": ["technical_standard"],
            },
            {
                "query_id": "query:counter",
                "query_role": "counter_evidence",
                "query_text": "counter",
                "required_terms": ["PCB"],
                "excluded_terms": [],
                "source_classes": ["company_engineering_document"],
                "priority": 3,
            },
        ],
        "languages": ["en"],
        "geography": ["global"],
        "publication_window": "within_12_months",
        "result_limit_per_query": 20,
        "deduplication_policy": "normalized_url_then_content_hash",
        "stop_conditions": ["all planned queries executed"],
        "status": "planned",
        "provenance": deepcopy(PROVENANCE),
    }


def result(**overrides: object) -> DiscoveryResult:
    values: dict[str, object] = {
        "url": "https://example.com/document",
        "title": "Engineering document",
        "snippet": "Engineering constraints and measurements.",
        "publisher": "Example Publisher",
        "publish_date": "2026-01-02",
        "source_class": "technical_standard",
        "query_id": "query:mechanism",
        "rank": 1,
    }
    values.update(overrides)
    return DiscoveryResult(**values)  # type: ignore[arg-type]


class StaticProvider:
    def __init__(self, results_by_query: dict[str, list[DiscoveryResult]]) -> None:
        self.results_by_query = results_by_query

    def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
        return list(self.results_by_query.get(query["query_id"], []))


def assert_discovery_error(call, *, reason: str | None = None) -> ResearchProjectV2Error:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        call()
    assert exc_info.value.code.startswith("RESEARCH_PROJECT_V2_1_DISCOVERY")
    if reason is not None:
        assert exc_info.value.details["reason"] == reason
    return exc_info.value


def assert_url_error(raw: str) -> ResearchProjectV2Error:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        normalize_url(raw)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_DISCOVERY_URL_INVALID"
    assert exc_info.value.details["url"] == raw
    assert isinstance(exc_info.value.details["reason"], str)
    assert exc_info.value.details["reason"]
    return exc_info.value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://ExAmPle.COM:443?B=2&a=&utm_Source=x&SPM=y&from=z&REF=r&source=s#frag",
            "https://example.com/?B=2&a=",
        ),
        ("http://EXAMPLE.com:80/a", "http://example.com/a"),
        ("https://EXAMPLE.com:8443/a", "https://example.com:8443/a"),
        ("https://例子.测试/路径", "https://xn--fsqu00a.xn--0zwm56d/路径"),
        ("https://faß.de/a", "https://xn--fa-hia.de/a"),
        ("https://fass.de/a", "https://fass.de/a"),
        ("https://Example.COM./a", "https://example.com/a"),
        ("https://192.0.2.1/a", "https://192.0.2.1/a"),
        ("https://[2001:db8::1]:443/a", "https://[2001:db8::1]/a"),
        (
            "https://[2001:0db8:0000:0000:0000:0000:0000:0001]/a",
            "https://[2001:db8::1]/a",
        ),
        ("https://example.com/p?z=2&z=1&a=", "https://example.com/p?a=&z=1&z=2"),
        (
            "https://example.com/%e4%b8%ad?q=%e4%b8%ad",
            "https://example.com/%E4%B8%AD?q=%E4%B8%AD",
        ),
    ],
)
def test_normalize_url_canonicalizes_supported_web_urls(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://example.com/a",
        "https:///missing-host",
        "https://user:password@example.com/a",
        "https://example.com:invalid/a",
        "https://example.com:/a",
        "https://\ud800.example/a",
        "https://exa mple.com/a",
        "https://example.com\\evil/a",
        "https://example.com/a\\evil",
        "https://example.com/a b",
        "https://example.com/a?q=bad\tvalue",
        "https://exam\nple.com/a",
        "https://-bad.example/a",
        "https://bad-.example/a",
        "https://bad_name.example/a",
        "https://999.1.1.1/a",
        "https://192.168.001.1/a",
        "https://[fe80::1%eth0]/a",
        "https://[fe80::1%25eth0]/a",
        "https://example.com/%ZZ",
        "https://example.com/%FF",
        "https://example.com/a?q=%FF",
        f"https://{'a' * 64}.example/a",
        f"https://{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 63}/a",
        "not a url",
    ],
)
def test_normalize_url_rejects_unsupported_or_malformed_urls(raw: str) -> None:
    assert_url_error(raw)


def test_candidate_id_is_deterministic_and_uses_trimmed_title() -> None:
    normalized = "https://example.com/a"
    first = source_candidate_id(normalized, "  A title  ")
    second = source_candidate_id(normalized, "A title")

    assert first == second
    assert first == "source_candidate:" + __import__("hashlib").sha256(
        b"https://example.com/a\nA title"
    ).hexdigest()[:24]


def test_discovery_result_is_frozen_and_provider_contract_is_runtime_usable() -> None:
    item = result()
    with pytest.raises(FrozenInstanceError):
        item.rank = 2  # type: ignore[misc]

    provider: DiscoveryProvider = StaticProvider({"query:mechanism": [item]})
    assert provider.search(search_plan()["queries"][0]) == [item]


def test_imported_provider_reads_fixture_and_returns_only_requested_query() -> None:
    provider = ImportedJsonDiscoveryProvider(FIXTURE_PATH)

    mechanism = provider.search({"query_id": "query:mechanism"})
    quantification = provider.search({"query_id": "query:quantification"})

    assert len(mechanism) == 3
    assert {item.query_id for item in mechanism} == {"query:mechanism"}
    assert len(quantification) == 1
    assert quantification[0].title.startswith("A differently titled")
    assert provider.search({"query_id": "query:missing"}) == []


def test_imported_provider_wraps_non_utf8_input_as_stable_discovery_error(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid-utf8.json"
    invalid.write_bytes(b'{"results": ["\xff"]}')

    exc = assert_discovery_error(
        lambda: ImportedJsonDiscoveryProvider(invalid),
        reason="invalid imported discovery JSON",
    )

    assert exc.details["path"] == str(invalid)
    assert isinstance(exc.__cause__, UnicodeError)


def test_direct_url_provider_is_offline_and_converts_query_specs_to_results() -> None:
    query = search_plan()["queries"][0]
    provider = DirectUrlDiscoveryProvider(
        {
            "query:mechanism": [
            "https://standards.example.org/direct.pdf",
            {
                "url": "https://engineering.example.org/doc",
                "title": "Engineering memo",
                "snippet": "Primary engineering detail",
                "publisher": "Engineering Org",
                "publish_date": None,
                "source_class": "company_engineering_document",
            },
            ]
        }
    )

    results = provider.search(query)

    assert [item.rank for item in results] == [1, 2]
    assert results[0] == result(
        url="https://standards.example.org/direct.pdf",
        title="https://standards.example.org/direct.pdf",
        snippet="",
        publisher=None,
        publish_date=None,
        source_class="direct_url",
        rank=1,
    )
    assert results[1].query_id == "query:mechanism"
    assert results[1].title == "Engineering memo"
    assert "direct_urls" not in query


def test_discover_rejects_schema_invalid_search_plan_with_stable_path() -> None:
    plan = search_plan()
    plan.pop("result_limit_per_query")

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        discover_sources(
            plan,
            StaticProvider({}),
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_DISCOVERY_PLAN_INVALID"
    assert exc_info.value.details["path"] == ["search_plan", "result_limit_per_query"]


def test_discover_applies_result_limit_after_rank_and_stable_tie_sorting() -> None:
    plan = search_plan()
    plan["result_limit_per_query"] = 2
    provider = StaticProvider(
        {
            "query:mechanism": [
                result(url="https://example.com/rank-3", title="rank 3", rank=3),
                result(url="https://example.com/rank-2-z", title="Z", rank=2),
                result(url="https://example.com/rank-1", title="rank 1", rank=1),
                result(url="https://example.com/rank-2-a", title="A", rank=2),
            ]
        }
    )

    batch = discover_sources(
        plan,
        provider,
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert [item["rank"] for item in batch["candidates"]] == [1, 2]
    assert [item["title"] for item in batch["candidates"]] == ["rank 1", "A"]


def test_discover_rejects_result_source_class_outside_query_contract() -> None:
    provider = StaticProvider(
        {
            "query:quantification": [
                result(
                    query_id="query:quantification",
                    source_class="company_engineering_document",
                )
            ]
        }
    )

    assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            provider,
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="source_class not allowed for query",
    )


def test_provider_failures_are_wrapped_but_discovery_and_fatal_errors_propagate() -> None:
    class FailingProvider:
        def __init__(self, failure: BaseException) -> None:
            self.failure = failure

        def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
            raise self.failure

    for failure in [
        OSError("offline"),
        UnicodeError("decode"),
        ValueError("invalid"),
        TypeError("bad"),
        json.JSONDecodeError("json", "{", 0),
    ]:
        with pytest.raises(ResearchProjectV2Error) as exc_info:
            discover_sources(
                search_plan(),
                FailingProvider(failure),
                provider_name="failing",
                discovered_at=DISCOVERED_AT,
                provenance=PROVENANCE,
            )
        assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_DISCOVERY_PROVIDER_FAILED"
        assert exc_info.value.details == {
            "provider": "failing",
            "query_id": "query:mechanism",
            "exception_type": type(failure).__name__,
        }
        assert exc_info.value.__cause__ is failure

    discovery_failure = ResearchProjectV2Error("stop", code="CUSTOM", details={})
    with pytest.raises(ResearchProjectV2Error) as discovery_exc:
        discover_sources(
            search_plan(),
            FailingProvider(discovery_failure),
            provider_name="failing",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        )
    assert discovery_exc.value is discovery_failure

    with pytest.raises(MemoryError):
        discover_sources(
            search_plan(),
            FailingProvider(MemoryError()),
            provider_name="failing",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        )


def test_discover_normalizes_deduplicates_excludes_policy_and_is_deterministic() -> None:
    plan = search_plan()
    original_plan = deepcopy(plan)
    raw_fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    original_fixture = deepcopy(raw_fixture)
    provider = ImportedJsonDiscoveryProvider(FIXTURE_PATH)
    original_provider_results = deepcopy(provider.results_by_query)

    first = discover_sources(
        plan,
        provider,
        provider_name="imported_json",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    second = discover_sources(
        plan,
        provider,
        provider_name="imported_json",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert first == second
    assert plan == original_plan
    assert raw_fixture == original_fixture
    assert provider.results_by_query == original_provider_results
    assert first["executed_query_ids"] == [
        "query:mechanism",
        "query:quantification",
        "query:counter",
    ]
    assert len(first["candidates"]) == 3
    duplicate = next(
        item for item in first["candidates"] if item["normalized_url"].endswith("?a=1&b=2")
    )
    assert duplicate["query_id"] == "query:mechanism"
    assert duplicate["rank"] == 2
    assert duplicate["title"] == "PCB fabrication standard overview"
    assert duplicate["dedup_key"] == duplicate["normalized_url"]
    assert duplicate["exclusion_status"] == "included"
    assert duplicate["exclusion_reasons"] == []
    engineering = next(
        item for item in first["candidates"] if item["source_class"] == "company_engineering_document"
    )
    assert engineering["exclusion_status"] == "included"
    assert len(first["policy_excluded_results"]) == 1
    excluded = first["policy_excluded_results"][0]
    assert excluded["source_class"] == "stock_opinion"
    assert excluded["exclusion_status"] == "excluded_by_policy"
    assert excluded["exclusion_reasons"]
    assert not ({"stock_rating", "company_rating"} & set(excluded))
    assert [
        (item["query_id"], item["normalized_url"], item["candidate_id"])
        for item in first["candidates"]
    ] == sorted(
        [
            (item["query_id"], item["normalized_url"], item["candidate_id"])
            for item in first["candidates"]
        ],
        key=lambda row: (
            {"query:mechanism": 1, "query:quantification": 2, "query:counter": 3}[row[0]],
            row[1],
            row[2],
        ),
    )
    assert first["content_hash"] == content_sha256(
        first, excluded_paths={("content_hash",)}
    )


def test_candidate_has_exact_schema_shape_and_validates_against_task2_definition() -> None:
    batch = discover_sources(
        search_plan(),
        StaticProvider({"query:mechanism": [result()]}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    candidate = batch["candidates"][0]
    expected_fields = {
        "candidate_id",
        "search_plan_id",
        "query_id",
        "normalized_url",
        "original_url",
        "title",
        "snippet",
        "publisher",
        "publish_date",
        "source_class",
        "rank",
        "exclusion_status",
        "exclusion_reasons",
        "dedup_key",
        "provenance",
    }
    assert set(candidate) == expected_fields
    assert candidate["provenance"] == PROVENANCE
    assert candidate["provenance"] is not PROVENANCE

    definitions_path = LayeredResearchLayout.default().schema_dir / "definitions_v2_1.schema.json"
    definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        definitions["$defs"]["industry_source_candidate"],
        resolver=RefResolver.from_schema(definitions),
        format_checker=FormatChecker(),
    )
    assert list(validator.iter_errors(candidate)) == []


def test_title_phrase_policy_exclusion_does_not_depend_on_source_class() -> None:
    provider = StaticProvider(
        {
            "query:mechanism": [
                result(
                    title="PCB process target price and buy rating",
                    source_class="independent_secondary",
                )
            ]
        }
    )

    batch = discover_sources(
        search_plan(),
        provider,
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert batch["candidates"] == []
    assert batch["policy_excluded_results"][0]["exclusion_status"] == "excluded_by_policy"


def test_deduplication_prefers_included_alias_over_higher_priority_policy_alias() -> None:
    provider = StaticProvider(
        {
            "query:mechanism": [
                result(
                    title="Top stock for PCB growth",
                    source_class="stock_opinion",
                    rank=2,
                )
            ],
            "query:quantification": [
                result(
                    title="Engineering measurements",
                    source_class="technical_standard",
                    query_id="query:quantification",
                    rank=1,
                )
            ],
        }
    )

    batch = discover_sources(
        search_plan(),
        provider,
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert len(batch["candidates"]) == 1
    assert batch["candidates"][0]["query_id"] == "query:quantification"
    assert batch["policy_excluded_results"] == []


def test_deduplication_keeps_one_excluded_winner_when_all_aliases_are_policy_results() -> None:
    provider = StaticProvider(
        {
            "query:mechanism": [
                result(title="Top stock picks", source_class="stock_opinion", rank=2),
                result(title="Buy rating", source_class="equity_research", rank=1),
            ]
        }
    )

    batch = discover_sources(
        search_plan(),
        provider,
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert batch["candidates"] == []
    assert len(batch["policy_excluded_results"]) == 1
    assert batch["policy_excluded_results"][0]["title"] == "Buy rating"


@pytest.mark.parametrize(
    "investment_text",
    [
        "target price raised",
        "new price target",
        "buy rating",
        "sell rating",
        "strong buy",
        "top stock picks",
        "company ranking",
        "目标价上调",
        "股票推荐名单",
        "买入评级",
        "卖出评级",
        "增持评级",
        "建议买入",
        "受益标的",
        "最强龙头",
        "估值最低",
    ],
)
def test_policy_taxonomy_excludes_investment_opinion_text(investment_text: str) -> None:
    batch = discover_sources(
        search_plan(),
        StaticProvider(
            {
                "query:mechanism": [
                    result(
                        title=investment_text,
                        snippet="Market commentary",
                        source_class="independent_secondary",
                    )
                ]
            }
        ),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert batch["candidates"] == []
    assert len(batch["policy_excluded_results"]) == 1


def test_policy_taxonomy_keeps_inventory_stock_and_company_engineering_context() -> None:
    batch = discover_sources(
        search_plan(),
        StaticProvider(
            {
                "query:mechanism": [
                    result(
                        url="https://example.com/warehouse",
                        title="Top stock levels in warehouse",
                        snippet="Inventory availability for production",
                        source_class="independent_secondary",
                    )
                ],
                "query:counter": [
                    result(
                        url="https://engineering.example.com/process",
                        title="Company engineering process notes",
                        source_class="company_engineering_document",
                        query_id="query:counter",
                    )
                ],
            }
        ),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert {item["title"] for item in batch["candidates"]} == {
        "Top stock levels in warehouse",
        "Company engineering process notes",
    }
    assert batch["policy_excluded_results"] == []


@pytest.mark.parametrize(
    ("bad_result", "reason"),
    [
        (result(query_id="query:unknown"), "unknown query_id"),
        (result(rank=0), "invalid rank"),
        (result(title="  "), "blank title"),
        (result(url=" "), "blank URL"),
        (result(source_class=" "), "blank source_class"),
        (result(publish_date="2026-02-30"), "invalid publish_date"),
        (result(publisher=123), "invalid publisher"),
    ],
)
def test_discover_rejects_invalid_provider_results(
    bad_result: DiscoveryResult, reason: str
) -> None:
    provider = StaticProvider({"query:mechanism": [bad_result]})
    assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            provider,
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason=reason,
    )


def test_discover_rejects_non_results_and_invalid_plan_or_batch_inputs() -> None:
    class BadProvider:
        def search(self, query: dict[str, Any]) -> list[DiscoveryResult]:
            return ["bad"]  # type: ignore[list-item]

    assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            BadProvider(),
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="invalid provider result type",
    )

    bad_plan = search_plan()
    bad_plan["queries"][1]["priority"] = 1
    assert_discovery_error(
        lambda: discover_sources(
            bad_plan,
            StaticProvider({}),
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="duplicate query priority",
    )


@pytest.mark.parametrize("bad_query_id", [" query:mechanism", "query:mechanism ", "  "])
def test_discover_rejects_search_plan_query_ids_with_whitespace(
    bad_query_id: str,
) -> None:
    plan = search_plan()
    plan["queries"][0]["query_id"] = bad_query_id

    exc = assert_discovery_error(
        lambda: discover_sources(
            plan,
            StaticProvider({}),
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="invalid query_id",
    )

    assert exc.details["query_id"] == bad_query_id


def test_discover_rejects_trimmed_equivalent_plan_query_ids_stably() -> None:
    plan = search_plan()
    plan["queries"][0]["query_id"] = "q"
    plan["queries"][1]["query_id"] = " q "

    exc = assert_discovery_error(
        lambda: discover_sources(
            plan,
            StaticProvider({}),
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="invalid query_id",
    )

    assert exc.details["query_id"] == " q "


@pytest.mark.parametrize("bad_query_id", [" query:mechanism", "query:mechanism "])
def test_discover_rejects_provider_result_query_id_whitespace(
    bad_query_id: str,
) -> None:
    provider = StaticProvider({"query:mechanism": [result(query_id=bad_query_id)]})

    exc = assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            provider,
            provider_name="static",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        ),
        reason="invalid query_id",
    )

    assert exc.details["query_id"] == bad_query_id


def test_write_batch_is_canonical_hashed_atomic_idempotent_and_immutable(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({"query:mechanism": [result()]}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    first_path = write_discovery_batch(batch, layout=layout)
    first_bytes = first_path.read_bytes()
    second_path = write_discovery_batch(deepcopy(batch), layout=layout)

    assert first_path == (
        layout.evidence_discovery_dir
        / "search_plan:pcb-industry"
        / f"{batch['content_hash']}.json"
    )
    assert second_path == first_path
    assert first_bytes == canonical_bytes(batch)
    assert second_path.read_bytes() == first_bytes
    assert list(first_path.parent.glob(f".{first_path.name}.*")) == []

    different = deepcopy(batch)
    different["provider"] = "tampered"
    different["content_hash"] = batch["content_hash"]
    assert_discovery_error(
        lambda: write_discovery_batch(different, layout=layout),
        reason="content_hash mismatch",
    )

    first_path.write_bytes(b"different")
    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="immutable batch path conflict",
    )


@pytest.mark.parametrize(
    "search_plan_id",
    ["../escape", "nested/path", "", ".", "search plan"],
)
def test_writer_rejects_unsafe_search_plan_ids(tmp_path: Path, search_plan_id: str) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    batch["search_plan_id"] = search_plan_id
    batch["content_hash"] = content_sha256(batch, excluded_paths={("content_hash",)})

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe search_plan_id",
    )
    assert not layout.evidence_discovery_dir.exists()


def test_writer_rejects_symlinked_parent_without_external_write(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    outside = tmp_path / "outside"
    outside.mkdir()
    layout.evidence_discovery_dir.parent.mkdir(parents=True)
    layout.evidence_discovery_dir.symlink_to(outside, target_is_directory=True)
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )
    assert list(outside.iterdir()) == []


def test_writer_failure_is_stable_and_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    def fail_link(source: str, target: str, **kwargs: object) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(discovery_module.os, "link", fail_link)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="discovery batch write failed",
    )
    batch_dir = layout.evidence_discovery_dir / batch["search_plan_id"]
    assert list(batch_dir.iterdir()) == []


def test_writer_rejects_non_directory_managed_parent_with_stable_error(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    layout.root.mkdir()
    (layout.root / "evidence").write_text("not a directory", encoding="utf-8")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )


def test_writer_concurrent_fresh_root_is_idempotent_and_never_overwrites(
    tmp_path: Path,
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({"query:mechanism": [result()]}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(
            executor.map(
                lambda _: write_discovery_batch(deepcopy(batch), layout=layout),
                range(16),
            )
        )

    assert len(set(paths)) == 1
    assert paths[0].read_bytes() == canonical_bytes(batch)
    assert list(paths[0].parent.iterdir()) == [paths[0]]


def test_writer_rejects_final_symlink_without_reading_or_writing_external_file(
    tmp_path: Path,
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    batch_dir = layout.evidence_discovery_dir / batch["search_plan_id"]
    batch_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("external", encoding="utf-8")
    target = batch_dir / f"{batch['content_hash']}.json"
    target.symlink_to(outside)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )
    assert outside.read_text(encoding="utf-8") == "external"


def test_writer_detects_final_symlink_swap_after_atomic_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    target = (
        layout.evidence_discovery_dir
        / batch["search_plan_id"]
        / f"{batch['content_hash']}.json"
    )
    outside = tmp_path / "outside-final.json"
    outside.write_text("external", encoding="utf-8")
    original_fsync = discovery_module.os.fsync
    calls = 0

    def swap_on_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            target.unlink()
            target.symlink_to(outside)
        original_fsync(descriptor)

    monkeypatch.setattr(discovery_module.os, "fsync", swap_on_directory_fsync)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )
    assert outside.read_text(encoding="utf-8") == "external"


def test_writer_detects_batch_directory_symlink_swap_without_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    batch_dir = layout.evidence_discovery_dir / batch["search_plan_id"]
    outside = tmp_path / "outside"
    outside.mkdir()
    original_link = discovery_module.os.link
    swapped = False

    def swap_then_link(source: str, target: str, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            backup = batch_dir.with_name(f"{batch_dir.name}-detached")
            batch_dir.rename(backup)
            batch_dir.symlink_to(outside, target_is_directory=True)
        original_link(source, target, **kwargs)

    monkeypatch.setattr(discovery_module.os, "link", swap_then_link)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )
    assert list(outside.iterdir()) == []


def test_writer_detects_discovery_directory_symlink_swap_without_false_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    discovery_dir = layout.evidence_discovery_dir
    outside = tmp_path / "outside-discovery"
    outside.mkdir()
    original_link = discovery_module.os.link
    swapped = False

    def swap_then_link(source: str, target: str, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            backup = discovery_dir.with_name("discovery-detached")
            discovery_dir.rename(backup)
            discovery_dir.symlink_to(outside, target_is_directory=True)
        original_link(source, target, **kwargs)

    monkeypatch.setattr(discovery_module.os, "link", swap_then_link)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="unsafe managed path",
    )
    assert list(outside.iterdir()) == []


def test_writer_fails_closed_without_required_posix_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    monkeypatch.setattr(discovery_module.os, "O_NOFOLLOW", 0)

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="secure dir-fd storage unavailable",
    )
    assert not layout.root.exists()


def test_writer_requires_absolute_managed_discovery_path() -> None:
    layout = LayeredResearchLayout(Path("relative-v2_1"))
    batch = discover_sources(
        search_plan(),
        StaticProvider({}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    assert_discovery_error(
        lambda: write_discovery_batch(batch, layout=layout),
        reason="managed discovery path must be absolute",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda batch: batch.pop("provider"),
        lambda batch: batch.update(extra=True),
        lambda batch: batch.update(discovered_at="today"),
        lambda batch: batch.update(executed_query_ids=["query:mechanism", 1]),
        lambda batch: batch.update(candidates="bad"),
        lambda batch: batch.update(policy_excluded_results="bad"),
    ],
)
def test_writer_strictly_validates_batch_structure(tmp_path: Path, mutation) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({"query:mechanism": [result()]}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    mutation(batch)
    if set(batch) == {
        "search_plan_id",
        "executed_query_ids",
        "provider",
        "discovered_at",
        "candidates",
        "policy_excluded_results",
        "content_hash",
    }:
        batch["content_hash"] = content_sha256(batch, excluded_paths={("content_hash",)})

    assert_discovery_error(lambda: write_discovery_batch(batch, layout=layout))
    assert not any(tmp_path.rglob("*.json"))


def test_writer_rejects_cross_field_inconsistency_and_noncanonical_order(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    provider = StaticProvider(
        {
            "query:mechanism": [
                result(url="https://example.com/b", title="B"),
                result(url="https://example.com/a", title="A", rank=2),
            ]
        }
    )
    valid = discover_sources(
        search_plan(),
        provider,
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )

    mutations = []
    reversed_candidates = deepcopy(valid)
    reversed_candidates["candidates"].reverse()
    mutations.append(reversed_candidates)
    mismatched_original = deepcopy(valid)
    mismatched_original["candidates"][0]["original_url"] = "https://other.example/a"
    mutations.append(mismatched_original)
    unknown_query = deepcopy(valid)
    unknown_query["candidates"][0]["query_id"] = "query:unknown"
    mutations.append(unknown_query)
    policy_leak = deepcopy(valid)
    policy_leak["candidates"][0]["source_class"] = "stock_opinion"
    mutations.append(policy_leak)

    for invalid in mutations:
        invalid["content_hash"] = content_sha256(
            invalid, excluded_paths={("content_hash",)}
        )
        assert_discovery_error(lambda invalid=invalid: write_discovery_batch(invalid, layout=layout))

    assert not any(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda batch: batch.update(provider=" static "),
        lambda batch: batch.update(discovered_at="2026-07-18 10:30:00+08:00"),
        lambda batch: batch["candidates"][0].update(title=" Engineering document "),
        lambda batch: batch["candidates"][0]["provenance"].update(
            created_by=" fixture-importer "
        ),
        lambda batch: batch["candidates"][0]["provenance"].update(
            created_at="2026-07-18 02:30:00+00:00"
        ),
    ],
)
def test_writer_rejects_semantically_equivalent_noncanonical_batch_strings(
    tmp_path: Path, mutate
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    batch = discover_sources(
        search_plan(),
        StaticProvider({"query:mechanism": [result()]}),
        provider_name="static",
        discovered_at=DISCOVERED_AT,
        provenance=PROVENANCE,
    )
    mutate(batch)
    batch["content_hash"] = content_sha256(batch, excluded_paths={("content_hash",)})

    assert_discovery_error(lambda: write_discovery_batch(batch, layout=layout))
    assert not any(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    ("provider_name", "provenance_mutation"),
    [
        (" static ", None),
        ("static", lambda value: value.update(created_by=" fixture-importer ")),
        (
            "static",
            lambda value: value.update(created_at="2026-07-18 02:30:00+00:00"),
        ),
    ],
)
def test_producer_rejects_noncanonical_provider_and_provenance_strings(
    provider_name: str, provenance_mutation
) -> None:
    provenance = deepcopy(PROVENANCE)
    if provenance_mutation is not None:
        provenance_mutation(provenance)

    assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            StaticProvider({}),
            provider_name=provider_name,
            discovered_at=DISCOVERED_AT,
            provenance=provenance,
        )
    )


def test_discover_requires_explicit_valid_discovered_at_and_provider_name() -> None:
    provider = StaticProvider({})
    for bad_time in ["", "today", datetime.now()]:
        assert_discovery_error(
            lambda bad_time=bad_time: discover_sources(
                search_plan(),
                provider,
                provider_name="static",
                discovered_at=bad_time,  # type: ignore[arg-type]
                provenance=PROVENANCE,
            )
        )
    assert_discovery_error(
        lambda: discover_sources(
            search_plan(),
            provider,
            provider_name=" ",
            discovered_at=DISCOVERED_AT,
            provenance=PROVENANCE,
        )
    )
