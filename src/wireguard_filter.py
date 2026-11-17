"""Common filtering rules for WireGuard interfaces."""


def is_warp_interface(interface_name):
    """Return True for internal WARP transport interfaces."""
    normalized = str(interface_name or "").strip().lower()
    return normalized == "warp" or normalized.startswith("warp-")
