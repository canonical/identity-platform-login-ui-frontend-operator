# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for config.py."""

import pytest

from config import CharmConfig
from exceptions import InvalidConfigError


class TestCharmConfig:
    """Tests for CharmConfig validation and parsing."""

    def test_config_valid_minimal(self) -> None:
        """Test minimal valid configuration."""
        raw = {"ui-bundle-url": "https://s3.example.com:8443/dist"}
        cfg = CharmConfig.from_dict(raw)
        assert cfg.ui_bundle_url == "https://s3.example.com:8443/dist"
        assert cfg.bundle.hostname == "s3.example.com"
        assert cfg.bundle.port == 8443
        assert cfg.istio_route_hostnames == []
        assert cfg.istio_resources_namespace == ""

    def test_config_missing_url(self) -> None:
        """Test missing required ui-bundle-url."""
        with pytest.raises(InvalidConfigError, match="ui-bundle-url"):
            CharmConfig.from_dict({})

    def test_config_istio_options(self) -> None:
        """Test istio-route-hostnames and istio-resources-namespace parsing."""
        raw = {
            "ui-bundle-url": "https://s3.example.com/dist",
            "istio-route-hostnames": " auth.example.com , id.example.com , ",
            "istio-resources-namespace": " istio-system ",
        }
        cfg = CharmConfig.from_dict(raw)
        assert cfg.istio_route_hostnames == ["auth.example.com", "id.example.com"]
        assert cfg.istio_resources_namespace == "istio-system"
