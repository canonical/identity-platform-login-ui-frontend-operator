# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for constants and exceptions."""

from constants import (
    HEALTH_CHECK_PATH,
    ISTIO_INTEGRATION_NAME,
    ISTIO_NETWORKING_GROUP,
    ISTIO_NETWORKING_VERSION,
    PUBLIC_PATH_PREFIX,
    RESPONSE_HEADERS,
    TRAEFIK_INTEGRATION_NAME,
)
from exceptions import (
    BundleUrlError,
    InvalidConfigError,
    KubernetesPermissionError,
    KubernetesResourceError,
)


def test_constants() -> None:
    """Test constant values."""
    assert TRAEFIK_INTEGRATION_NAME == "traefik-ingress"
    assert ISTIO_INTEGRATION_NAME == "istio-ingress"
    assert PUBLIC_PATH_PREFIX == "/ui"
    assert HEALTH_CHECK_PATH == "/index.html"
    assert ISTIO_NETWORKING_GROUP == "networking.istio.io"
    assert ISTIO_NETWORKING_VERSION == "v1alpha3"
    assert "Content-Security-Policy" in RESPONSE_HEADERS
    assert "default-src 'self'" in RESPONSE_HEADERS["Content-Security-Policy"]


def test_exceptions() -> None:
    """Test custom exception hierarchy."""
    err = BundleUrlError("Invalid URL")
    assert isinstance(err, InvalidConfigError)
    assert str(err) == "Invalid URL"

    perm_err = KubernetesPermissionError("Forbidden")
    res_err = KubernetesResourceError("Server error")
    assert str(perm_err) == "Forbidden"
    assert str(res_err) == "Server error"
