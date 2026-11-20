"""The repository address is written the same way everywhere (README, website, packaging, app)."""

from pathlib import Path

import pytest

import truck_tms

ROOT = Path(__file__).resolve().parent.parent


def test_project_urls():
    assert truck_tms.PROJECT_URL == "https://github.com/ArslanEren-Dev/truck-tms"
    assert truck_tms.WEBSITE_URL == "https://arslaneren-dev.github.io/truck-tms/"


@pytest.mark.parametrize("name", ["README.md", "docs/index.html", "pyproject.toml", "docs/CODE_SIGNING.md"])
def test_files_point_to_the_repository(name):
    path = ROOT / name
    if not path.is_file():
        pytest.skip("only available in a source checkout")
    text = path.read_text(encoding="utf-8")
    assert truck_tms.PROJECT_URL in text
    for placeholder in ("<your-username>", "<kullanici-adiniz>", "&lt;user&gt;", 'href="#"'):
        assert placeholder not in text, f"{placeholder} left in {name}"


def test_release_tag_check_matches_version_format():
    assert truck_tms.__version__.count(".") == 2
    workflow = ROOT / ".github" / "workflows" / "release.yml"
    if workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        assert "signpath/github-action-submit-signing-request@v3" in text
        assert "__version__" in text
