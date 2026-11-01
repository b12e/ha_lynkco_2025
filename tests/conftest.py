"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the Home Assistant test harness load custom_components/lynkco."""
    yield
