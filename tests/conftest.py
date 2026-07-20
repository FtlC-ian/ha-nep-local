"""Shared Home Assistant test configuration."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


def pytest_configure(config):
    """Register the marker used by the HA custom integration test plugin."""
    config.addinivalue_line("markers", "enable_custom_integrations")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the repository's custom component discoverable to the HA loader."""
