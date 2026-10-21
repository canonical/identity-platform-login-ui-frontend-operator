# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Typed configuration parser and validator for identity-platform-login-ui-frontend-operator."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from bundle import BundleUrl
from exceptions import InvalidConfigError, IstioConfigError


@dataclass(frozen=True, slots=True)
class CharmConfig:
    """Typed charm configuration."""

    ui_bundle_url: str
    bundle: BundleUrl
    istio_route_hostnames: list[str] = field(default_factory=list)
    istio_resources_namespace: str = ""
    istio_egress_proxy: str = ""
    istio_gateway_workload_labels: dict[str, str] = field(default_factory=dict)
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None

    @staticmethod
    def _parse_proxy(raw_proxy: str) -> tuple[Optional[str], Optional[int]]:
        """Parse and validate the istio-egress-proxy host:port string."""
        if not raw_proxy:
            return None, None

        cleaned_proxy = raw_proxy
        for prefix in ("http://", "https://"):
            if cleaned_proxy.startswith(prefix):
                cleaned_proxy = cleaned_proxy[len(prefix) :]
                break
        cleaned_proxy = cleaned_proxy.rstrip("/")
        if ":" not in cleaned_proxy:
            raise IstioConfigError(
                f"Invalid 'istio-egress-proxy' value '{raw_proxy}'. Expected host:port."
            )
        host_part, port_part = cleaned_proxy.rsplit(":", 1)
        host_part = host_part.strip()
        try:
            port_val = int(port_part.strip())
        except ValueError as e:
            raise IstioConfigError(
                f"Invalid port in 'istio-egress-proxy' value '{raw_proxy}'. Expected integer port."
            ) from e
        if not host_part or not (1 <= port_val <= 65535):
            raise IstioConfigError(
                f"Invalid 'istio-egress-proxy' value '{raw_proxy}'. Expected valid host:port."
            )
        return host_part, port_val

    @staticmethod
    def _parse_labels(raw_labels: str) -> dict[str, str]:
        """Parse and validate comma-separated key=value workload labels."""
        labels: dict[str, str] = {}
        if not raw_labels.strip():
            return labels

        for item in raw_labels.split(","):
            if "=" not in item:
                raise IstioConfigError(
                    f"Invalid label pair '{item}' in 'istio-gateway-workload-labels'. Expected key=value."
                )
            k, v = item.split("=", 1)
            labels[k.strip()] = v.strip()
        return labels

    @classmethod
    def from_dict(cls, config: Mapping[str, Any]) -> "CharmConfig":
        """Parse and validate configuration mapping from charm.config."""
        raw_url = str(config.get("ui-bundle-url") or "").strip()
        if not raw_url:
            raise InvalidConfigError("Option 'ui-bundle-url' is required.")

        bundle = BundleUrl.parse(raw_url)

        raw_hostnames = str(config.get("istio-route-hostnames") or "")
        hostnames = [h.strip() for hh in raw_hostnames.split(",") if (h := hh.strip())]

        raw_proxy = str(config.get("istio-egress-proxy") or "").strip()
        proxy_host, proxy_port = cls._parse_proxy(raw_proxy)

        raw_labels = str(config.get("istio-gateway-workload-labels") or "")
        labels = cls._parse_labels(raw_labels)

        if raw_proxy and not labels:
            raise IstioConfigError(
                "Option 'istio-gateway-workload-labels' is required when 'istio-egress-proxy' is set."
            )

        return cls(
            ui_bundle_url=raw_url,
            bundle=bundle,
            istio_route_hostnames=hostnames,
            istio_resources_namespace=str(config.get("istio-resources-namespace") or "").strip(),
            istio_egress_proxy=raw_proxy,
            istio_gateway_workload_labels=labels,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
        )
