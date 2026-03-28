"""Tests for URL validation and SSRF prevention."""

from __future__ import annotations

import pytest

from clawwork.tools.web._validation import is_private_ip, validate_url


class TestIsPrivateIP:
    """Tests for is_private_ip function."""

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
            "127.0.0.1",
            "127.255.255.255",
            "169.254.1.1",
            "0.0.0.0",
        ],
    )
    def test_private_ipv4_addresses_detected(self, ip: str) -> None:
        """Private IPv4 addresses are correctly identified."""
        assert is_private_ip(ip) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "8.8.8.8",
            "1.1.1.1",
            "142.250.80.46",
            "151.101.1.140",
        ],
    )
    def test_public_ipv4_addresses_pass(self, ip: str) -> None:
        """Public IPv4 addresses are not flagged."""
        assert is_private_ip(ip) is False

    @pytest.mark.parametrize(
        "ip",
        [
            "::1",
            "fe80::1",
            "fc00::1",
        ],
    )
    def test_private_ipv6_addresses_detected(self, ip: str) -> None:
        """Private IPv6 addresses are correctly identified."""
        assert is_private_ip(ip) is True

    def test_ipv4_mapped_ipv6_private_detected(self) -> None:
        """IPv4-mapped IPv6 addresses with private IPs are detected."""
        assert is_private_ip("::ffff:192.168.1.1") is True
        assert is_private_ip("::ffff:127.0.0.1") is True

    def test_ipv4_mapped_ipv6_public_passes(self) -> None:
        """IPv4-mapped IPv6 addresses with public IPs pass."""
        assert is_private_ip("::ffff:8.8.8.8") is False

    def test_invalid_ip_returns_false(self) -> None:
        """Invalid IP strings return False."""
        assert is_private_ip("not-an-ip") is False
        assert is_private_ip("") is False


class TestValidateURL:
    """Tests for validate_url function."""

    def test_valid_http_url_passes(self) -> None:
        """Valid HTTP URLs pass validation."""
        assert validate_url("http://example.com/path") is None

    def test_valid_https_url_passes(self) -> None:
        """Valid HTTPS URLs pass validation."""
        assert validate_url("https://example.com/path?q=1") is None

    def test_ftp_scheme_rejected(self) -> None:
        """FTP URLs are rejected."""
        error = validate_url("ftp://example.com/file")
        assert error is not None
        assert "scheme" in error

    def test_file_scheme_rejected(self) -> None:
        """File URLs are rejected."""
        error = validate_url("file:///etc/passwd")
        assert error is not None
        assert "scheme" in error

    def test_javascript_scheme_rejected(self) -> None:
        """JavaScript URLs are rejected."""
        error = validate_url("javascript:alert(1)")
        assert error is not None
        assert "scheme" in error

    def test_localhost_blocked(self) -> None:
        """Localhost is blocked."""
        error = validate_url("http://localhost/admin")
        assert error is not None
        assert "blocked" in error.lower()

    def test_localhost_variants_blocked(self) -> None:
        """Localhost variants are blocked."""
        error = validate_url("http://localhost.localdomain/")
        assert error is not None
        assert "blocked" in error.lower()

    def test_private_ip_in_url_rejected(self) -> None:
        """Private IPs in URL are rejected."""
        error = validate_url("http://192.168.1.1/admin")
        assert error is not None
        assert "private" in error.lower()

    def test_loopback_ip_rejected(self) -> None:
        """Loopback IPs are rejected."""
        error = validate_url("http://127.0.0.1:8080/")
        assert error is not None
        assert "private" in error.lower()

    def test_url_without_host_rejected(self) -> None:
        """URLs without hostname are rejected."""
        error = validate_url("http:///path")
        assert error is not None
        assert "hostname" in error.lower()
