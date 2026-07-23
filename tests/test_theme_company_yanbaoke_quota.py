from __future__ import annotations

import pandas as pd

from stock_research import theme_company_yanbaoke_quota as planner


def test_coverage_target_uses_approved_priority_bands():
    assert planner.coverage_target(95) == 3
    assert planner.coverage_target(89.9) == 2
    assert planner.coverage_target(79.9) == 1
    assert planner.coverage_target(60) == 1


def test_build_allocation_slots_respects_bucket_sizes_and_company_caps():
    companies = pd.DataFrame(
        [
            {"ts_code": "A.SH", "priority_score": 95, "pdf120": 0, "theme_count": 2, "scarcity_score": 5},
            {"ts_code": "B.SH", "priority_score": 85, "pdf120": 0, "theme_count": 1, "scarcity_score": 4},
            {"ts_code": "C.SH", "priority_score": 76, "pdf120": 0, "theme_count": 1, "scarcity_score": 3},
            {"ts_code": "D.SH", "priority_score": 70, "pdf120": 1, "theme_count": 1, "scarcity_score": 2},
        ]
    )

    slots = planner.build_allocation_slots(
        companies,
        primary_limit=6,
        multi_theme_limit=1,
        scarcity_limit=1,
        reserve_release_limit=1,
    )

    assert slots["allocation_bucket"].value_counts().to_dict() == {
        "primary_coverage": 6,
        "multi_theme_depth": 1,
        "theme_scarcity": 1,
        "reserve_release": 1,
    }
    counts = slots.groupby("ts_code").size().to_dict()
    assert counts["A.SH"] <= 5
    assert all(count <= 4 for code, count in counts.items() if code != "A.SH")


def test_select_download_queue_excludes_duplicates_and_enforces_caps():
    candidates = pd.DataFrame(
        [
            {"uuid": "u1", "ts_code": "A.SH", "broker": "Broker A", "report_title": "Company deep dive", "publish_date": "2026-07-20", "candidate_score": 100},
            {"uuid": "u2", "ts_code": "A.SH", "broker": "Broker A", "report_title": "Morning meeting", "publish_date": "2026-07-19", "candidate_score": 99},
            {"uuid": "u3", "ts_code": "B.SH", "broker": "Broker A", "report_title": "Initiation report", "publish_date": "2026-07-18", "candidate_score": 98},
            {"uuid": "u4", "ts_code": "C.SH", "broker": "Broker A", "report_title": "Quarterly review", "publish_date": "2026-07-17", "candidate_score": 97},
            {"uuid": "u5", "ts_code": "D.SH", "broker": "Broker B", "report_title": "Annual review", "publish_date": "2026-07-16", "candidate_score": 96},
            {"uuid": "u6", "ts_code": "D.SH", "broker": "Broker C", "report_title": "Annual review", "publish_date": "2026-07-16", "candidate_score": 95},
        ]
    )
    slots = pd.DataFrame(
        [
            {"ts_code": "A.SH", "allocation_bucket": "primary_coverage"},
            {"ts_code": "B.SH", "allocation_bucket": "primary_coverage"},
            {"ts_code": "C.SH", "allocation_bucket": "primary_coverage"},
            {"ts_code": "D.SH", "allocation_bucket": "primary_coverage"},
        ]
    )

    selected, replacements = planner.select_download_queue(
        candidates,
        slots,
        target_successes=4,
        candidate_pool_size=5,
        broker_cap=2,
        existing_uuids={"u3"},
    )

    assert "u2" not in set(selected["uuid"]) | set(replacements["uuid"])
    assert "u3" not in set(selected["uuid"]) | set(replacements["uuid"])
    assert selected["broker"].value_counts().max() <= 2
    assert selected["uuid"].is_unique
    assert replacements["uuid"].is_unique
    assert set(selected["uuid"]).isdisjoint(set(replacements["uuid"]))


def test_select_download_queue_excludes_existing_report_identity():
    candidates = pd.DataFrame(
        [
            {
                "uuid": "new_uuid",
                "ts_code": "A.SH",
                "broker": "Broker A",
                "report_title": "Company deep dive",
                "publish_date": "2026-07-20",
                "candidate_score": 100,
            }
        ]
    )
    slots = pd.DataFrame([{"ts_code": "A.SH", "allocation_bucket": "primary_coverage"}])

    selected, replacements = planner.select_download_queue(
        candidates,
        slots,
        target_successes=1,
        candidate_pool_size=2,
        existing_report_keys={
            ("A.SH", "Broker A", "2026-07-20", planner.normalize_report_title("Company deep dive"))
        },
    )

    assert selected.empty
    assert replacements.empty


def test_existing_report_identities_only_include_readable_pdfs():
    rows = [
        {
            "ts_code": "A.SH",
            "broker": "Broker A",
            "publish_date": "2026-07-20",
            "report_title": "Indexed only",
            "has_pdf": False,
        },
        {
            "ts_code": "B.SH",
            "broker": "Broker B",
            "publish_date": "2026-07-19",
            "report_title": "Readable report",
            "has_pdf": True,
        },
    ]

    identities = planner.existing_readable_report_keys(rows)

    assert identities == {
        ("B.SH", "Broker B", "2026-07-19", planner.normalize_report_title("Readable report"))
    }


def test_load_downloaded_manifest_uuids_reads_only_successes(tmp_path):
    manifest = tmp_path / "yanbaoke_direct_uuid_downloads.csv"
    pd.DataFrame(
        [
            {"uuid": "done_uuid", "status": "downloaded"},
            {"uuid": "error_uuid", "status": "error"},
            {"uuid": "", "status": "downloaded"},
        ]
    ).to_csv(manifest, index=False)

    assert planner.load_downloaded_manifest_uuids([manifest]) == {"done_uuid"}
