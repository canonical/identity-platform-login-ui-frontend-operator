# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration data loaders and requirer helpers for Traefik and Istio ingress."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import yaml
from charmlibs.interfaces.istio_ingress_route import (
    BackendRef,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteRequirer,
    Listener,
    PathModifier,
    PathModifierType,
    ProtocolType,
    RequestRedirectFilter,
    RequestRedirectSpec,
    URLRewriteFilter,
    URLRewriteSpec,
)
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template

from bundle import BundleUrl
from config import CharmConfig
from constants import (
    ENVOY_TUNNEL_PORT,
    INTERNAL_BUNDLE_HOST_SUFFIX,
    PUBLIC_PATH_PREFIX,
    RESPONSE_HEADERS,
    TRAEFIK_ROUTE_TEMPLATE_PATH,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TraefikRouteData:
    """Data class representing the Traefik route configuration."""

    external_host: str = ""
    scheme: str = ""
    config: Dict = field(default_factory=dict)

    @classmethod
    def is_ready(cls, requirer: TraefikRouteRequirer) -> bool:
        """Check whether the Traefik route relation is active and not being torn down."""
        return requirer.is_ready()

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer, bundle: BundleUrl) -> "TraefikRouteData":
        """Render the Jinja2 Traefik dynamic configuration template for the given bundle."""
        external_host = requirer.external_host or ""
        scheme = requirer.scheme or "http"
        app_name = requirer._charm.app.name
        model_name = requirer._charm.model.name

        template_content = Path(TRAEFIK_ROUTE_TEMPLATE_PATH).read_text(encoding="utf-8")
        rendered = Template(template_content).render(
            model=model_name,
            app=app_name,
            external_host=external_host,
            origin=bundle.origin,
            base_path=bundle.base_path.rstrip("/"),
            public_path_prefix=PUBLIC_PATH_PREFIX,
            response_headers=RESPONSE_HEADERS,
        )
        config = yaml.safe_load(rendered)
        return cls(
            external_host=external_host,
            scheme=scheme,
            config=config,
        )


@dataclass(frozen=True, slots=True)
class IstioIngressRouteData:
    """Data class representing the Istio ingress route configuration."""

    config: IstioIngressRouteConfig

    @classmethod
    def is_ready(cls, requirer: IstioIngressRouteRequirer) -> bool:
        """Check whether the Istio ingress relation is active and not being torn down."""
        return requirer.is_ready()

    @classmethod
    def load(
        cls,
        requirer: IstioIngressRouteRequirer,
        charm_config: CharmConfig,
        app_name: str,
        model_name: str,
    ) -> "IstioIngressRouteData":
        """Build the IstioIngressRouteConfig for direct or proxied bundle backends."""
        bundle = charm_config.bundle
        base = bundle.base_path.rstrip("/")
        hostnames = charm_config.istio_route_hostnames or None

        if charm_config.istio_egress_proxy:
            backend_host = f"{app_name}{INTERNAL_BUNDLE_HOST_SUFFIX}"
            backend_port = ENVOY_TUNNEL_PORT
        else:
            backend_host = f"{app_name}-s3-external"
            backend_port = bundle.port

        http_listener = Listener(port=80, protocol=ProtocolType.HTTP)
        backend = BackendRef(service=backend_host, port=backend_port, weight=100)

        # 1. Exact /ui -> 301 redirect to /ui/
        redirect_route = HTTPRoute(
            name="ui-redirect",
            listener=http_listener,
            hostnames=hostnames,
            backends=[],
            matches=[
                HTTPRouteMatch(
                    path=HTTPPathMatch(
                        type=HTTPPathMatchType.Exact,
                        value=PUBLIC_PATH_PREFIX,
                    )
                )
            ],
            filters=[
                RequestRedirectFilter(
                    requestRedirect=RequestRedirectSpec(
                        path=PathModifier(
                            type=PathModifierType.ReplaceFullPath,
                            value=f"{PUBLIC_PATH_PREFIX}/",
                        ),
                        statusCode=301,
                    )
                )
            ],
        )

        # 2. Exact /ui/ -> rewrite to <base>/index.html
        root_route = HTTPRoute(
            name="ui-root",
            listener=http_listener,
            hostnames=hostnames,
            backends=[backend],
            matches=[
                HTTPRouteMatch(
                    path=HTTPPathMatch(
                        type=HTTPPathMatchType.Exact,
                        value=f"{PUBLIC_PATH_PREFIX}/",
                    )
                )
            ],
            filters=[
                URLRewriteFilter(
                    urlRewrite=URLRewriteSpec(
                        hostname=bundle.hostname,
                        path=PathModifier(
                            type=PathModifierType.ReplaceFullPath,
                            value=f"{base}/index.html" if base else "/index.html",
                        ),
                    )
                )
            ],
        )

        # 3. Trailing-slash page routes ^/ui/([^/.]+)/$ -> 301 redirect to /ui/<page> via EnvoyFilter
        page_slash_redirect_route = HTTPRoute(
            name="ui-page-slash-redirect",
            listener=http_listener,
            hostnames=hostnames,
            backends=[],
            matches=[
                HTTPRouteMatch(
                    path=HTTPPathMatch(
                        type=HTTPPathMatchType.RegularExpression,
                        value=f"^{PUBLIC_PATH_PREFIX}/([^/.]+)/$",
                    )
                )
            ],
            filters=[
                RequestRedirectFilter(
                    requestRedirect=RequestRedirectSpec(
                        path=PathModifier(
                            type=PathModifierType.ReplaceFullPath,
                            value=f"{PUBLIC_PATH_PREFIX}/",
                        ),
                        statusCode=301,
                    )
                )
            ],
        )

        # 4. Extensionless page routes ^/ui/([^/.]+)$ -> path rewritten to <base>/<page>.html via EnvoyFilter.
        # Trailing slash is excluded so /ui/<page>/ is redirected by ui-page-slash-redirect.
        page_route = HTTPRoute(
            name="ui-page",
            listener=http_listener,
            hostnames=hostnames,
            backends=[backend],
            matches=[
                HTTPRouteMatch(
                    path=HTTPPathMatch(
                        type=HTTPPathMatchType.RegularExpression,
                        value=f"^{PUBLIC_PATH_PREFIX}/([^/.]+)$",
                    )
                )
            ],
            filters=[
                URLRewriteFilter(
                    urlRewrite=URLRewriteSpec(
                        hostname=bundle.hostname,
                    )
                )
            ],
        )

        # 5. Static assets under /ui/... -> path rewritten to <base>/<asset> via EnvoyFilter.
        assets_route = HTTPRoute(
            name="ui-assets",
            listener=http_listener,
            hostnames=hostnames,
            backends=[backend],
            matches=[
                HTTPRouteMatch(
                    path=HTTPPathMatch(
                        type=HTTPPathMatchType.RegularExpression,
                        value=f"^{PUBLIC_PATH_PREFIX}/(?:.+/.+|.+\\..+)$",
                    )
                )
            ],
            filters=[
                URLRewriteFilter(
                    urlRewrite=URLRewriteSpec(
                        hostname=bundle.hostname,
                    )
                )
            ],
        )

        config = IstioIngressRouteConfig(
            model=model_name,
            listeners=[http_listener],
            http_routes=[
                redirect_route,
                root_route,
                page_slash_redirect_route,
                page_route,
                assets_route,
            ],
        )
        return cls(config=config)
