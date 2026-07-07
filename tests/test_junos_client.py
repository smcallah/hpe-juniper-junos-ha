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

FLOW_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <flow-session-information>
        <flow-session-summary>
            <active-sessions>0</active-sessions>
            <max-sessions>262144</max-sessions>
        </flow-session-summary>
    </flow-session-information>
</rpc-reply>
"""

IPSEC_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <ipsec-security-associations-information>
        <ipsec-security-associations-block>
            <sa-block-state>UP</sa-block-state>
        </ipsec-security-associations-block>
        <ipsec-security-associations-block>
            <sa-block-state>DOWN</sa-block-state>
        </ipsec-security-associations-block>
    </ipsec-security-associations-information>
</rpc-reply>
"""

CLUSTER_XML = """\
<rpc-reply xmlns:junos="http://xml.juniper.net/junos/23.2R2.21/junos">
    <chassis-cluster-status>
        <redundancy-group>
            <redundancy-group-id>0</redundancy-group-id>
            <status>primary</status>
            <primary-node>node0</primary-node>
        </redundancy-group>
    </chassis-cluster-status>
</rpc-reply>
"""

BANANA_CONFIG_XML = """\
<rpc-reply>
    <configuration>
        <version>23.2R2.21</version>
        <system>
            <host-name>banana</host-name>
            <services>
                <ssh>
                    <protocol-version>v2</protocol-version>
                    <sftp-server/>
                </ssh>
                <netconf>
                    <ssh/>
                </netconf>
                <dhcp-local-server>
                    <group>
                        <name>jdhcp-group</name>
                        <interface>irb.100</interface>
                    </group>
                </dhcp-local-server>
                <web-management>
                    <https>
                        <system-generated-certificate/>
                    </https>
                </web-management>
            </services>
        </system>
        <interfaces>
            <interface>
                <name>ge-0/0/0</name>
                <description>To: Cable Modem</description>
                <unit>
                    <name>0</name>
                    <family>
                        <inet>
                            <dhcp/>
                        </inet>
                    </family>
                </unit>
            </interface>
            <interface>
                <name>ge-0/0/1</name>
                <description>To: TP-LINK Easy Smart Switch Port 8</description>
                <unit>
                    <name>0</name>
                    <family>
                        <ethernet-switching/>
                    </family>
                </unit>
            </interface>
            <interface>
                <name>ge-0/0/7</name>
                <description>To: PoE Switch Port 6</description>
                <unit>
                    <name>0</name>
                    <family>
                        <ethernet-switching/>
                    </family>
                </unit>
            </interface>
            <interface>
                <name>dl0</name>
                <unit>
                    <name>0</name>
                    <family>
                        <inet>
                            <negotiate-address/>
                        </inet>
                    </family>
                </unit>
            </interface>
            <interface>
                <name>irb</name>
                <unit>
                    <name>100</name>
                    <family>
                        <inet>
                            <address>
                                <name>192.168.0.1/24</name>
                            </address>
                        </inet>
                    </family>
                </unit>
            </interface>
        </interfaces>
    </configuration>
</rpc-reply>
"""

INTERFACE_XML = """\
<rpc-reply>
    <interface-information>
        <physical-interface>
            <name>ge-0/0/0</name>
            <admin-status>up</admin-status>
            <oper-status>up</oper-status>
            <description>To: Cable Modem</description>
            <logical-interface>
                <name>ge-0/0/0.0</name>
                <admin-status>up</admin-status>
                <oper-status>up</oper-status>
            </logical-interface>
        </physical-interface>
        <physical-interface>
            <name>ge-0/0/1</name>
            <admin-status>up</admin-status>
            <oper-status>down</oper-status>
            <description>To: TP-LINK Easy Smart Switch Port 8</description>
            <logical-interface>
                <name>ge-0/0/1.0</name>
                <admin-status>up</admin-status>
                <oper-status>down</oper-status>
            </logical-interface>
        </physical-interface>
        <physical-interface>
            <name>irb</name>
            <admin-status>up</admin-status>
            <oper-status>up</oper-status>
            <logical-interface>
                <name>irb.100</name>
                <admin-status>up</admin-status>
                <oper-status>up</oper-status>
            </logical-interface>
        </physical-interface>
    </interface-information>
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

    def test_parse_optional_srx_metrics(self) -> None:
        """Parse optional SRX flow, IPsec, and chassis cluster metrics."""
        data = parse_junos_data(
            ET.fromstring(SYSTEM_XML),
            ET.fromstring(ROUTE_ENGINE_XML),
            ET.fromstring(ALARM_XML),
            flow_xml=ET.fromstring(FLOW_XML),
            ipsec_xml=ET.fromstring(IPSEC_XML),
            cluster_xml=ET.fromstring(CLUSTER_XML),
            fallback_host="192.0.2.1",
        )

        self.assertEqual(data.active_flow_sessions, 0)
        self.assertEqual(data.max_flow_sessions, 262144)
        self.assertEqual(data.ipsec_tunnel_count, 2)
        self.assertEqual(data.ipsec_tunnels_up, 1)
        self.assertEqual(data.ipsec_tunnels_down, 1)
        self.assertTrue(data.chassis_cluster_enabled)
        self.assertEqual(
            data.chassis_cluster_redundancy_group_status,
            "RG 0: primary, primary node0",
        )

    def test_parse_banana_configured_services_and_interfaces(self) -> None:
        """Parse service and interface model from banana's real config shape."""
        data = parse_junos_data(
            None,
            ET.fromstring(ROUTE_ENGINE_XML),
            ET.fromstring(ALARM_XML),
            config_xml=ET.fromstring(BANANA_CONFIG_XML),
            interface_xml=ET.fromstring(INTERFACE_XML),
            fallback_host="192.0.2.1",
        )

        self.assertEqual(data.hostname, "banana")
        self.assertEqual(data.model, "srx320")
        self.assertEqual(data.version, "23.2R2.21")
        self.assertEqual(
            data.system_services,
            (
                "ssh",
                "netconf_ssh",
                "dhcp_local_server",
                "web_management_https",
            ),
        )

        interfaces = {interface.name: interface for interface in data.interfaces}
        self.assertIn("ge-0/0/0", interfaces)
        self.assertIn("ge-0/0/0.0", interfaces)
        self.assertIn("ge-0/0/7", interfaces)
        self.assertIn("dl0.0", interfaces)
        self.assertIn("irb.100", interfaces)
        self.assertEqual(interfaces["ge-0/0/0"].description, "To: Cable Modem")
        self.assertTrue(interfaces["ge-0/0/0"].enabled)
        self.assertFalse(interfaces["ge-0/0/1"].enabled)
        self.assertTrue(interfaces["irb.100"].enabled)
