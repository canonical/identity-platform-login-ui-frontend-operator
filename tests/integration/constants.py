# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]

TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_PUBLIC_APP = "traefik-public"
PUBLIC_INGRESS_DOMAIN = "public"
TRAEFIK_INTEGRATION_NAME = "traefik-ingress"

ISTIO_CHARM = "istio-k8s"
ISTIO_APP = "istio-k8s"
ISTIO_INGRESS_CHARM = "istio-ingress-k8s"
ISTIO_INGRESS_APP = "istio-ingress"
ISTIO_INTEGRATION_NAME = "istio-ingress"

MINIO_CHARM = "minio"
MINIO_APP = "minio"
MINIO_ACCESS_KEY = "minio"
MINIO_SECRET_KEY = "minio123"
MINIO_PORT = 9000
MINIO_BUCKET = "login-ui-bundle"
BUNDLE_PREFIX = "dist"

SAMPLE_BUNDLE_FILES: dict[str, str] = {
    f"{BUNDLE_PREFIX}/index.html": "<html><body>Index Page</body></html>",
    f"{BUNDLE_PREFIX}/404.html": "<html><body>404 Not Found</body></html>",
    f"{BUNDLE_PREFIX}/login.html": "<html><body>Login Page</body></html>",
    f"{BUNDLE_PREFIX}/_next/static/app.js": "console.log('login-ui-frontend');",
}

EXPECTED_SECURITY_HEADERS: dict[str, str] = {
    "Permissions-Policy": "interest-cohort=()",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": (
        "default-src 'self' data: https://assets.ubuntu.com; script-src 'self'; style-src 'self'"
    ),
    "Cache-Control": "no-cache, no-store, must-revalidate",
}
