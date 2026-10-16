# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Custom exceptions for Identity Platform Login UI Frontend Operator."""


class CharmError(Exception):
    """Base exception class for charm errors."""


class InvalidConfigError(CharmError):
    """Raised when configuration is invalid or missing."""


class BundleUrlError(InvalidConfigError):
    """Raised when the S3 bundle URL is malformed or invalid."""


class IstioConfigError(InvalidConfigError):
    """Raised when Istio configuration or labels are invalid."""


class HealthCheckError(CharmError):
    """Raised when health check against S3 bundle fails."""


class KubernetesPermissionError(CharmError):
    """Raised when Kubernetes API operations fail due to missing Juju trust/permissions."""


class KubernetesResourceError(CharmError):
    """Raised when Kubernetes API operations fail due to an API error."""
