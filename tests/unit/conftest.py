# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared pytest fixtures for Scenario unit tests."""

from unittest.mock import MagicMock

import pytest
from ops.testing import Context
from pytest_mock import MockerFixture

from charm import IdentityPlatformLoginUiFrontendCharm


@pytest.fixture
def context() -> Context[IdentityPlatformLoginUiFrontendCharm]:
    """Return an ops.testing.Context for IdentityPlatformLoginUiFrontendCharm."""
    return Context(IdentityPlatformLoginUiFrontendCharm)


@pytest.fixture
def mock_bundle_reachable(mocker: MockerFixture) -> MagicMock:
    """Mock BundleHealthCheck.check to return True by default."""
    return mocker.patch("services.BundleHealthCheck.check", return_value=True)


@pytest.fixture
def mock_istio_mesh(mocker: MockerFixture) -> MagicMock:
    """Mock IstioMeshService methods to avoid Kubernetes API calls during charm tests."""
    mock = MagicMock()
    mocker.patch("charm.IstioMeshService", return_value=mock)
    return mock
