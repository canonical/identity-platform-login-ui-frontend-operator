# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for integrations.py."""

from unittest.mock import MagicMock

from bundle import BundleUrl
from config import CharmConfig
from constants import RESPONSE_HEADERS
from integrations import IstioIngressRouteData, TraefikRouteData


class TestTraefikRouteData:
    """Tests for TraefikRouteData."""

    def test_is_ready_true(self) -> None:
        """Test TraefikRouteData.is_ready returns True when requirer is ready."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        assert TraefikRouteData.is_ready(requirer) is True

    def test_is_ready_false(self) -> None:
        """Test TraefikRouteData.is_ready returns False when requirer is not ready."""
        requirer = MagicMock()
        requirer.is_ready.return_value = False
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

    def test_is_ready_true(self) -> None:
        """Test IstioIngressRouteData.is_ready returns True when requirer is ready."""
        requirer = MagicMock()
        requirer.is_ready.return_value = True
        assert IstioIngressRouteData.is_ready(requirer) is True

    def test_is_ready_false(self) -> None:
        """Test IstioIngressRouteData.is_ready returns False when requirer is not ready."""
        requirer = MagicMock()
        requirer.is_ready.return_value = False
        assert IstioIngressRouteData.is_ready(requirer) is False

    def test_load_with_custom_port_and_hostnames(self) -> None:
        """Test IstioIngressRouteData.load preserves custom S3 port and hostnames."""
        requirer = MagicMock()
        requirer.tls_enabled = False
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

        assert len(data.config.listeners) == 1
        assert data.config.listeners[0].port == 80

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
            assert route.listener.port == 80

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

    def test_load_tls_enabled_uses_port_443(self) -> None:
        """Test IstioIngressRouteData.load sets listener port to 443 when TLS is enabled."""
        requirer = MagicMock()
        requirer.tls_enabled = True
        cfg = CharmConfig.from_dict({
            "ui-bundle-url": "https://s3.example.com/bucket",
        })

        data = IstioIngressRouteData.load(
            requirer,
            charm_config=cfg,
            app_name="login-ui",
            model_name="iam",
        )

        assert len(data.config.listeners) == 1
        assert data.config.listeners[0].port == 443
        for route in data.config.http_routes:
            assert route.listener.port == 443
