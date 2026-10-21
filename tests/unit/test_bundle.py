# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for bundle.py."""

import pytest

from bundle import BundleUrl
from exceptions import BundleUrlError


class TestBundleUrl:
    """Tests for BundleUrl parsing and validation."""

    def test_bundle_url_standard(self) -> None:
        """Test standard S3 bundle URL splitting."""
        url = "https://s3.example.com/dist"
        b = BundleUrl.parse(url)
        assert b.origin == "https://s3.example.com"
        assert b.hostname == "s3.example.com"
        assert b.port == 443
        assert b.base_path == "/dist"
        assert b.get_index_url() == "https://s3.example.com/dist/index.html"

    def test_bundle_url_custom_port(self) -> None:
        """Test S3 bundle URL with a custom HTTPS port."""
        url = "https://minio.example.com:9000/ui-bucket/v1/"
        b = BundleUrl.parse(url)
        assert b.origin == "https://minio.example.com:9000"
        assert b.hostname == "minio.example.com"
        assert b.port == 9000
        assert b.base_path == "/ui-bucket/v1"
        assert b.get_index_url() == "https://minio.example.com:9000/ui-bucket/v1/index.html"

    def test_bundle_url_swift(self) -> None:
        """Test Swift S3 bundle URL splitting."""
        url = "https://s3.example.com/swift/v1/AUTH_123/bucket"
        b = BundleUrl.parse(url)
        assert b.origin == "https://s3.example.com"
        assert b.hostname == "s3.example.com"
        assert b.port == 443
        assert b.base_path == "/swift/v1/AUTH_123/bucket"
        assert b.get_index_url() == "https://s3.example.com/swift/v1/AUTH_123/bucket/index.html"

    def test_bundle_url_root(self) -> None:
        """Test root S3 bucket URL."""
        url = "https://mybucket.s3.amazonaws.com"
        b = BundleUrl.parse(url)
        assert b.origin == "https://mybucket.s3.amazonaws.com"
        assert b.hostname == "mybucket.s3.amazonaws.com"
        assert b.port == 443
        assert b.base_path == ""
        assert b.get_index_url() == "https://mybucket.s3.amazonaws.com/index.html"

    def test_bundle_url_empty(self) -> None:
        """Test empty URL raises BundleUrlError."""
        with pytest.raises(BundleUrlError, match="cannot be empty"):
            BundleUrl.parse("   ")

    def test_bundle_url_invalid_scheme(self) -> None:
        """Test HTTP scheme raises BundleUrlError."""
        with pytest.raises(BundleUrlError, match="https://"):
            BundleUrl.parse("http://s3.example.com/dist")

    def test_bundle_url_with_credentials(self) -> None:
        """Test URL with credentials raises BundleUrlError."""
        with pytest.raises(BundleUrlError, match="credentials"):
            BundleUrl.parse("https://user:pass@s3.example.com/dist")

    def test_bundle_url_with_query(self) -> None:
        """Test URL with query string raises BundleUrlError."""
        with pytest.raises(BundleUrlError, match="query"):
            BundleUrl.parse("https://s3.example.com/dist?v=1")
