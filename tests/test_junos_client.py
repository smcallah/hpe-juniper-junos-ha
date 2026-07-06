"""Parser tests for Junos NETCONF XML."""

import sys
import types
from unittest import TestCase
from xml.etree import ElementTree as ET
import importlib.util
from pathlib import Path

if "jnpr" not in sys.modules:
    jnpr = types.ModuleType("jnpr")
    junos = types.ModuleType("jnpr.junos")
    exception = types.ModuleType("jnpr.junos.exception")

    class _Device:
        pass

    class _JunosError(Exception):
        pass

    junos.Device = _Device
    exception.ConnectAuthError = _JunosError
    exception.ConnectError = _JunosError
    exception.ConnectRefusedError = _JunosError
    exception.ConnectTimeoutError = _JunosError
    exception.RpcError = _JunosError
    sys.modules["jnpr"] = jnpr
    sys.modules["jnpr.junos"] = junos
    sys.modules["jnpr.junos.exception"] = exception

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "junos_netconf"
    / "junos_client.py"
)
PACKAGE_PATH = MODULE_PATH.parent
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(PACKAGE_PATH.parent)]
junos_netconf = types.ModuleType("custom_components.junos_netconf")
junos_netconf.__path__ = [str(PACKAGE_PATH)]
sys.modules["custom_components"] = custom_components
sys.modules["custom_components.junos_netconf"] = junos_netconf

SPEC = importlib.util.spec_from_file_location(
    "custom_components.junos_netconf.junos_client",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
junos_client = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = junos_client
SPEC.loader.exec_module(junos_client)
parse_junos_data = junos_client.parse_junos_data


ROUTE_ENGINE_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <route-engine-information xmlns="http://xml.juniper.net/junos/23.2R0/junos-chassis">
        <route-engine>
            <status>OK</status>
            <memory-system-total-util>33</memory-system-total-util>
            <cpu-idle>32</cpu-idle>
            <up-time junos:seconds="34200680">395 days, 20 hours, 11 minutes, 20 seconds</up-time>
        </route-engine>
    </route-engine-information>
</rpc-reply>
"""

SYSTEM_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <system-information>
        <hardware-model>srx320</hardware-model>
        <os-version>23.2R2.21</os-version>
        <serial-number>CW4922AN1179</serial-number>
        <host-name>banana</host-name>
    </system-information>
</rpc-reply>
"""

ALARM_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <alarm-information/>
</rpc-reply>
"""


class JunosParserTest(TestCase):
    """Tests for Junos XML parsing."""

    def test_parse_srx320_route_engine_metrics(self) -> None:
        """Parse route-engine CPU, memory, and uptime from SRX320 XML."""
        data = parse_junos_data(
            ET.fromstring(SYSTEM_XML),
            ET.fromstring(ROUTE_ENGINE_XML),
            ET.fromstring(ALARM_XML),
            fallback_host="192.0.2.1",
        )

        self.assertEqual(data.hostname, "banana")
        self.assertEqual(data.re_cpu_idle, 32)
        self.assertEqual(data.re_memory_usage, 33)
        self.assertEqual(data.uptime, "395 days, 20 hours, 11 minutes, 20 seconds")
