# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scenario-based unit tests for IdentityPlatformLoginUiFrontendCharm."""

from unittest.mock import MagicMock

import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Context, Relation, State

from charm import IdentityPlatformLoginUiFrontendCharm
from constants import ISTIO_INTEGRATION_NAME, TRAEFIK_INTEGRATION_NAME
from exceptions import KubernetesPermissionError, KubernetesResourceError


class TestConfigChangedEvent:
    """Tests for the config_changed lifecycle event."""

    def test_missing_bundle_url_blocks_unit(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that missing ui-bundle-url puts the unit into BlockedStatus."""
        state = State(leader=True, config={})
        out = context.run(context.on.config_changed(), state)
        assert isinstance(out.unit_status, BlockedStatus)
        assert "ui-bundle-url" in out.unit_status.message
        mock_istio_mesh.reconcile.assert_not_called()

    def test_valid_config_without_ingress_waits(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that valid config without any ingress relation puts the unit into WaitingStatus."""
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
        )
        out = context.run(context.on.config_changed(), state)
        assert out.unit_status == WaitingStatus("Waiting for ingress integration")
        mock_istio_mesh.reconcile.assert_not_called()

    def test_unreachable_bundle_blocks_unit(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that an unreachable bundle URL puts the unit into BlockedStatus."""
        mock_bundle_reachable.return_value = False
        traefik_rel = Relation(
            endpoint=TRAEFIK_INTEGRATION_NAME,
            interface="traefik_route",
            remote_app_name="traefik",
            remote_app_data={"external_host": "auth.example.com", "scheme": "https"},
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
            relations=[traefik_rel],
        )
        out = context.run(context.on.config_changed(), state)
        assert isinstance(out.unit_status, BlockedStatus)
        assert "Cannot reach UI bundle" in out.unit_status.message


class TestTraefikIngressEvents:
    """Tests for traefik-ingress relation events."""

    def test_traefik_relation_submits_raw_config_and_becomes_active(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that joining traefik-ingress publishes the rendered Traefik config."""
        traefik_rel = Relation(
            endpoint=TRAEFIK_INTEGRATION_NAME,
            interface="traefik_route",
            remote_app_name="traefik",
            remote_app_data={"external_host": "auth.example.com", "scheme": "https"},
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
            relations=[traefik_rel],
        )
        out = context.run(context.on.relation_changed(traefik_rel), state)
        assert out.unit_status == ActiveStatus()

        updated_rel = out.get_relation(traefik_rel.id)
        assert updated_rel.local_app_data.get("raw") == "True"
        raw_cfg = yaml.safe_load(updated_rel.local_app_data["config"])
        assert "http" in raw_cfg
        mock_istio_mesh.reconcile.assert_not_called()

    def test_traefik_relation_broken_transitions_to_waiting(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that breaking traefik-ingress transitions the unit to WaitingStatus."""
        traefik_rel = Relation(
            endpoint=TRAEFIK_INTEGRATION_NAME,
            interface="traefik_route",
            remote_app_name="traefik",
            remote_app_data={"external_host": "auth.example.com", "scheme": "https"},
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
            relations=[traefik_rel],
        )
        out = context.run(context.on.relation_broken(traefik_rel), state)
        assert out.unit_status == WaitingStatus("Waiting for ingress integration")


class TestIstioIngressEvents:
    """Tests for istio-ingress relation events."""

    def test_istio_relation_reconciles_mesh_and_submits_routes(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that istio-ingress relation reconciles IstioMeshService and publishes routes."""
        istio_rel = Relation(
            endpoint=ISTIO_INTEGRATION_NAME,
            interface="istio_ingress_route",
            remote_app_name="istio-ingress",
            remote_app_data={"external_host": "auth.example.com", "tls_enabled": "false"},
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com:8443/dist"},
            relations=[istio_rel],
        )
        out = context.run(context.on.relation_changed(istio_rel), state)
        assert out.unit_status == ActiveStatus()
        mock_istio_mesh.reconcile.assert_called_once()
        mock_bundle_reachable.assert_called_once()

        updated_rel = out.get_relation(istio_rel.id)
        assert "config" in updated_rel.local_app_data

    def test_istio_relation_broken_cleans_up_mesh_resources(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test breaking istio-ingress cleans up mesh resources and transitions to Waiting."""
        istio_rel = Relation(
            endpoint=ISTIO_INTEGRATION_NAME,
            interface="istio_ingress_route",
            remote_app_name="istio-ingress",
            remote_app_data={"external_host": "auth.example.com", "tls_enabled": "false"},
        )
        state = State(
            leader=True,
            config={
                "ui-bundle-url": "https://s3.example.com/dist",
                "istio-resources-namespace": "istio-system",
            },
            relations=[istio_rel],
        )
        out = context.run(context.on.relation_broken(istio_rel), state)
        mock_istio_mesh.cleanup.assert_called_once_with(istio_resources_namespace="istio-system")
        mock_istio_mesh.reconcile.assert_not_called()
        assert out.unit_status == WaitingStatus("Waiting for ingress integration")

    def test_remove_event_cleans_up_mesh_resources(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test removing the charm cleans up Istio mesh resources on the leader unit."""
        istio_rel = Relation(
            endpoint=ISTIO_INTEGRATION_NAME,
            interface="istio_ingress_route",
            remote_app_name="istio-ingress",
            remote_app_data={"external_host": "auth.example.com", "tls_enabled": "false"},
        )
        state = State(
            leader=True,
            config={
                "ui-bundle-url": "https://s3.example.com/dist",
                "istio-resources-namespace": "istio-system",
            },
            relations=[istio_rel],
        )
        context.run(context.on.remove(), state)
        mock_istio_mesh.cleanup.assert_called_once_with(istio_resources_namespace="istio-system")
        mock_istio_mesh.reconcile.assert_not_called()


class TestCollectStatusEvent:
    """Tests for holistic status evaluation via collect_unit_status."""

    def test_rbac_permission_error_blocks_unit(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that KubernetesPermissionError reports BlockedStatus."""
        mock_istio_mesh.reconcile.side_effect = KubernetesPermissionError(
            "Missing RBAC permissions to manage Istio resources (try `juju trust`)."
        )
        istio_rel = Relation(
            endpoint=ISTIO_INTEGRATION_NAME,
            interface="istio_ingress_route",
            remote_app_name="istio-ingress",
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
            relations=[istio_rel],
        )
        out = context.run(context.on.relation_changed(istio_rel), state)
        assert isinstance(out.unit_status, BlockedStatus)
        assert "RBAC" in out.unit_status.message

    def test_k8s_resource_error_blocks_unit(
        self,
        context: Context[IdentityPlatformLoginUiFrontendCharm],
        mock_bundle_reachable: MagicMock,
        mock_istio_mesh: MagicMock,
    ) -> None:
        """Test that KubernetesResourceError reports BlockedStatus."""
        mock_istio_mesh.reconcile.side_effect = KubernetesResourceError(
            "Failed to apply Istio resource: webhook error"
        )
        istio_rel = Relation(
            endpoint=ISTIO_INTEGRATION_NAME,
            interface="istio_ingress_route",
            remote_app_name="istio-ingress",
        )
        state = State(
            leader=True,
            config={"ui-bundle-url": "https://s3.example.com/dist"},
            relations=[istio_rel],
        )
        out = context.run(context.on.relation_changed(istio_rel), state)
        assert isinstance(out.unit_status, BlockedStatus)
        assert "Failed to apply Istio resource" in out.unit_status.message
