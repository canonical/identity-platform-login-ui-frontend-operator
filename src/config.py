# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Typed configuration parser and validator for identity-platform-login-ui-frontend-operator."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from bundle import BundleUrl
from exceptions import InvalidConfigError


@dataclass(frozen=True, slots=True)
class CharmConfig:
    """Typed charm configuration."""

    ui_bundle_url: str
    bundle: BundleUrl
    istio_route_hostnames: list[str] = field(default_factory=list)
    istio_resources_namespace: str = ""

    @classmethod
    def from_dict(cls, config: Mapping[str, Any]) -> "CharmConfig":
        """Parse and validate configuration mapping from charm.config."""
        raw_url = str(config.get("ui-bundle-url") or "").strip()
        if not raw_url:
            raise InvalidConfigError("Option 'ui-bundle-url' is required.")

        bundle = BundleUrl.parse(raw_url)

        raw_hostnames = str(config.get("istio-route-hostnames") or "")
        hostnames = [h.strip() for hh in raw_hostnames.split(",") if (h := hh.strip())]

        return cls(
            ui_bundle_url=raw_url,
            bundle=bundle,
            istio_route_hostnames=hostnames,
            istio_resources_namespace=str(config.get("istio-resources-namespace") or "").strip(),
        )
