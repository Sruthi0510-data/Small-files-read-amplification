"""Shared fixtures, kept thin: most tests build the two files they need inline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sfa.cost import profile  # noqa: E402
from sfa.fixtures import events  # noqa: E402


@pytest.fixture(scope="session")
def s3():
    return profile("s3-spark")


@pytest.fixture(scope="session")
def shipped():
    return events()
