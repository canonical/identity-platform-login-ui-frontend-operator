# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Service layer for S3 bundle health checks and Istio mesh resource management."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import lightkube
import requests
from lightkube.core.exceptions import ApiError
from lightkube.core.generic_client import httpx
from lightkube.generic_resource import create_namespaced_resource
from lightkube.models.meta_v1 import ObjectMeta

from bundle import BundleUrl
from config import CharmConfig
from constants import (
    ENVOY_TUNNEL_PORT,
    FIELD_MANAGER,
    HEALTH_CHECK_TIMEOUT,
    INTERNAL_BUNDLE_HOST_SUFFIX,
    ISTIO_NETWORKING_GROUP,
    ISTIO_NETWORKING_VERSION,
    RESPONSE_HEADERS,
)
from exceptions import KubernetesPermissionError, KubernetesResourceError

logger = logging.getLogger(__name__)

SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")

ServiceEntry = create_namespaced_resource(
    group=ISTIO_NETWORKING_GROUP,
    version=ISTIO_NETWORKING_VERSION,
    kind="ServiceEntry",
    plural="serviceentries",
)

DestinationRule = create_namespaced_resource(
    group=ISTIO_NETWORKING_GROUP,
    version=ISTIO_NETWORKING_VERSION,
    kind="DestinationRule",
    plural="destinationrules",
)

EnvoyFilter = create_namespaced_resource(
    group=ISTIO_NETWORKING_GROUP,
    version=ISTIO_NETWORKING_VERSION,
    kind="EnvoyFilter",
    plural="envoyfilters",
)


class BundleHealthCheck:
    """Performs HTTP HEAD reachability checks against the static UI bundle."""

    @staticmethod
    def _get_proxies() -> Optional[Dict[str, str]]:
        """Retrieve Juju proxy settings from environment variables."""
        https_proxy = os.environ.get("JUJU_CHARM_HTTPS_PROXY") or os.environ.get("HTTPS_PROXY")
        http_proxy = os.environ.get("JUJU_CHARM_HTTP_PROXY") or os.environ.get("HTTP_PROXY")
        proxies: Dict[str, str] = {}
        if https_proxy:
            proxies["https"] = https_proxy
        if http_proxy:
            proxies["http"] = http_proxy
        return proxies if proxies else None

    @staticmethod
    def _get_ca_bundle() -> bool | str:
        """Determine the CA bundle for TLS verification, preferring system CA certificates."""
        ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
        if ca_bundle:
            return ca_bundle
        if SYSTEM_CA_BUNDLE.exists():
            return str(SYSTEM_CA_BUNDLE)
        return True

    @classmethod
    def check(cls, bundle: BundleUrl, timeout: int = HEALTH_CHECK_TIMEOUT) -> bool:
        """Check if the UI bundle index.html is reachable via HTTP HEAD."""
        url = bundle.get_index_url()
        proxies = cls._get_proxies()
        verify = cls._get_ca_bundle()

        try:
            response = requests.head(
                url,
                timeout=timeout,
                proxies=proxies,
                allow_redirects=True,
                verify=verify,
            )
            if 200 <= response.status_code < 400:
                return True
            logger.warning(
                "Health check to %s returned unexpected status code: %d",
                url,
                response.status_code,
            )
            return False
        except requests.RequestException as exc:
            logger.warning("Health check to %s failed: %s", url, exc)
            return False


