"""Probe Junos NETCONF with the same PyEZ library used by Home Assistant.

Run this from the Home Assistant host/container after installing junos-eznc:

    python3 probe_junos_pyez.py --host 192.0.2.10 --user ha-monitor
"""

from __future__ import annotations

import argparse
from getpass import getpass
import logging

from jnpr.junos import Device


def main() -> int:
    """Run a read-only PyEZ NETCONF probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=830)
    parser.add_argument("--user", required=True)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--verify-hostkey", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    password = getpass("Password: ")
    dev = Device(
        host=args.host,
        port=args.port,
        user=args.user,
        passwd=password,
        conn_open_timeout=args.timeout,
        timeout=args.timeout,
        gather_facts=False,
        allow_agent=False,
        look_for_keys=False,
        hostkey_verify=args.verify_hostkey,
    )

    try:
        print(f"Opening NETCONF session to {args.host}:{args.port} as {args.user}")
        dev.open()
        print("Connected. Running get-system-information...")
        system_xml = dev.rpc.get_system_information()
        hostname = system_xml.findtext(".//host-name")
        version = system_xml.findtext(".//os-version")
        print(f"hostname={hostname!r} version={version!r}")
        return 0
    except Exception as err:  # Diagnostic script: show the exact transport failure.
        original = getattr(err, "_orig", None)
        print(f"FAILED: {err.__class__.__name__}: {err}")
        if original is not None:
            print(f"ORIGINAL: {original.__class__.__name__}: {original}")
        return 1
    finally:
        try:
            dev.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
