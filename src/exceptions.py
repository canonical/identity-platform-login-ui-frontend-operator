# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Custom exceptions for the Identity Platform Login UI Frontend operator."""


class PebbleServiceError(Exception):
    """Raised when Pebble service configuration or execution fails."""
