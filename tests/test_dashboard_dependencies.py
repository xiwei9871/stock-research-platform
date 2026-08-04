from pathlib import Path
import tomllib


def test_dashboard_test_dependencies_declare_standard_httpx_package() -> None:
    project_file = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))

    dev_dependencies = project["project"]["optional-dependencies"]["dev"]

    assert "httpx" in dev_dependencies
    assert "httpx2" not in dev_dependencies
