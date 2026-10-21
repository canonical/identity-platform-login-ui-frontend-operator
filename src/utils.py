# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility decorators and precondition checks for charm event handling."""

import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Tuple

from config import CharmConfig
from exceptions import InvalidConfigError
from integrations import IstioIngressRouteData, TraefikRouteData
from services import BundleHealthCheck

if TYPE_CHECKING:
    from charm import IdentityPlatformLoginUiFrontendCharm

logger = logging.getLogger(__name__)

Condition = Callable[["IdentityPlatformLoginUiFrontendCharm"], bool]


def leader_unit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to run an event handler or method only on the leader unit."""

    @wraps(func)
    def wrapper(charm: "IdentityPlatformLoginUiFrontendCharm", *args: Any, **kwargs: Any) -> Any:
        if not charm.unit.is_leader():
            return None
        return func(charm, *args, **kwargs)

    return wrapper


def config_is_valid(charm: "IdentityPlatformLoginUiFrontendCharm") -> bool:
    """Check whether the charm configuration is valid."""
    try:
        CharmConfig.from_dict(dict(charm.config))
        return True
    except InvalidConfigError:
        return False


def ingress_integration_exists(charm: "IdentityPlatformLoginUiFrontendCharm") -> bool:
    """Check whether at least one ingress relation (Traefik or Istio) is ready."""
    return TraefikRouteData.is_ready(charm.traefik_route) or IstioIngressRouteData.is_ready(
        charm.istio_route
    )


def bundle_is_reachable(charm: "IdentityPlatformLoginUiFrontendCharm") -> bool:
    """Check whether the configured UI bundle URL responds to an HTTP HEAD check."""
    try:
        cfg = CharmConfig.from_dict(dict(charm.config))
    except InvalidConfigError:
        return False
    if charm._bundle_reachable is None:
        charm._bundle_reachable = BundleHealthCheck.check(cfg.bundle)
    return charm._bundle_reachable


NOOP_CONDITIONS: Tuple[Condition, ...] = (
    config_is_valid,
    ingress_integration_exists,
    bundle_is_reachable,
)
