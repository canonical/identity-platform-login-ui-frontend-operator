# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Services management for Identity Platform Login UI Frontend charm."""

import logging
from typing import Dict

from ops.model import Container, ModelError
from ops.pebble import Layer

from constants import WORKLOAD_CONTAINER_NAME, WORKLOAD_SERVICE_NAME
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)


class PebbleService:
    """Manager for Pebble layer configuration and service lifecycle."""

    def __init__(self, container: Container) -> None:
        """Initialise Pebble service manager."""
        self._container = container

    def render_pebble_layer(self, env_vars: Dict[str, str]) -> Layer:
        """Render Pebble layer configuration for the workload container."""
        return Layer(
            {
                "summary": "login UI frontend layer",
                "description": "pebble config layer for login UI frontend",
                "services": {
                    WORKLOAD_SERVICE_NAME: {
                        "override": "replace",
                        "summary": "login UI frontend service",
                        "command": "/app/frontend",
                        "startup": "enabled",
                        "environment": env_vars,
                    }
                },
            }
        )

    def plan(self, env_vars: Dict[str, str]) -> None:
        """Update Pebble layer configuration and restart workload service if required."""
        if not self._container.can_connect():
            logger.info("Container %s not ready for connection", WORKLOAD_CONTAINER_NAME)
            return

        current_layer = self._container.get_plan()
        new_layer = self.render_pebble_layer(env_vars)

        if current_layer.services != new_layer.services:
            self._container.add_layer(WORKLOAD_CONTAINER_NAME, new_layer, combine=True)
            try:
                self._container.restart(WORKLOAD_SERVICE_NAME)
            except ModelError as exc:
                raise PebbleServiceError(
                    f"Failed to restart service {WORKLOAD_SERVICE_NAME}"
                ) from exc