class IstioMeshService:
    """Manages Istio ServiceEntry, DestinationRule, and EnvoyFilter resources via lightkube."""

    def __init__(self, app_name: str, namespace: str) -> None:
        self.app_name = app_name
        self.namespace = namespace
        self._client: Optional[lightkube.Client] = None

    @property
    def client(self) -> lightkube.Client:
        """Lazily initialise and return the lightkube Client."""
        if self._client is None:
            self._client = lightkube.Client(field_manager=FIELD_MANAGER)
        return self._client

    @property
    def internal_host(self) -> str:
        """Synthetic internal host used for the Envoy HTTP CONNECT tunnel."""
        return f"{self.app_name}{INTERNAL_BUNDLE_HOST_SUFFIX}"

    @property
    def internal_service_fqdn(self) -> str:
        """Kubernetes Service FQDN for the internal tunnel backend."""
        return f"{self.internal_host}.{self.namespace}.svc.cluster.local"

    @property
    def external_service_fqdn(self) -> str:
        """Kubernetes Service FQDN for the external S3 backend."""
        return f"{self.app_name}-s3-external.{self.namespace}.svc.cluster.local"

    @property
    def proxy_cluster_name(self) -> str:
        """Envoy cluster name for the corporate forward proxy."""
        return f"{self.app_name}-proxy-cluster"

    def _apply(self, resource: Any) -> None:
        """Apply a namespaced Kubernetes resource and translate ApiErrors."""
        try:
            self.client.apply(resource, field_manager=FIELD_MANAGER, force=True)
        except ApiError as exc:
            if exc.status.code == 403:
                logger.error("Kubernetes RBAC permission denied: %s", exc)
                raise KubernetesPermissionError(
                    "Missing RBAC permissions to manage Istio resources (try `juju trust`)."
                ) from exc
            logger.error("Failed to apply Istio resource: %s", exc)
            raise KubernetesResourceError(f"Failed to apply Istio resource: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.error("Kubernetes RBAC permission denied: %s", exc)
                raise KubernetesPermissionError(
                    "Missing RBAC permissions to manage Istio resources (try `juju trust`)."
                ) from exc
            logger.error("Failed to apply Istio resource: %s", exc)
            raise KubernetesResourceError(f"Failed to apply Istio resource: {exc}") from exc

    def _delete(self, resource_cls: Any, name: str, namespace: str) -> None:
        """Delete a namespaced Kubernetes resource, ignoring 404 Not Found errors."""
        try:
            self.client.delete(resource_cls, name=name, namespace=namespace)
        except ApiError as exc:
            if exc.status.code == 404:
                return
            if exc.status.code == 403:
                logger.error("Kubernetes RBAC permission denied on delete: %s", exc)
                raise KubernetesPermissionError(
                    "Missing RBAC permissions to delete Istio resources (try `juju trust`)."
                ) from exc
            logger.error("Failed to delete Istio resource %s/%s: %s", namespace, name, exc)
            raise KubernetesResourceError(f"Failed to delete Istio resource: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return
            if exc.response.status_code == 403:
                logger.error("Kubernetes RBAC permission denied on delete: %s", exc)
                raise KubernetesPermissionError(
                    "Missing RBAC permissions to delete Istio resources (try `juju trust`)."
                ) from exc
            logger.error("Failed to delete Istio resource %s/%s: %s", namespace, name, exc)
            raise KubernetesResourceError(f"Failed to delete Istio resource: {exc}") from exc

    def reconcile(self, config: CharmConfig) -> None:
        """Reconcile Istio mesh resources for either direct or proxy-tunnelled egress."""
        if config.istio_egress_proxy:
            self._reconcile_tunnel_mode(config)
        else:
            self._reconcile_direct_mode(config)
        self._reconcile_route_rewrite_filter(config)

    def _reconcile_route_rewrite_filter(self, config: CharmConfig) -> None:
        """Apply EnvoyFilter to configure regex rewrites, redirects, and security headers."""
        base = config.bundle.base_path.rstrip("/")
        gw_namespace = config.istio_resources_namespace or self.namespace
        filter_name = f"{self.app_name}-ui-rewrite"
        metadata_key = f"{self.app_name}_ui_response_headers"

        host_check_lines = ""
        if config.istio_route_hostnames:
            allowed_hosts = ", ".join(f'["{h}"] = true' for h in config.istio_route_hostnames)
            host_check_lines = (
                f"  local allowed_hosts = {{{allowed_hosts}}}\n"
                '  local authority = request_handle:headers():get(":authority") or ""\n'
                '  local host = string.gsub(authority, ":%d+$", "")\n'
                "  if not allowed_hosts[host] then\n"
                "    return\n"
                "  end\n"
            )

        header_lines = "\n".join(
            f'  response_handle:headers():replace("{key}", "{value}")'
            for key, value in RESPONSE_HEADERS.items()
        )

        lua_code = (
            "function envoy_on_request(request_handle)\n"
            f"{host_check_lines}"
            '  local raw_path = request_handle:headers():get(":path") or ""\n'
            '  local path, query = string.match(raw_path, "^([^?]*)(.*)$")\n'
            '  if not path or string.sub(path, 1, 4) ~= "/ui/" then\n'
            "    return\n"
            "  end\n"
            '  local slash_page = string.match(path, "^/ui/([^/.]+)/$")\n'
            "  if slash_page then\n"
            "    request_handle:respond(\n"
            '      {[":status"] = "301", ["location"] = "/ui/" .. slash_page .. (query or "")},\n'
            '      ""\n'
            "    )\n"
            "    return\n"
            "  end\n"
            "  request_handle:streamInfo():dynamicMetadata():set(\n"
            f'    "envoy.filters.http.lua", "{metadata_key}", "true"\n'
            "  )\n"
            f'  local base = "{base}"\n'
            '  if path == "/ui/" then\n'
            '    request_handle:headers():replace(":path", base .. "/index.html" .. (query or ""))\n'
            "    return\n"
            "  end\n"
            '  local page = string.match(path, "^/ui/([^/.]+)$")\n'
            "  if page then\n"
            '    request_handle:headers():replace(":path", base .. "/" .. page .. ".html" .. (query or ""))\n'
            "    return\n"
            "  end\n"
            "  local rest = string.sub(path, 5)\n"
            '  request_handle:headers():replace(":path", base .. "/" .. rest .. (query or ""))\n'
            "end\n\n"
            "function envoy_on_response(response_handle)\n"
            '  local meta = response_handle:streamInfo():dynamicMetadata():get("envoy.filters.http.lua")\n'
            f'  if not meta or meta["{metadata_key}"] ~= "true" then\n'
            "    return\n"
            "  end\n"
            f"{header_lines}\n"
            "end\n"
        )

        spec: Dict[str, Any] = {
            "configPatches": [
                {
                    "applyTo": "HTTP_FILTER",
                    "match": {
                        "context": "GATEWAY",
                        "listener": {
                            "filterChain": {
                                "filter": {
                                    "name": "envoy.filters.network.http_connection_manager",
                                    "subFilter": {
                                        "name": "envoy.filters.http.router",
                                    },
                                }
                            }
                        },
                    },
                    "patch": {
                        "operation": "INSERT_BEFORE",
                        "value": {
                            "name": "envoy.filters.http.lua",
                            "typed_config": {
                                "@type": "type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua",
                                "clearRouteCache": False,
                                "defaultSourceCode": {
                                    "inlineString": lua_code,
                                },
                            },
                        },
                    },
                }
            ]
        }
        if config.istio_gateway_workload_labels:
            spec["workloadSelector"] = {"labels": config.istio_gateway_workload_labels}

        ef = EnvoyFilter(
            metadata=ObjectMeta(name=filter_name, namespace=gw_namespace),
            spec=spec,
        )
        self._apply(ef)

    def _reconcile_direct_mode(self, config: CharmConfig) -> None:
        """Apply ServiceEntry and DestinationRule for direct TLS origination to S3 (PS6)."""
        s3_host = config.bundle.hostname
        s3_port = config.bundle.port
        resource_name = f"{self.app_name}-s3-external"

        se = ServiceEntry(
            metadata=ObjectMeta(name=resource_name, namespace=self.namespace),
            spec={
                "hosts": [self.external_service_fqdn, s3_host],
                "location": "MESH_EXTERNAL",
                "ports": [
                    {
                        "number": s3_port,
                        "name": "https",
                        "protocol": "TLS",
                        "targetPort": s3_port,
                    }
                ],
                "resolution": "DNS",
                "endpoints": [{"address": s3_host}],
            },
        )
        self._apply(se)

        dr = DestinationRule(
            metadata=ObjectMeta(name=resource_name, namespace=self.namespace),
            spec={
                "host": self.external_service_fqdn,
                "trafficPolicy": {
                    "tls": {
                        "mode": "SIMPLE",
                        "sni": s3_host,
                    },
                    "portLevelSettings": [
                        {
                            "port": {"number": s3_port},
                            "tls": {
                                "mode": "SIMPLE",
                                "sni": s3_host,
                            },
                        }
                    ],
                },
            },
        )
        self._apply(dr)

        # Remove any stale EnvoyFilter if switching from tunnel mode to direct mode
        gw_namespace = config.istio_resources_namespace or self.namespace
        filter_name = f"{self.app_name}-proxy-tunnel"
        self._delete(EnvoyFilter, name=filter_name, namespace=gw_namespace)

    def _reconcile_tunnel_mode(self, config: CharmConfig) -> None:
        """Apply ServiceEntry, DestinationRule, and EnvoyFilter for HTTP CONNECT proxy egress (PS7)."""
        s3_host = config.bundle.hostname
        s3_port = config.bundle.port
        resource_name = f"{self.app_name}-s3-external"

        se = ServiceEntry(
            metadata=ObjectMeta(name=resource_name, namespace=self.namespace),
            spec={
                "hosts": [self.internal_service_fqdn, self.internal_host],
                "location": "MESH_INTERNAL",
                "ports": [
                    {
                        "number": ENVOY_TUNNEL_PORT,
                        "name": "http",
                        "protocol": "HTTP",
                    }
                ],
                "resolution": "STATIC",
                "endpoints": [{"address": "127.0.0.1"}],
            },
        )
        self._apply(se)

        dr = DestinationRule(
            metadata=ObjectMeta(name=resource_name, namespace=self.namespace),
            spec={
                "host": self.internal_service_fqdn,
                "trafficPolicy": {
                    "tls": {
                        "mode": "SIMPLE",
                        "sni": s3_host,
                    },
                    "portLevelSettings": [
                        {
                            "port": {"number": ENVOY_TUNNEL_PORT},
                            "tls": {
                                "mode": "SIMPLE",
                                "sni": s3_host,
                            },
                        }
                    ],
                },
            },
        )
        self._apply(dr)

        gw_namespace = config.istio_resources_namespace or self.namespace
        filter_name = f"{self.app_name}-proxy-tunnel"

        ef = EnvoyFilter(
            metadata=ObjectMeta(name=filter_name, namespace=gw_namespace),
            spec={
                "workloadSelector": {"labels": config.istio_gateway_workload_labels},
                "configPatches": [
                    {
                        "applyTo": "LISTENER",
                        "match": {"context": "GATEWAY"},
                        "patch": {
                            "operation": "ADD",
                            "value": {
                                "name": f"{self.app_name}_connect_tunnel",
                                "address": {
                                    "socketAddress": {
                                        "address": "127.0.0.1",
                                        "portValue": ENVOY_TUNNEL_PORT,
                                    }
                                },
                                "filterChains": [
                                    {
                                        "filters": [
                                            {
                                                "name": "envoy.filters.network.tcp_proxy",
                                                "typedConfig": {
                                                    "@type": "type.googleapis.com/envoy.extensions.filters.network.tcp_proxy.v3.TcpProxy",
                                                    "statPrefix": "egress_proxy_tcp",
                                                    "cluster": self.proxy_cluster_name,
                                                    "tunnelingConfig": {
                                                        "hostname": f"{s3_host}:{s3_port}",
                                                    },
                                                },
                                            }
                                        ]
                                    }
                                ],
                            },
                        },
                    },
                    {
                        "applyTo": "CLUSTER",
                        "match": {"context": "GATEWAY"},
                        "patch": {
                            "operation": "ADD",
                            "value": {
                                "name": self.proxy_cluster_name,
                                "type": "LOGICAL_DNS",
                                "connectTimeout": "10s",
                                "lbPolicy": "ROUND_ROBIN",
                                "loadAssignment": {
                                    "clusterName": self.proxy_cluster_name,
                                    "endpoints": [
                                        {
                                            "lbEndpoints": [
                                                {
                                                    "endpoint": {
                                                        "address": {
                                                            "socketAddress": {
                                                                "address": config.proxy_host,
                                                                "portValue": config.proxy_port,
                                                            }
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    ],
                                },
                            },
                        },
                    },
                ],
            },
        )
        self._apply(ef)

    def cleanup(self, istio_resources_namespace: str = "") -> None:
        """Delete all Istio custom resources created by this charm."""
        resource_name = f"{self.app_name}-s3-external"
        filter_name = f"{self.app_name}-proxy-tunnel"
        rewrite_filter_name = f"{self.app_name}-ui-rewrite"
        gw_namespace = istio_resources_namespace or self.namespace

        self._delete(ServiceEntry, name=resource_name, namespace=self.namespace)
        self._delete(DestinationRule, name=resource_name, namespace=self.namespace)
        self._delete(EnvoyFilter, name=filter_name, namespace=gw_namespace)
        self._delete(EnvoyFilter, name=rewrite_filter_name, namespace=gw_namespace)
