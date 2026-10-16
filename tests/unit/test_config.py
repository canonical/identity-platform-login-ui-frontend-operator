# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for config.py."""

import pytest

from config import CharmConfig
from exceptions import InvalidConfigError, IstioConfigError


class TestCharmConfig:
    """Tests for CharmConfig validation and parsing."""

    def test_config_valid_minimal(self) -> None:
        """Test minimal valid configuration."""
        raw = {"ui-bundle-url": "https://s3.example.com:8443/dist"}
        cfg = CharmConfig.from_dict(raw)
        assert cfg.ui_bundle_url == "https://s3.example.com:8443/dist"
        assert cfg.bundle.hostname == "s3.example.com"
        assert cfg.bundle.port == 8443
        assert cfg.istio_egress_proxy == ""
        assert cfg.proxy_host is None
        assert cfg.proxy_port is None
        assert cfg.istio_gateway_workload_labels == {}

    def test_config_missing_url(self) -> None:
        """Test missing required ui-bundle-url."""
        with pytest.raises(InvalidConfigError, match="ui-bundle-url"):
            CharmConfig.from_dict({})

    def test_config_istio_proxy_without_labels(self) -> None:
        """Test error when istio-egress-proxy is set without workload labels."""
        raw = {
            "ui-bundle-url": "https://s3.example.com/dist",
            "istio-egress-proxy": "proxy.example.com:3128",
        }
        with pytest.raises(IstioConfigError, match="istio-gateway-workload-labels"):
            CharmConfig.from_dict(raw)

    def test_config_istio_proxy_with_valid_labels(self) -> None:
        """Test istio-egress-proxy with workload labels and http:// prefix."""
        raw = {
            "ui-bundle-url": "https://s3.example.com/dist",
            "istio-egress-proxy": "http://proxy.example.com:3128",
            "istio-gateway-workload-labels": "app=istio-ingress, tier=gateway",
        }
        cfg = CharmConfig.from_dict(raw)
        assert cfg.istio_egress_proxy == "http://proxy.example.com:3128"
        assert cfg.proxy_host == "proxy.example.com"
        assert cfg.proxy_port == 3128
        assert cfg.istio_gateway_workload_labels == {
            "app": "istio-ingress",
            "tier": "gateway",
        }

    def test_config_istio_proxy_invalid_format(self) -> None:
        """Test invalid istio-egress-proxy without port."""
        raw = {
            "ui-bundle-url": "https://s3.example.com/dist",
            "istio-egress-proxy": "proxy.example.com",
            "istio-gateway-workload-labels": "app=istio-ingress",
        }
        with pytest.raises(IstioConfigError, match="host:port"):
            CharmConfig.from_dict(raw)

    def test_config_invalid_workload_labels(self) -> None:
        """Test malformed istio-gateway-workload-labels."""
        raw = {
            "ui-bundle-url": "https://s3.example.com/dist",
            "istio-gateway-workload-labels": "invalid-label-without-equals",
        }
        with pytest.raises(IstioConfigError, match="key=value"):
            CharmConfig.from_dict(raw)
