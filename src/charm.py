#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the service."""

import logging

import ops
from charmlibs.interfaces.istio_ingress_route import IstioIngressRouteRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from config import CharmConfig
from constants import ISTIO_INTEGRATION_NAME, TRAEFIK_INTEGRATION_NAME
from exceptions import (
    InvalidConfigError,
    KubernetesPermissionError,
    KubernetesResourceError,
)
from integrations import IstioIngressRouteData, TraefikRouteData
from services import BundleHealthCheck, IstioMeshService
from utils import NOOP_CONDITIONS, leader_unit

logger = logging.getLogger(__name__)


class IdentityPlatformLoginUiFrontendCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self.traefik_route = TraefikRouteRequirer(
            self,
            self.model.get_relation(TRAEFIK_INTEGRATION_NAME),
            TRAEFIK_INTEGRATION_NAME,
            raw=True,
        )
        self.istio_route = IstioIngressRouteRequirer(
            self,
            relation_name=ISTIO_INTEGRATION_NAME,
        )
        self.istio_mesh = IstioMeshService(
            app_name=self.app.name,
            namespace=self.model.name,
        )
        self._breaking_relations: set[str] = set()
        self._bundle_reachable: bool | None = None
        self._istio_reconcile_error: Exception | None = None

        # Lifecycle events
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.leader_elected, self._on_leader_elected)
        framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        framework.observe(self.on.update_status, self._on_update_status)
        framework.observe(self.on.remove, self._on_remove)

        # Traefik ingress relation events
        framework.observe(
            self.on[TRAEFIK_INTEGRATION_NAME].relation_joined,
            self._on_ingress_changed,
        )
        framework.observe(
            self.on[TRAEFIK_INTEGRATION_NAME].relation_changed,
            self._on_ingress_changed,
        )
        framework.observe(
            self.on[TRAEFIK_INTEGRATION_NAME].relation_broken,
            self._on_ingress_changed,
        )

        # Istio ingress relation events
        framework.observe(
            self.on[ISTIO_INTEGRATION_NAME].relation_joined,
            self._on_ingress_changed,
        )
        framework.observe(
            self.on[ISTIO_INTEGRATION_NAME].relation_changed,
            self._on_ingress_changed,
        )
        framework.observe(
            self.on[ISTIO_INTEGRATION_NAME].relation_broken,
            self._on_istio_ingress_broken,
        )

        # Holistic status evaluation
        framework.observe(self.on.collect_unit_status, self._on_collect_status)

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_leader_elected(self, event: ops.LeaderElectedEvent) -> None:
        self._holistic_handler(event)

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent) -> None:
        self._holistic_handler(event)

    def _on_update_status(self, event: ops.UpdateStatusEvent) -> None:
        self._holistic_handler(event)

    def _on_remove(self, event: ops.RemoveEvent) -> None:
        """Clean up Istio Kubernetes resources when the charm is removed."""
        self._cleanup_istio_mesh()

    def _on_ingress_changed(self, event: ops.RelationEvent) -> None:
        if isinstance(event, ops.RelationBrokenEvent):
            self._breaking_relations.add(event.relation.name)
        self._holistic_handler(event)

    def _on_istio_ingress_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Clean up Istio Kubernetes resources when the Istio ingress relation is removed."""
        self._breaking_relations.add(ISTIO_INTEGRATION_NAME)
        self._cleanup_istio_mesh()
        self._holistic_handler(event)

    @leader_unit
    def _cleanup_istio_mesh(self) -> None:
        """Delete Istio Kubernetes resources managed by this charm."""
        istio_ns = str(self.config.get("istio-resources-namespace", "")).strip()
        try:
            self.istio_mesh.cleanup(istio_resources_namespace=istio_ns)
        except (KubernetesPermissionError, KubernetesResourceError) as exc:
            logger.warning("Failed to clean up Istio resources: %s", exc)

    @leader_unit
    def _holistic_handler(self, event: ops.EventBase) -> None:
        """Holistically reconcile ingress relations and Istio mesh resources."""
        if not all(condition(self) for condition in NOOP_CONDITIONS):
            return

        self.unit.status = MaintenanceStatus("Configuring ingress resources")
        charm_config = CharmConfig.from_dict(dict(self.config))

        if TraefikRouteData.is_ready(self.traefik_route):
            traefik_data = TraefikRouteData.load(self.traefik_route, charm_config.bundle)
            self.traefik_route.submit_to_traefik(config=traefik_data.config)

        if IstioIngressRouteData.is_ready(self.istio_route):
            try:
                self.istio_mesh.reconcile(charm_config)
                self._istio_reconcile_error = None
            except (KubernetesPermissionError, KubernetesResourceError) as exc:
                self._istio_reconcile_error = exc
                return
            istio_data = IstioIngressRouteData.load(
                self.istio_route,
                charm_config=charm_config,
                app_name=self.app.name,
                model_name=self.model.name,
            )
            self.istio_route.submit_config(istio_data.config)

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        """Evaluate and set the unit status deterministically."""
        try:
            charm_config = CharmConfig.from_dict(dict(self.config))
        except InvalidConfigError as exc:
            event.add_status(BlockedStatus(str(exc)))
            return

        traefik_ready = TraefikRouteData.is_ready(self.traefik_route)
        istio_ready = IstioIngressRouteData.is_ready(self.istio_route)

        if not traefik_ready and not istio_ready:
            event.add_status(WaitingStatus("Waiting for ingress integration"))
            return

        if self._bundle_reachable is None:
            self._bundle_reachable = BundleHealthCheck.check(charm_config.bundle)

        if not self._bundle_reachable:
            event.add_status(
                BlockedStatus(f"Cannot reach UI bundle at {charm_config.bundle.get_index_url()}")
            )
            return

        if istio_ready and self._istio_reconcile_error is not None:
            event.add_status(BlockedStatus(str(self._istio_reconcile_error)))
            return

        event.add_status(ActiveStatus())


if __name__ == "__main__":  # pragma: nocover
    ops.main(IdentityPlatformLoginUiFrontendCharm)
