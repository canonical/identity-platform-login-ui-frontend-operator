#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from typing import Callable

import jubilant
import pytest
import requests
from integration.conftest import integrate_dependencies
from integration.constants import (
    APP_NAME,
    BUNDLE_PREFIX,
    ISTIO_APP,
    ISTIO_CHARM,
    ISTIO_INGRESS_APP,
    ISTIO_INGRESS_CHARM,
    ISTIO_INTEGRATION_NAME,
    MINIO_ACCESS_KEY,
    MINIO_APP,
    MINIO_BUCKET,
    MINIO_CHARM,
    MINIO_PORT,
    MINIO_SECRET_KEY,
    PUBLIC_INGRESS_DOMAIN,
    TRAEFIK_CHARM,
    TRAEFIK_INTEGRATION_NAME,
    TRAEFIK_PUBLIC_APP,
)
from integration.utils import (
    StatusPredicate,
    all_active,
    any_error,
    assert_security_headers,
    generate_self_signed_cert,
    get_unit_address,
    is_active,
    is_blocked,
    is_istio_control_plane_deployed,
    remove_integration,
    trust_ca_in_istio_gateway,
    trust_ca_in_unit,
    upload_sample_bundle,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy the charm-under-test with MinIO, Traefik, and Istio ingress."""
    assert juju.model is not None
    minio_fqdn = f"{MINIO_APP}.{juju.model}.svc.cluster.local"
    ssl_cert, ssl_key = generate_self_signed_cert(minio_fqdn)

    deploy_istio_core = not is_istio_control_plane_deployed()
    if deploy_istio_core:
        juju.deploy(
            ISTIO_CHARM,
            app=ISTIO_APP,
            channel="2/edge",
            trust=True,
        )

    juju.deploy(
        MINIO_CHARM,
        app=MINIO_APP,
        channel="ckf-1.9/stable",
        config={
            "access-key": MINIO_ACCESS_KEY,
            "secret-key": MINIO_SECRET_KEY,
            "ssl-cert": ssl_cert,
            "ssl-key": ssl_key,
        },
        trust=True,
    )

    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_PUBLIC_APP,
        channel="latest/stable",
        config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
        trust=True,
    )

    juju.deploy(
        str(local_charm),
        app=APP_NAME,
        base="ubuntu@22.04",
        trust=True,
    )

    if deploy_istio_core:
        juju.wait(
            ready=is_active(ISTIO_APP),
            error=any_error(ISTIO_APP),
            timeout=10 * 60,
        )

    juju.deploy(
        ISTIO_INGRESS_CHARM,
        app=ISTIO_INGRESS_APP,
        channel="2/edge",
        trust=True,
    )

    # Charm must enter BlockedStatus when ui-bundle-url is not yet configured
    juju.wait(
        ready=is_blocked(APP_NAME),
        error=any_error(APP_NAME),
        timeout=10 * 60,
    )

    juju.wait(
        ready=all_active(MINIO_APP, TRAEFIK_PUBLIC_APP, ISTIO_INGRESS_APP),
        error=any_error(MINIO_APP, TRAEFIK_PUBLIC_APP, ISTIO_INGRESS_APP),
        timeout=10 * 60,
    )

    # Install MinIO's self-signed CA certificate in the charm unit, Traefik, and Istio gateway
    trust_ca_in_unit(juju, f"{APP_NAME}/0", ssl_cert)
    trust_ca_in_unit(juju, f"{TRAEFIK_PUBLIC_APP}/0", ssl_cert, container="traefik")
    juju.ssh(f"{TRAEFIK_PUBLIC_APP}/0", "/charm/bin/pebble restart traefik", container="traefik")
    s3_service_host = f"{APP_NAME}-s3-external.{juju.model}.svc.cluster.local"
    trust_ca_in_istio_gateway(juju.model, ssl_cert, s3_service_host, MINIO_PORT)

    minio_address = get_unit_address(juju, app_name=MINIO_APP)
    upload_sample_bundle(f"https://{minio_address}:{MINIO_PORT}")

    bundle_url = f"https://{minio_fqdn}:{MINIO_PORT}/{MINIO_BUCKET}/{BUNDLE_PREFIX}"
    juju.config(
        APP_NAME,
        {
            "ui-bundle-url": bundle_url,
            "istio-resources-namespace": juju.model,
        },
    )

    integrate_dependencies(juju)

    juju.wait(
        ready=all_active(APP_NAME, TRAEFIK_PUBLIC_APP, ISTIO_INGRESS_APP),
        error=any_error(APP_NAME, TRAEFIK_PUBLIC_APP, ISTIO_INGRESS_APP),
        timeout=10 * 60,
    )


def test_traefik_routing(
    traefik_address: str,
    http_client: requests.Session,
) -> None:
    """Verify /ui, /ui/, /ui/login, /ui/login/, static assets, and missing paths via Traefik."""
    redirect_resp = http_client.get(f"http://{traefik_address}/ui", allow_redirects=False)
    assert redirect_resp.status_code in (301, 308)
    assert redirect_resp.headers["Location"].endswith("/ui/")

    root_resp = http_client.get(f"http://{traefik_address}/ui/")
    assert root_resp.status_code == 200
    assert "Index Page" in root_resp.text
    assert_security_headers(root_resp)

    slash_redirect_resp = http_client.get(
        f"http://{traefik_address}/ui/login/", allow_redirects=False
    )
    assert slash_redirect_resp.status_code in (301, 308)
    assert slash_redirect_resp.headers["Location"].endswith("/ui/login")

    login_resp = http_client.get(f"http://{traefik_address}/ui/login")
    assert login_resp.status_code == 200
    assert "Login Page" in login_resp.text
    assert_security_headers(login_resp)

    asset_resp = http_client.get(f"http://{traefik_address}/ui/_next/static/app.js")
    assert asset_resp.status_code == 200
    assert "login-ui-frontend" in asset_resp.text
    assert_security_headers(asset_resp)

    missing_resp = http_client.get(f"http://{traefik_address}/ui/nonexistent")
    assert missing_resp.status_code == 404


def test_istio_routing(
    istio_address: str,
    http_client: requests.Session,
) -> None:
    """Verify /ui, /ui/, /ui/login, /ui/login/, static assets, and missing paths via Istio."""
    redirect_resp = http_client.get(f"http://{istio_address}/ui", allow_redirects=False)
    assert redirect_resp.status_code == 301
    assert redirect_resp.headers["Location"].endswith("/ui/")

    root_resp = http_client.get(f"http://{istio_address}/ui/")
    assert root_resp.status_code == 200
    assert "Index Page" in root_resp.text
    assert_security_headers(root_resp)

    slash_redirect_resp = http_client.get(
        f"http://{istio_address}/ui/login/", allow_redirects=False
    )
    assert slash_redirect_resp.status_code == 301
    assert slash_redirect_resp.headers["Location"].endswith("/ui/login")

    login_resp = http_client.get(f"http://{istio_address}/ui/login")
    assert login_resp.status_code == 200
    assert "Login Page" in login_resp.text
    assert_security_headers(login_resp)

    asset_resp = http_client.get(f"http://{istio_address}/ui/_next/static/app.js")
    assert asset_resp.status_code == 200
    assert "login-ui-frontend" in asset_resp.text
    assert_security_headers(asset_resp)

    missing_resp = http_client.get(f"http://{istio_address}/ui/nonexistent")
    assert missing_resp.status_code == 404


@pytest.mark.parametrize(
    "remote_app_name,integration_name,is_status",
    [
        (TRAEFIK_PUBLIC_APP, TRAEFIK_INTEGRATION_NAME, is_active),
        (ISTIO_INGRESS_APP, ISTIO_INTEGRATION_NAME, is_active),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    is_status: Callable[[str], StatusPredicate],
) -> None:
    """Test removing and re-adding ingress integrations."""
    with remove_integration(juju, remote_app_name, integration_name):
        juju.wait(
            ready=is_status(APP_NAME),
            error=any_error(APP_NAME),
            timeout=10 * 60,
        )
    juju.wait(
        ready=all_active(APP_NAME, remote_app_name),
        error=any_error(APP_NAME, remote_app_name),
        timeout=10 * 60,
    )


@pytest.mark.teardown
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(APP_NAME, force=True, destroy_storage=True)
    juju.wait(lambda s: APP_NAME not in s.apps, timeout=10 * 60)
