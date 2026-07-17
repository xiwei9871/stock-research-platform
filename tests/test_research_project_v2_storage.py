from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout


def test_default_layout_points_at_versioned_artifact_root():
    layout = ResearchProjectLayout.default()
    assert layout.root.as_posix().endswith("artifacts/research_projects/v2")
    assert layout.schema_dir == layout.root / "schema"
    assert layout.projects_dir == layout.root / "projects"
    assert layout.index_path == layout.root / "index/research_project_index_v2.json"


def test_domain_error_exposes_stable_code_and_details():
    error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details={"version": "0.1.0"},
    )
    assert error.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"
    assert error.details == {"version": "0.1.0"}


def test_domain_error_copies_details_for_each_instance():
    source_details = {"version": "0.1.0"}

    first_error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details=source_details,
    )
    second_error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details=source_details,
    )

    assert first_error.details is not source_details
    assert second_error.details is not source_details
    assert first_error.details is not second_error.details

    first_error.details["version"] = "0.2.0"

    assert second_error.details == {"version": "0.1.0"}
    assert source_details == {"version": "0.1.0"}
