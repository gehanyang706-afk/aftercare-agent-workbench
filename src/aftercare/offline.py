"""Process-wide offline guard installed only by an explicit CLI entrypoint.

The audit hook covers Python socket connections, including SDKs. It is not an OS
sandbox. No subprocess-based inference or inference SDK is exposed in phase 0.
"""

import ipaddress
import socket
import sys


def is_loopback(host: object) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


def install_offline_guard() -> None:
    def audit(event: str, args: tuple) -> None:
        if event == "socket.getaddrinfo" and not is_loopback(args[0]):
            raise PermissionError("OFFLINE_EGRESS_DENIED")
        if event == "socket.connect":
            sock, address = args
            if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(address[0]):
                raise PermissionError("OFFLINE_EGRESS_DENIED")
        if event == "socket.sendto":
            sock, address = args
            if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(address[0]):
                raise PermissionError("OFFLINE_EGRESS_DENIED")

    sys.addaudithook(audit)
