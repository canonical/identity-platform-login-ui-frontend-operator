#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for Identity Platform Login UI Frontend."""

import logging

from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops import (
    ActiveStatus,
    BlockedStatus,
    CharmBase,
    CollectStatusEvent,
    ConfigChangedEvent,
    PebbleReadyEvent,
    WaitingStatus,
    main,
)

from constants import (
    APPLICATION_PORT,
    GRAFANA_INTEGRATION_NAME,
    INGRESS_INTEGRATION_NAME,
    LOGGING_INTEGRATION_NAME,
    METRICS_INTEGRATION_NAME,
    TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER_NAME,
)
from exceptions import PebbleServiceError
from services import PebbleService

logger = logging.getLogger(__name__)


class IdentityPlatformLoginUiFrontendOperatorCharm(CharmBase):
    """Charmed Identity Platform Login UI Frontend operator."""

    def __init__(self, *args):
        """Initialise Charm."""
        super().__init__(*args)

        self.container = self.unit.get_container(WORKLOAD_CONTAINER_NAME)
        self._pebble_service = PebbleService(self.container)

        # Observability integrations
        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)
        self._tracing = TracingEndpointRequirer(self, relation_name=TRACING_INTEGRATION_NAME)
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=METRICS_INTEGRATION_NAME,
            jobs=[{"static_configs": [{"targets": [f"*:{APPLICATION_PORT}"]}]}],
        )
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_INTEGRATION_NAME
        )

        # Ingress integration
        self._ingress = IngressPerAppRequirer(
            self,
            relation_name=INGRESS_INTEGRATION_NAME,
            port=APPLICATION_PORT,
        )

        # Kubernetes compute resources patch
        self._resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER_NAME,
            resource_reqs_func=lambda: ResourceRequirements(),
        )

        # Event observers
        self.framework.observe(
            self.on[WORKLOAD_CONTAINER_NAME].pebble_ready, self._on_pebble_ready
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Handle pebble ready event."""
        self._configure_charm()

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle config changed event."""
        self._configure_charm()

    def _configure_charm(self) -> None:
        """Configure and start the workload service."""
        if not self.container.can_connect():
            return

        env_vars = {
            "LOG_LEVEL": str(self.config.get("log_level", "info")),
            "PORT": str(APPLICATION_PORT),
        }

        try:
            self._pebble_service.plan(env_vars)
        except PebbleServiceError as exc:
            logger.error("Failed to configure Pebble service: %s", exc)

    def _on_collect_unit_status(self, event: CollectStatusEvent) -> None:
        """Evaluate and report unit status declaratively."""
        if not self.container.can_connect():
            event.add_status(WaitingStatus("Waiting for workload container"))
            return

        env_vars = {
            "LOG_LEVEL": str(self.config.get("log_level", "info")),
            "PORT": str(APPLICATION_PORT),
        }

        try:
            self._pebble_service.plan(env_vars)
        except PebbleServiceError:
            event.add_status(BlockedStatus("Failed to configure Pebble service"))
            return

        event.add_status(ActiveStatus())


if __name__ == "__main__":  # pragma: nocover
    main(IdentityPlatformLoginUiFrontendOperatorCharm)
