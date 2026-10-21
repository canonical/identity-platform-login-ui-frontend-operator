# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for Identity Platform Login UI Frontend Operator."""

TRAEFIK_INTEGRATION_NAME = "traefik-ingress"
ISTIO_INTEGRATION_NAME = "istio-ingress"

PUBLIC_PATH_PREFIX = "/ui"

HEALTH_CHECK_PATH = "/index.html"
HEALTH_CHECK_TIMEOUT = 5

# Istio & Envoy constants
ENVOY_TUNNEL_PORT = 15999
INTERNAL_BUNDLE_HOST_SUFFIX = "-ui-bundle-internal"
FIELD_MANAGER = "identity-platform-login-ui-frontend-operator"
ISTIO_NETWORKING_GROUP = "networking.istio.io"
ISTIO_NETWORKING_VERSION = "v1alpha3"

# Template paths
TRAEFIK_ROUTE_TEMPLATE_PATH = "templates/traefik-route.json.j2"

# Security and cache-control headers matching identity-platform-login-ui/pkg/ui/handlers.go
PERMISSIONS_POLICY_HEADER = "interest-cohort=()"
X_CONTENT_TYPE_OPTIONS_HEADER = "nosniff"
X_FRAME_OPTIONS_HEADER = "SAMEORIGIN"
CONTENT_SECURITY_POLICY_HEADER = (
    "default-src 'self' data: https://assets.ubuntu.com; script-src 'self'; style-src 'self'"
)
CACHE_CONTROL_HEADER = "no-cache, no-store, must-revalidate"

RESPONSE_HEADERS: dict[str, str] = {
    "Permissions-Policy": PERMISSIONS_POLICY_HEADER,
    "X-Content-Type-Options": X_CONTENT_TYPE_OPTIONS_HEADER,
    "X-Frame-Options": X_FRAME_OPTIONS_HEADER,
    "Content-Security-Policy": CONTENT_SECURITY_POLICY_HEADER,
    "Cache-Control": CACHE_CONTROL_HEADER,
}
