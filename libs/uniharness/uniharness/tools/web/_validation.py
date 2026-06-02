"""URL validation for SSRF prevention.

Provides blocklist-based URL validation to prevent access to private networks.
"""

from __future__ import annotations

import ipaddress
from typing import Final
from urllib.parse import urlparse

# Private/reserved IP ranges to block
PRIVATE_RANGES: Final[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = (
    # IPv4 private ranges
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("0.0.0.0/8"),
    # IPv6 private ranges
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
)

# Hostnames to block
BLOCKED_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
    }
)


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal.

    Args:
        ip_str: IP address string to check.

    Returns:
        True if the IP is private/internal, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Handle IPv4-mapped IPv6 addresses
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_private_ip(str(ip.ipv4_mapped))

    return any(ip in network for network in PRIVATE_RANGES)


def validate_url(url: str) -> str | None:
    """Validate URL for security.

    Checks:
    - Scheme is HTTP or HTTPS
    - Hostname is present
    - Hostname is not in blocklist
    - Hostname (if IP) is not a private address

    Args:
        url: The URL to validate.

    Returns:
        None if valid, error message string if invalid.
    """
    try:
        parsed = urlparse(url)
    except ValueError as e:
        return f"Invalid URL format: {e}"

    # Check scheme
    if parsed.scheme.lower() not in ("http", "https"):
        return f"Invalid URL: scheme '{parsed.scheme}' not allowed. Use http:// or https://"

    # Check hostname
    if not parsed.hostname:
        return "Invalid URL: missing hostname."

    hostname = parsed.hostname.lower()

    # Check blocklist
    if hostname in BLOCKED_HOSTS:
        return f"Invalid URL: access to '{hostname}' is blocked."

    # Check if hostname is a private IP
    if is_private_ip(hostname):
        return "Invalid URL: access to private/internal IP addresses is blocked."

    return None
