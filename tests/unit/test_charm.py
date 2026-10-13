# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Identity Platform Login UI Frontend operator."""

from conftest import create_state
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Context

from constants import WORKLOAD_CONTAINER_NAME


def test_pebble_ready(context: Context):
    """Test pebble ready event sets active status when container is ready."""
    state_in = create_state(can_connect=True)
    container = state_in.get_container(WORKLOAD_CONTAINER_NAME)
    state_out = context.run(context.on.pebble_ready(container), state_in)
    assert state_out.unit_status == ActiveStatus()


def test_container_cannot_connect(context: Context):
    """Test status is waiting when container cannot connect."""
    state_in = create_state(can_connect=False)
    state_out = context.run(context.on.config_changed(), state_in)
    assert state_out.unit_status == WaitingStatus("Waiting for workload container")
