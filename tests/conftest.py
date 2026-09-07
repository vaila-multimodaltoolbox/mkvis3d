from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def rec3d_csv() -> Path:
    return FIXTURES_DIR / "rec3d_20260826_121305.csv"


@pytest.fixture
def rec3d_c3d() -> Path:
    return FIXTURES_DIR / "rec3d_20260826_121305_m.c3d"
