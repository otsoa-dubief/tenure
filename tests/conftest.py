"""Test setup: tenure is imported as a package from the repository's tenure/ directory."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import pytest


@pytest.fixture(autouse=True)
def _study_start(monkeypatch):
    """Most tests exercise the study rule from T1: they start in probation, in study mode. Tests of the trusted start
    set ``start: trusted`` in their settings."""
    from tenure import params
    monkeypatch.setattr(params, "DEFAULT_START", os.environ.get("TENURE_TEST_START", "probation"))
    # Simple mode is the default since 1.4; the tests written for the study rule keep it (tests/test_simple_mode.py
    # sets ``mode: simple``).
    monkeypatch.setattr(params, "DEFAULT_MODE", os.environ.get("TENURE_TEST_MODE", "study"))
