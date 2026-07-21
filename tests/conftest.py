from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    """Returns callable(name) -> html str from tests/fixtures/<name>.html."""
    def _load(name: str) -> str:
        return (FIXTURE_DIR / f"{name}.html").read_text(encoding="utf-8")
    return _load
