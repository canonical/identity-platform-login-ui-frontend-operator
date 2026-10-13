# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test configuration for Identity Platform Login UI Frontend operator."""

import ops.testing
import pytest
from pytest_mock import MockerFixture

from charm import IdentityPlatformLoginUiFrontendOperatorCharm
from constants import WORKLOAD_CONTAINER_NAME


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    """Mock Kubernetes compute resources patch calls."""
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def context() -> ops.testing.Context:
    """Initialise ops testing Context with Charm."""
    return ops.testing.Context(IdentityPlatformLoginUiFrontendOperatorCharm)


@pytest.fixture
def container_can_connect() -> ops.testing.Container:
    """Workload container in connectable state."""
    return ops.testing.Container(
        name=WORKLOAD_CONTAINER_NAME,
        can_connect=True,
    )


@pytest.fixture
def container_cannot_connect() -> ops.testing.Container:
    """Workload container in non-connectable state."""
    return ops.testing.Container(
        name=WORKLOAD_CONTAINER_NAME,
        can_connect=False,
    )


def create_state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    container: ops.testing.Container | None = None,
    relations: list[ops.testing.Relation] | None = None,
) -> ops.testing.State:
    """Factory function to create charm state.

    Args:
        leader: Whether this unit is the leader.
        can_connect: Whether the workload container can connect.
        container: Custom container to use.
        relations: List of relations to include in state.
    """
    if container is None:
        container = ops.testing.Container(
            name=WORKLOAD_CONTAINER_NAME,
            can_connect=can_connect,
        )

    return ops.testing.State(
        leader=leader,
        containers=[container],
        relations=relations or [],
    )
