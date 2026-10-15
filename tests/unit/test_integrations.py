# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for integrations.py."""

from unittest.mock import MagicMock

from bundle import BundleUrl
from config import CharmConfig
from constants import (
    ENVOY_TUNNEL_PORT,
    INTERNAL_BUNDLE_HOST_SUFFIX,
    ISTIO_INTEGRATION_NAME,
    RESPONSE_HEADERS,
    TRAEFIK_INTEGRATION_NAME,
)
from integrations import IstioIngressRouteData, TraefikRouteData


class TestTraefikRouteData:
    """Tests for TraefikRouteData."""

    def test_is_ready_true(self) -> None:
        """Test TraefikRouteData.is_ready when relation and remote app exist."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        requirer._relation = MagicMock(app=MagicMock())
        assert TraefikRouteData.is_ready(requirer) is True

    def test_is_ready_false_when_departing(self) -> None:
        """Test TraefikRouteData.is_ready returns False when relation.app is None."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        requirer._relation = MagicMock(app=None)
        assert TraefikRouteData.is_ready(requirer) is False

    def test_is_ready_false_when_breaking(self) -> None:
        """Test TraefikRouteData.is_ready returns False when relation is marked breaking."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        requirer._relation = MagicMock(app=MagicMock())
        requirer._charm._breaking_relations = {TRAEFIK_INTEGRATION_NAME}
        assert TraefikRouteData.is_ready(requirer) is False

    def test_load_renders_template_with_headers_and_404(self) -> None:
        """Test TraefikRouteData.load renders Jinja2 template with all routers and middlewares."""
        requirer = MagicMock()
        requirer.external_host = "auth.example.com"
        requirer.scheme = "https"
        requirer._charm.app.name = "login-ui"
        requirer._charm.model.name = "iam"

        bundle = BundleUrl.parse("https://s3.example.com:8443/swift/v1/AUTH_123/ui")
        data = TraefikRouteData.load(requirer, bundle)

        assert data.external_host == "auth.example.com"
        assert data.scheme == "https"

        http_cfg = data.config["http"]
        middlewares = http_cfg["middlewares"]
        routers = http_cfg["routers"]
        services = http_cfg["services"]

        # Verify security headers middleware
        sec_headers = middlewares["login-ui-security-headers"]["headers"]["customResponseHeaders"]
        assert sec_headers == RESPONSE_HEADERS

        # Verify custom 404 error middleware
        err_mw = middlewares["login-ui-error-404"]["errors"]
        assert err_mw["status"] == "404"
        assert err_mw["service"] == "login-ui-s3-service"
        assert err_mw["query"] == "/swift/v1/AUTH_123/ui/404.html"

        # Verify page trailing-slash redirect middleware and router
        slash_mw = middlewares["login-ui-page-slash-redirect-mw"]["redirectRegex"]
        assert slash_mw["regex"] == "^(.*)/ui/([^/.]+)/$"
        assert slash_mw["replacement"] == "${1}/ui/${2}"
        assert slash_mw["permanent"] is True
        assert "login-ui-page-slash-redirect" in routers
        assert "login-ui-page-slash-redirect-tls" in routers

        # Verify page middleware excludes trailing slash
        page_mw = middlewares["login-ui-page-mw"]["replacePathRegex"]
        assert page_mw["regex"] == "^/ui/([^/.]+)$"
        assert page_mw["replacement"] == "/swift/v1/AUTH_123/ui/$1.html"

        # Verify backend service
        lb = services["login-ui-s3-service"]["loadBalancer"]
        assert lb["passHostHeader"] is False
        assert lb["servers"] == [{"url": "https://s3.example.com:8443"}]


class TestIstioIngressRouteData:
    """Tests for IstioIngressRouteData."""

    def test_is_ready_false_when_breaking(self) -> None:
        """Test IstioIngressRouteData.is_ready returns False when relation is marked breaking."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        requirer._charm._breaking_relations = {ISTIO_INTEGRATION_NAME}
        assert IstioIngressRouteData.is_ready(requirer) is False

    def test_load_direct_mode_with_custom_port_and_hostnames(self) -> None:
        """Test IstioIngressRouteData.load in direct mode preserves custom S3 port and hostnames."""
        requirer = MagicMock()
        cfg = CharmConfig.from_dict({
            "ui-bundle-url": "https://s3.example.com:9443/bucket/v1",
            "istio-route-hostnames": "auth.example.com, id.example.com",
        })

        data = IstioIngressRouteData.load(
            requirer,
            charm_config=cfg,
            app_name="login-ui",
            model_name="iam",
        )

        routes = {r.name: r for r in data.config.http_routes}
        assert set(routes.keys()) == {
            "ui-redirect",
            "ui-root",
            "ui-page-slash-redirect",
            "ui-page",
            "ui-assets",
        }

        for route in routes.values():
            assert route.hostnames == ["auth.example.com", "id.example.com"]

        # Direct mode backend uses DNS-1035 service name and custom port
        root_backend = routes["ui-root"].backends[0]
        assert root_backend.service == "login-ui-s3-external"
        assert root_backend.port == 9443

        # Trailing-slash redirect route matches ^/ui/([^/.]+)/$ with 301 fallback
        slash_route = routes["ui-page-slash-redirect"]
        assert slash_route.matches[0].path.value == "^/ui/([^/.]+)/$"
        slash_redirect = slash_route.filters[0].requestRedirect
        assert slash_redirect.path.value == "/ui/"
        assert slash_redirect.statusCode == 301

        # Page regex excludes trailing slash and rewrites only hostname (path rewritten by EnvoyFilter)
        page_match = routes["ui-page"].matches[0].path
        assert page_match.value == "^/ui/([^/.]+)$"
        page_rewrite = routes["ui-page"].filters[0].urlRewrite
        assert page_rewrite.hostname == "s3.example.com"
        assert page_rewrite.path is None

        # Assets route rewrites only hostname (path rewritten by EnvoyFilter)
        assets_rewrite = routes["ui-assets"].filters[0].urlRewrite
        assert assets_rewrite.hostname == "s3.example.com"
        assert assets_rewrite.path is None

        # URLRewrite sets Host header to s3.example.com and exact path on ui-root
        root_rewrite = routes["ui-root"].filters[0].urlRewrite
        assert root_rewrite.hostname == "s3.example.com"
        assert root_rewrite.path.value == "/bucket/v1/index.html"

    def test_load_tunnel_mode(self) -> None:
        """Test IstioIngressRouteData.load in proxy tunnel mode targets synthetic internal host."""
        requirer = MagicMock()
        cfg = CharmConfig.from_dict({
            "ui-bundle-url": "https://s3.example.com:9443/bucket",
            "istio-egress-proxy": "proxy.internal:3128",
            "istio-gateway-workload-labels": "istio=ingressgateway",
        })

        data = IstioIngressRouteData.load(
            requirer,
            charm_config=cfg,
            app_name="login-ui",
            model_name="iam",
        )

        routes = {r.name: r for r in data.config.http_routes}
        root_backend = routes["ui-root"].backends[0]
        assert routes["ui-root"].hostnames is None
        assert root_backend.service == f"login-ui{INTERNAL_BUNDLE_HOST_SUFFIX}"
        assert root_backend.port == ENVOY_TUNNEL_PORT
