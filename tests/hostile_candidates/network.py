# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: open an outbound TCP connection (DNS server and the Docker host)."""
import socket


def control(obs, state):
    s = socket.create_connection(("1.1.1.1", 53), timeout=1.0)
    s.close()
    return 1.0, state
