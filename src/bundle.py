# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""S3 bundle URL parsing and URL mapping utility."""

from dataclasses import dataclass
from urllib.parse import urlparse

from constants import HEALTH_CHECK_PATH
from exceptions import BundleUrlError


@dataclass(frozen=True, slots=True)
class BundleUrl:
    """Parsed S3 bundle URL components."""

    origin: str
    base_path: str
    full_url: str
    hostname: str = ""
    port: int = 443

    @classmethod
    def parse(cls, url: str) -> "BundleUrl":
        """Parse S3 bundle URL into origin, hostname, port, and base path."""
        url_str = url.strip()
        if not url_str:
            raise BundleUrlError("Option 'ui-bundle-url' cannot be empty.")

        parsed = urlparse(url_str)

        if parsed.scheme != "https":
            raise BundleUrlError(f"URL '{url_str}' must use 'https://' scheme.")

        if not parsed.hostname:
            raise BundleUrlError(f"URL '{url_str}' has no valid hostname.")

        if parsed.username or parsed.password:
            raise BundleUrlError("URL 'ui-bundle-url' must not contain credentials.")

        if parsed.query or parsed.fragment:
            raise BundleUrlError(
                "URL 'ui-bundle-url' must not contain query parameters or fragments."
            )

        try:
            raw_port = parsed.port
        except ValueError as e:
            raise BundleUrlError(f"URL '{url_str}' has an invalid port.") from e

        port = raw_port or 443

        # Reconstruct origin (scheme://netloc)
        port_suffix = f":{raw_port}" if raw_port and raw_port not in (80, 443) else ""
        origin = f"https://{parsed.hostname}{port_suffix}"

        # Clean base_path
        path = parsed.path.rstrip("/")
        if not path:
            base_path = ""
        else:
            base_path = path if path.startswith("/") else f"/{path}"

        return cls(
            origin=origin,
            base_path=base_path,
            full_url=url_str,
            hostname=parsed.hostname,
            port=port,
        )

    def get_index_url(self) -> str:
        """Return full HTTPS URL to HEAD health check target (/index.html)."""
        if self.base_path:
            return f"{self.origin}{self.base_path}{HEALTH_CHECK_PATH}"
        return f"{self.origin}{HEALTH_CHECK_PATH}"
