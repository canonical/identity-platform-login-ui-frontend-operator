# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for services.py."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from lightkube.core.exceptions import ApiError
from lightkube.core.generic_client import httpx

from bundle import BundleUrl
from config import CharmConfig
from constants import ENVOY_TUNNEL_PORT, INTERNAL_BUNDLE_HOST_SUFFIX
from exceptions import KubernetesPermissionError, KubernetesResourceError
from services import (
    SYSTEM_CA_BUNDLE,
    BundleHealthCheck,
    DestinationRule,
    EnvoyFilter,
    IstioMeshService,
    ServiceEntry,
)


class TestBundleHealthCheck:
    """Tests for BundleHealthCheck."""

    @patch("services.requests.head")
    def test_check_success(self, mock_head: MagicMock) -> None:
        """Test successful HTTP HEAD check."""
        mock_head.return_value = MagicMock(status_code=200)
        bundle = BundleUrl.parse("https://s3.example.com/dist")
        assert BundleHealthCheck.check(bundle) is True
        expected_verify = str(SYSTEM_CA_BUNDLE) if SYSTEM_CA_BUNDLE.exists() else True
        mock_head.assert_called_once_with(
            "https://s3.example.com/dist/index.html",
            timeout=5,
            proxies=None,
            allow_redirects=True,
            verify=expected_verify,
        )

    @patch("services.requests.head")
    def test_check_with_juju_proxies(
        self, mock_head: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test HTTP HEAD check respects JUJU_CHARM_HTTPS_PROXY."""
        monkeypatch.setenv("JUJU_CHARM_HTTPS_PROXY", "http://squid.internal:3128")
        mock_head.return_value = MagicMock(status_code=200)
        bundle = BundleUrl.parse("https://s3.example.com/dist")
        assert BundleHealthCheck.check(bundle) is True
        expected_verify = str(SYSTEM_CA_BUNDLE) if SYSTEM_CA_BUNDLE.exists() else True
        mock_head.assert_called_once_with(
            "https://s3.example.com/dist/index.html",
            timeout=5,
            proxies={"https": "http://squid.internal:3128"},
            allow_redirects=True,
            verify=expected_verify,
        )

    @patch("services.requests.head")
    def test_check_with_requests_ca_bundle_env(
        self, mock_head: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test HTTP HEAD check respects REQUESTS_CA_BUNDLE."""
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/custom/ca.crt")
        mock_head.return_value = MagicMock(status_code=200)
        bundle = BundleUrl.parse("https://s3.example.com/dist")
        assert BundleHealthCheck.check(bundle) is True
        mock_head.assert_called_once_with(
            "https://s3.example.com/dist/index.html",
            timeout=5,
            proxies=None,
            allow_redirects=True,
            verify="/custom/ca.crt",
        )

    @patch("services.requests.head")
    def test_check_non_200_returns_false(self, mock_head: MagicMock) -> None:
        """Test HTTP 404 returns False."""
        mock_head.return_value = MagicMock(status_code=404)
        bundle = BundleUrl.parse("https://s3.example.com/dist")
        assert BundleHealthCheck.check(bundle) is False

    @patch("services.requests.head")
    def test_check_request_exception_returns_false(self, mock_head: MagicMock) -> None:
        """Test network exception returns False."""
        mock_head.side_effect = requests.ConnectionError("Unreachable")
        bundle = BundleUrl.parse("https://s3.example.com/dist")
        assert BundleHealthCheck.check(bundle) is False


class TestIstioMeshService:
    """Tests for IstioMeshService."""

    def test_reconcile_direct_mode_with_custom_port(self) -> None:
        """Test PS6 direct mode creates ServiceEntry, DestinationRule, and rewrite EnvoyFilter."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        cfg = CharmConfig.from_dict({"ui-bundle-url": "https://s3.example.com:8443/dist"})
        service.reconcile(cfg)

        assert mock_client.apply.call_count == 3
        applied_se = mock_client.apply.call_args_list[0].args[0]
        applied_dr = mock_client.apply.call_args_list[1].args[0]
        applied_rewrite_ef = mock_client.apply.call_args_list[2].args[0]

        assert isinstance(applied_se, ServiceEntry)
        assert applied_se.spec["hosts"] == [
            "login-ui-s3-external.iam.svc.cluster.local",
            "s3.example.com",
        ]
        assert applied_se.spec["location"] == "MESH_EXTERNAL"
        assert applied_se.spec["ports"][0]["number"] == 8443
        assert applied_se.spec["ports"][0]["targetPort"] == 8443
        assert applied_se.spec["endpoints"] == [{"address": "s3.example.com"}]

        assert isinstance(applied_dr, DestinationRule)
        assert applied_dr.spec["host"] == "login-ui-s3-external.iam.svc.cluster.local"
        assert applied_dr.spec["trafficPolicy"]["tls"] == {
            "mode": "SIMPLE",
            "sni": "s3.example.com",
        }
        assert applied_dr.spec["trafficPolicy"]["portLevelSettings"][0]["port"]["number"] == 8443

        assert isinstance(applied_rewrite_ef, EnvoyFilter)
        assert applied_rewrite_ef.metadata.name == "login-ui-ui-rewrite"
        assert len(applied_rewrite_ef.spec["configPatches"]) == 1
        http_filter_patch = applied_rewrite_ef.spec["configPatches"][0]
        assert http_filter_patch["applyTo"] == "HTTP_FILTER"
        lua_cfg = http_filter_patch["patch"]["value"]["typed_config"]
        assert lua_cfg["clearRouteCache"] is False
        lua_code = lua_cfg["defaultSourceCode"]["inlineString"]
        assert "Content-Security-Policy" in lua_code
        assert 'local base = "/dist"' in lua_code

        mock_client.delete.assert_called_once_with(
            EnvoyFilter, name="login-ui-proxy-tunnel", namespace="iam"
        )

    def test_reconcile_tunnel_mode_with_sni_and_cluster_patch(self) -> None:
        """Test PS7 tunnel mode sets SNI to s3_host and includes LISTENER and CLUSTER patches."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        cfg = CharmConfig.from_dict({
            "ui-bundle-url": "https://s3.example.com:8443/dist",
            "istio-egress-proxy": "proxy.internal:3128",
            "istio-gateway-workload-labels": "istio=ingressgateway",
            "istio-resources-namespace": "istio-system",
        })
        service.reconcile(cfg)

        assert mock_client.apply.call_count == 4
        applied_se = mock_client.apply.call_args_list[0].args[0]
        applied_dr = mock_client.apply.call_args_list[1].args[0]
        applied_ef = mock_client.apply.call_args_list[2].args[0]
        applied_rewrite_ef = mock_client.apply.call_args_list[3].args[0]

        internal_host = f"login-ui{INTERNAL_BUNDLE_HOST_SUFFIX}"
        internal_fqdn = f"{internal_host}.iam.svc.cluster.local"
        assert applied_se.spec["hosts"] == [internal_fqdn, internal_host]
        assert applied_se.spec["ports"][0]["number"] == ENVOY_TUNNEL_PORT

        # Verify DestinationRule sets SNI to actual S3 hostname (not internal_host)
        assert applied_dr.spec["host"] == internal_fqdn
        assert applied_dr.spec["trafficPolicy"]["tls"]["sni"] == "s3.example.com"
        assert (
            applied_dr.spec["trafficPolicy"]["portLevelSettings"][0]["tls"]["sni"]
            == "s3.example.com"
        )

        # Verify EnvoyFilter has both LISTENER and CLUSTER patches in istio-system
        assert applied_ef.metadata.namespace == "istio-system"
        assert applied_ef.spec["workloadSelector"] == {"labels": {"istio": "ingressgateway"}}
        patches = applied_ef.spec["configPatches"]
        assert len(patches) == 2

        listener_patch = patches[0]
        assert listener_patch["applyTo"] == "LISTENER"
        tcp_cfg = listener_patch["patch"]["value"]["filterChains"][0]["filters"][0]["typedConfig"]
        assert tcp_cfg["cluster"] == "login-ui-proxy-cluster"
        assert tcp_cfg["tunnelingConfig"]["hostname"] == "s3.example.com:8443"

        cluster_patch = patches[1]
        assert cluster_patch["applyTo"] == "CLUSTER"
        cluster_val = cluster_patch["patch"]["value"]
        assert cluster_val["name"] == "login-ui-proxy-cluster"
        socket_addr = cluster_val["loadAssignment"]["endpoints"][0]["lbEndpoints"][0]["endpoint"][
            "address"
        ]["socketAddress"]
        assert socket_addr == {"address": "proxy.internal", "portValue": 3128}

        assert applied_rewrite_ef.metadata.name == "login-ui-ui-rewrite"
        assert applied_rewrite_ef.metadata.namespace == "istio-system"
        assert applied_rewrite_ef.spec["workloadSelector"] == {
            "labels": {"istio": "ingressgateway"}
        }

    def test_cleanup_deletes_all_resources(self) -> None:
        """Test cleanup deletes ServiceEntry, DestinationRule, and EnvoyFilters."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        service.cleanup(istio_resources_namespace="istio-gw")

        assert mock_client.delete.call_count == 4
        mock_client.delete.assert_any_call(
            ServiceEntry, name="login-ui-s3-external", namespace="iam"
        )
        mock_client.delete.assert_any_call(
            DestinationRule, name="login-ui-s3-external", namespace="iam"
        )
        mock_client.delete.assert_any_call(
            EnvoyFilter, name="login-ui-proxy-tunnel", namespace="istio-gw"
        )
        mock_client.delete.assert_any_call(
            EnvoyFilter, name="login-ui-ui-rewrite", namespace="istio-gw"
        )

    def test_apply_403_raises_permission_error(self) -> None:
        """Test 403 ApiError translates to KubernetesPermissionError."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        api_err = ApiError.__new__(ApiError)
        api_err.status = MagicMock(code=403, message="Forbidden")
        mock_client.apply.side_effect = api_err

        cfg = CharmConfig.from_dict({"ui-bundle-url": "https://s3.example.com/dist"})
        with pytest.raises(KubernetesPermissionError, match="RBAC"):
            service.reconcile(cfg)

    def test_apply_500_raises_resource_error(self) -> None:
        """Test non-403 ApiError translates to KubernetesResourceError."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        api_err = ApiError.__new__(ApiError)
        api_err.status = MagicMock(code=500, message="Internal Error")
        mock_client.apply.side_effect = api_err

        cfg = CharmConfig.from_dict({"ui-bundle-url": "https://s3.example.com/dist"})
        with pytest.raises(KubernetesResourceError, match="Failed to apply"):
            service.reconcile(cfg)

    def test_cleanup_ignores_http_404_when_crds_absent(self) -> None:
        """Test cleanup ignores httpx.HTTPStatusError 404 when Istio CRDs are absent."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        request = httpx.Request(
            "DELETE",
            "https://k8s/apis/networking.istio.io/v1alpha3/namespaces/iam/serviceentries/x",
        )
        response = httpx.Response(404, request=request, text="404 page not found")
        mock_client.delete.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=request, response=response
        )

        service.cleanup(istio_resources_namespace="iam")
        assert mock_client.delete.call_count == 4

    def test_apply_http_status_error_raises_resource_error(self) -> None:
        """Test httpx.HTTPStatusError on apply translates to KubernetesResourceError."""
        service = IstioMeshService(app_name="login-ui", namespace="iam")
        mock_client = MagicMock()
        service._client = mock_client

        request = httpx.Request(
            "PATCH",
            "https://k8s/apis/networking.istio.io/v1alpha3/namespaces/iam/serviceentries/x",
        )
        response = httpx.Response(404, request=request, text="404 page not found")
        mock_client.apply.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=request, response=response
        )

        cfg = CharmConfig.from_dict({"ui-bundle-url": "https://s3.example.com/dist"})
        with pytest.raises(KubernetesResourceError, match="Failed to apply"):
            service.reconcile(cfg)
