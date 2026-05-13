from typing import Any, Dict, List, Set

import psutil

VPN_INTERFACE_PREFIXES: Set[str] = {
    "tun",
    "tap",
    "utun",
    "wg",
    "tailscale",
    "ipsec",
    "nordlynx",
}
MINIMUM_VPN_COUNT: int = 1


def get_active_vpn_interfaces() -> List[str]:
    """Retrieves active network interfaces that match common VPN prefixes."""
    active_vpns: List[str] = []
    interfaces: Dict[str, Any] = psutil.net_if_addrs()
    stats: Dict[str, Any] = psutil.net_if_stats()

    for interface_name in interfaces.keys():
        interface_stats: Any = stats.get(interface_name)

        if interface_stats and interface_stats.isup:
            lower_name: str = interface_name.lower()
            if any(lower_name.startswith(prefix) for prefix in VPN_INTERFACE_PREFIXES):
                active_vpns.append(interface_name)

    return active_vpns


def is_vpn_connected() -> bool:
    """Evaluates if at least one VPN interface is active."""
    return len(get_active_vpn_interfaces()) >= MINIMUM_VPN_COUNT


if __name__ == "__main__":
    is_active: bool = is_vpn_connected()
    print(f"VPN Connected: {is_active}")
