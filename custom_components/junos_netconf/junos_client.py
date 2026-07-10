"""Read-only PyEZ client and XML parsing for Junos NETCONF."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from jnpr.junos import Device
from jnpr.junos.exception import (
    ConnectAuthError,
    ConnectError,
    ConnectRefusedError,
    ConnectTimeoutError,
    RpcError,
)
from lxml import etree

from .exceptions import JunosNetconfAuthError, JunosNetconfConnectionError

_LOGGER = logging.getLogger(__name__)

INTERNAL_INTERFACE_PREFIXES = (
    "lo0",
    "jsrv",
    "dsc",
    "gre",
    "ipip",
    "mtun",
    "pimd",
    "pime",
    "tap",
    "vlan",
    "irb",
    "lsi",
    "pp",
    "demux",
    "pfe",
    "pfh",
    "cbp",
    "em",
    "fxp",
    "mt",
    "sp",
    "fab",
    "rbeb",
)


def _configuration_filter(interface_allowlist: tuple[str, ...]) -> Any:
    """Build a narrow NETCONF subtree filter for configuration-derived state."""
    configuration = etree.Element("configuration")
    system = etree.SubElement(configuration, "system")
    etree.SubElement(system, "host-name")
    etree.SubElement(system, "services")

    selected_interfaces: dict[str, set[str] | None] = {}
    for interface_name in interface_allowlist:
        physical_name, separator, unit_name = interface_name.partition(".")
        if not separator:
            selected_interfaces[physical_name] = None
        elif physical_name not in selected_interfaces:
            selected_interfaces[physical_name] = {unit_name}
        elif selected_interfaces[physical_name] is not None:
            selected_interfaces[physical_name].add(unit_name)

    if selected_interfaces:
        interfaces = etree.SubElement(configuration, "interfaces")
        for physical_name, units in selected_interfaces.items():
            interface = etree.SubElement(interfaces, "interface")
            etree.SubElement(interface, "name").text = physical_name
            if units is not None:
                for unit_name in sorted(units):
                    unit = etree.SubElement(interface, "unit")
                    etree.SubElement(unit, "name").text = unit_name

    return configuration


@dataclass(frozen=True)
class JunosData:
    """Parsed read-only Junos state used by Home Assistant entities."""

    hostname: str | None
    model: str | None
    serial_number: str | None
    version: str | None
    uptime: str | None
    re_cpu_idle: int | None
    re_memory_usage: int | None
    chassis_alarm_count: int | None
    active_flow_sessions: int | None
    max_flow_sessions: int | None
    ipsec_tunnel_count: int | None
    ipsec_tunnels_up: int | None
    ipsec_tunnels_down: int | None
    chassis_cluster_enabled: bool | None
    chassis_cluster_redundancy_group_status: str | None
    system_services: tuple[str, ...] | None
    interfaces: tuple[JunosInterfaceState, ...]


@dataclass(frozen=True)
class JunosInterfaceState:
    """Parsed configured and operational interface state."""

    name: str
    description: str | None
    admin_status: str | None
    oper_status: str | None
    enabled: bool | None
    rx_mbps: float | None
    tx_mbps: float | None
    input_errors: int | None
    output_errors: int | None


@dataclass(frozen=True)
class IpsecTunnelCounts:
    """Parsed IPsec tunnel totals."""

    total: int | None
    up: int | None
    down: int | None


class JunosPyEzClient:
    """Small blocking PyEZ client for read-only operational RPCs."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: int,
        verify_hostkey: bool,
        interface_allowlist: tuple[str, ...] = (),
    ) -> None:
        """Store connection settings."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify_hostkey = verify_hostkey
        self.interface_allowlist = interface_allowlist

    def get_data(self) -> JunosData:
        """Open a NETCONF session, collect read-only data, and close it."""
        dev = self._device()
        try:
            _LOGGER.debug("Opening Junos NETCONF session to %s:%s", self.host, self.port)
            dev.open()
            system_xml = self._required_rpc(
                dev,
                "get-system-information",
                "get_system_information",
            )
            uptime_xml = self._optional_rpc(
                dev,
                "get-system-uptime-information",
                "get_system_uptime_information",
            )
            re_xml = self._required_rpc(
                dev,
                "get-route-engine-information",
                "get_route_engine_information",
            )
            alarm_xml = self._required_rpc(
                dev,
                "get-alarm-information",
                "get_alarm_information",
            )
            flow_xml = self._optional_rpc(
                dev,
                "get-flow-session-information",
                "get_flow_session_information",
                summary=True,
            )
            ipsec_xml = self._optional_rpc(
                dev,
                "get-ipsec-security-associations-information",
                "get_ipsec_security_associations_information",
            )
            cluster_xml = self._optional_rpc(
                dev,
                "get-chassis-cluster-status",
                "get_chassis_cluster_status",
            )
            config_xml = self._configuration_information(dev)
            interface_xml = self._interface_information(dev)
            data = parse_junos_data(
                system_xml,
                re_xml,
                alarm_xml,
                uptime_xml=uptime_xml,
                flow_xml=flow_xml,
                ipsec_xml=ipsec_xml,
                cluster_xml=cluster_xml,
                config_xml=config_xml,
                interface_xml=interface_xml,
                interface_allowlist=self.interface_allowlist,
                fallback_host=self.host,
            )
            self._validate_allowlisted_interfaces(data.interfaces)
            _log_missing_metrics(data, re_xml, uptime_xml)
            return data
        except ConnectAuthError as err:
            raise JunosNetconfAuthError("NETCONF authentication failed") from err
        except (ConnectError, ConnectRefusedError, ConnectTimeoutError, RpcError) as err:
            message = _exception_message(err)
            _LOGGER.warning("Junos NETCONF connection failed: %s", message)
            raise JunosNetconfConnectionError(message) from err
        except OSError as err:
            message = _exception_message(err)
            _LOGGER.warning("Junos NETCONF socket failure: %s", message)
            raise JunosNetconfConnectionError(message) from err
        finally:
            self._close(dev)

    def _device(self) -> Device:
        """Build a PyEZ Device object without enabling write/config actions."""
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "passwd": self.password,
            "conn_open_timeout": self.timeout,
            "timeout": self.timeout,
            "gather_facts": False,
            "allow_agent": False,
            "look_for_keys": False,
        }

        kwargs["hostkey_verify"] = self.verify_hostkey
        try:
            return Device(**kwargs)
        except TypeError:
            kwargs.pop("hostkey_verify")
            _LOGGER.debug("PyEZ Device does not accept hostkey_verify directly")
            return Device(**kwargs)

    def _optional_rpc(
        self,
        dev: Device,
        rpc_name: str,
        method_name: str,
        **kwargs: Any,
    ) -> Any | None:
        """Run an optional read-only RPC without failing the whole poll."""
        try:
            rpc_call = getattr(dev.rpc, method_name)
            return rpc_call(**kwargs)
        except (AttributeError, RpcError) as err:
            _LOGGER.debug("Optional Junos RPC %s failed: %s", rpc_name, err)
            return None

    def _required_rpc(
        self,
        dev: Device,
        rpc_name: str,
        method_name: str,
        **kwargs: Any,
    ) -> Any:
        """Run a required RPC and surface permission/support errors to HA."""
        try:
            rpc_call = getattr(dev.rpc, method_name)
            return rpc_call(**kwargs)
        except (AttributeError, RpcError) as err:
            raise JunosNetconfConnectionError(
                f"Required Junos RPC {rpc_name} failed: {err}"
            ) from err

    def _configuration_information(self, dev: Device) -> Any | None:
        """Fetch the small committed configuration subset for this poll."""
        return self._optional_rpc(
            dev,
            "get-configuration (filtered)",
            "get_config",
            filter_xml=_configuration_filter(self.interface_allowlist),
            options={"database": "committed"},
        )

    def _interface_information(self, dev: Device) -> tuple[Any, ...]:
        """Return detailed interface XML only for allowlisted interfaces."""
        replies: list[Any] = []
        for interface_name in self.interface_allowlist:
            reply = self._required_rpc(
                dev,
                f"get-interface-information {interface_name}",
                "get_interface_information",
                interface_name=interface_name,
                extensive=True,
            )
            replies.append(reply)
        return tuple(replies)

    def _validate_allowlisted_interfaces(
        self,
        interfaces: tuple[JunosInterfaceState, ...],
    ) -> None:
        """Fail clearly when an explicitly requested interface returned no data."""
        returned_names = {interface.name for interface in interfaces}
        missing_names = sorted(set(self.interface_allowlist) - returned_names)
        if missing_names:
            raise JunosNetconfConnectionError(
                "No operational data returned for allowlisted interface(s): "
                + ", ".join(missing_names)
            )

    def _close(self, dev: Device) -> None:
        """Close the PyEZ session without masking the original failure."""
        if not getattr(dev, "connected", False):
            return
        try:
            dev.close()
        except Exception as err:
            _LOGGER.debug("Error closing Junos NETCONF session: %s", err)


def parse_junos_data(
    system_xml: Any,
    re_xml: Any,
    alarm_xml: Any,
    *,
    uptime_xml: Any | None = None,
    flow_xml: Any | None = None,
    ipsec_xml: Any | None = None,
    cluster_xml: Any | None = None,
    config_xml: Any | None = None,
    interface_xml: Any | None = None,
    interface_allowlist: tuple[str, ...] = (),
    fallback_host: str,
) -> JunosData:
    """Parse the Junos operational XML into a small, stable data model."""
    ipsec_counts = _ipsec_tunnel_counts(ipsec_xml)
    interfaces = _interface_states(config_xml, interface_xml, interface_allowlist)
    return JunosData(
        hostname=(
            _first_text_any(system_xml, ("host-name", "hostname"))
            or _first_text_any(config_xml, ("host-name",))
            or fallback_host
        ),
        model=_first_text_any(system_xml, ("hardware-model", "model"))
        or _model_from_config(config_xml),
        serial_number=_first_text_any(system_xml, ("serial-number",)),
        version=_first_text_any(system_xml, ("os-version", "junos-version"))
        or _first_text_any(config_xml, ("version",)),
        uptime=_first_uptime(system_xml, uptime_xml, re_xml),
        re_cpu_idle=_first_int_any(re_xml, ("cpu-idle", "idle-cpu")),
        re_memory_usage=_first_int_any(
            re_xml,
            (
                "memory-system-total-util",
                "memory-buffer-utilization",
                "memory-control-plane",
                "memory-heap-utilization",
            ),
        ),
        chassis_alarm_count=_alarm_count(alarm_xml),
        active_flow_sessions=_active_flow_sessions(flow_xml),
        max_flow_sessions=_max_flow_sessions(flow_xml),
        ipsec_tunnel_count=ipsec_counts.total,
        ipsec_tunnels_up=ipsec_counts.up,
        ipsec_tunnels_down=ipsec_counts.down,
        chassis_cluster_enabled=_chassis_cluster_enabled(cluster_xml),
        chassis_cluster_redundancy_group_status=_chassis_cluster_rg_status(cluster_xml),
        system_services=_system_services(config_xml),
        interfaces=interfaces,
    )


def _local_name(tag: str) -> str:
    """Return an XML tag name without namespace."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _descendants(root: Any, name: str) -> list[Any]:
    """Return descendants matching a local XML element name."""
    if root is None:
        return []
    if isinstance(root, tuple | list):
        matches: list[Any] = []
        for item in root:
            matches.extend(_descendants(item, name))
        return matches
    return [node for node in root.iter() if _local_name(str(node.tag)) == name]


def _first_text(root: Any, name: str) -> str | None:
    """Return stripped text for the first matching XML descendant."""
    for node in _descendants(root, name):
        if node.text:
            value = node.text.strip()
            if value:
                return value
    return None


def _first_text_any(root: Any, names: tuple[str, ...]) -> str | None:
    """Return stripped text for the first matching XML descendant name."""
    for name in names:
        value = _first_text(root, name)
        if value is not None:
            return value
    return None


def _first_int(root: Any, name: str) -> int | None:
    """Return the first matching integer value, tolerating percent signs."""
    value = _first_text(root, name)
    if value is None:
        return None
    try:
        return int(value.replace("%", "").strip())
    except ValueError:
        return None


def _first_int_any(root: Any, names: tuple[str, ...]) -> int | None:
    """Return the first matching integer from any XML descendant name."""
    for name in names:
        value = _first_int(root, name)
        if value is not None:
            return value
    return None


def _first_int_matching(root: Any, needles: tuple[str, ...]) -> int | None:
    """Return first integer whose XML tag contains all requested text."""
    if root is None:
        return None
    for node in root.iter():
        name = _local_name(str(node.tag)).lower()
        if all(needle in name for needle in needles) and node.text:
            try:
                return int(node.text.replace("%", "").strip())
            except ValueError:
                continue
    return None


def _first_available(*values: int | None) -> int | None:
    """Return the first value that is not None, preserving zero."""
    for value in values:
        if value is not None:
            return value
    return None


def _model_from_config(config_xml: Any | None) -> str | None:
    """Return an SRX model inferred from banana's source-of-truth config shape."""
    configured_interfaces = _configured_interface_names(config_xml)
    if {"ge-0/0/0", "ge-0/0/7", "irb.100"}.issubset(configured_interfaces):
        return "SRX320"
    return None


def _first_uptime(system_xml: Any, uptime_xml: Any | None, re_xml: Any) -> str | None:
    """Return uptime from system, uptime, or routing-engine XML."""
    return (
        _first_text_any(system_xml, ("up-time", "uptime"))
        or _first_text_any(uptime_xml, ("up-time", "uptime", "time-length"))
        or _first_text_any(re_xml, ("up-time", "uptime"))
    )


def _system_services(config_xml: Any | None) -> tuple[str, ...] | None:
    """Return configured system services useful as HA status entities."""
    if config_xml is None:
        return None

    services: list[str] = []
    system_services = _first_descendant(config_xml, "services")
    if system_services is None:
        return ()

    if _first_descendant(system_services, "ssh") is not None:
        services.append("ssh")
    netconf = _first_descendant(system_services, "netconf")
    if netconf is not None and _first_descendant(netconf, "ssh") is not None:
        services.append("netconf_ssh")
    if _first_descendant(system_services, "dhcp-local-server") is not None:
        services.append("dhcp_local_server")
    web_management = _first_descendant(system_services, "web-management")
    if (
        web_management is not None
        and _first_descendant(web_management, "https") is not None
    ):
        services.append("web_management_https")
    return tuple(services)


def _first_descendant(root: Any | None, name: str) -> Any | None:
    """Return the first descendant matching a local XML element name."""
    matches = _descendants(root, name)
    if matches:
        return matches[0]
    return None


def _configured_interface_names(config_xml: Any | None) -> set[str]:
    """Return physical and logical interfaces configured on the device."""
    names: set[str] = set()
    interfaces = _first_descendant(config_xml, "interfaces")
    if interfaces is None:
        return names

    for interface in _direct_children(interfaces, "interface"):
        physical_name = _first_direct_text(interface, "name")
        if not physical_name:
            continue
        names.add(physical_name)
        for unit in _direct_children(interface, "unit"):
            unit_name = _first_direct_text(unit, "name")
            if unit_name is not None:
                names.add(f"{physical_name}.{unit_name}")
    return names


def _interface_states(
    config_xml: Any | None,
    interface_xml: Any | None,
    interface_allowlist: tuple[str, ...],
) -> tuple[JunosInterfaceState, ...]:
    """Return state for explicitly allowlisted interfaces only."""
    selected_names = tuple(dict.fromkeys(interface_allowlist))
    if not selected_names:
        return ()

    configured_names = {
        name
        for name in _configured_interface_names(config_xml)
        if _is_selected_interface(name, selected_names)
    }
    descriptions = _configured_interface_descriptions(config_xml)
    operational = _operational_interfaces(interface_xml)
    names = sorted(
        configured_names
        | {name for name in operational if _is_selected_interface(name, selected_names)},
        key=_interface_sort_key,
    )

    states: list[JunosInterfaceState] = []
    for name in names:
        op_state = operational.get(name, {})
        enabled = _interface_enabled(
            op_state.get("admin_status"),
            op_state.get("oper_status"),
        )
        states.append(
            JunosInterfaceState(
                name=name,
                description=op_state.get("description") or descriptions.get(name),
                admin_status=op_state.get("admin_status"),
                oper_status=op_state.get("oper_status"),
                enabled=enabled,
                rx_mbps=_mbps_from_bps(op_state.get("input_bps")),
                tx_mbps=_mbps_from_bps(op_state.get("output_bps")),
                input_errors=_int_from_text(op_state.get("input_errors")),
                output_errors=_int_from_text(op_state.get("output_errors")),
            )
        )
    return tuple(states)


def _configured_interface_descriptions(config_xml: Any | None) -> dict[str, str]:
    """Return descriptions for configured physical interfaces."""
    descriptions: dict[str, str] = {}
    interfaces = _first_descendant(config_xml, "interfaces")
    if interfaces is None:
        return descriptions

    for interface in _direct_children(interfaces, "interface"):
        name = _first_direct_text(interface, "name")
        description = _first_direct_text(interface, "description")
        if name and description:
            descriptions[name] = description
    return descriptions


def _operational_interfaces(
    interface_xml: Any | None,
) -> dict[str, dict[str, str | None]]:
    """Return operational interface state indexed by physical/logical name."""
    states: dict[str, dict[str, str | None]] = {}
    for physical in _descendants(interface_xml, "physical-interface"):
        name = _first_direct_text(physical, "name")
        if name:
            states[name] = {
                "description": _first_direct_text(physical, "description"),
                "admin_status": _first_direct_text(physical, "admin-status"),
                "oper_status": _first_direct_text(physical, "oper-status"),
                "input_bps": _first_text(physical, "input-bps"),
                "output_bps": _first_text(physical, "output-bps"),
                "input_errors": _first_text(physical, "input-errors"),
                "output_errors": _first_text(physical, "output-errors"),
            }
        for logical in _direct_children(physical, "logical-interface"):
            logical_name = _first_direct_text(logical, "name")
            if logical_name:
                states[logical_name] = {
                    "description": _first_direct_text(logical, "description"),
                    "admin_status": _first_direct_text(logical, "admin-status"),
                    "oper_status": _first_direct_text(logical, "oper-status"),
                    "input_bps": _first_text(logical, "input-bps"),
                    "output_bps": _first_text(logical, "output-bps"),
                    "input_errors": _first_text(logical, "input-errors"),
                    "output_errors": _first_text(logical, "output-errors"),
                }
    return states


def _interface_enabled(
    admin_status: str | None,
    oper_status: str | None,
) -> bool | None:
    """Return HA connectivity state from Junos interface status strings."""
    if oper_status:
        return oper_status.lower() == "up"
    if admin_status:
        return admin_status.lower() == "up"
    return None


def _direct_children(root: Any | None, name: str) -> list[Any]:
    """Return direct children matching a local XML element name."""
    if root is None:
        return []
    return [child for child in list(root) if _local_name(str(child.tag)) == name]


def _first_direct_text(root: Any | None, name: str) -> str | None:
    """Return stripped text for the first matching direct child."""
    for child in _direct_children(root, name):
        if child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _interface_sort_key(name: str) -> tuple[int, str]:
    """Sort physical Ethernet ports before logical and service interfaces."""
    if name.startswith("ge-0/0/"):
        return (0, name)
    if name.startswith("irb."):
        return (1, name)
    if name.startswith("dl"):
        return (2, name)
    return (3, name)


def _is_selected_interface(name: str, selected_names: tuple[str, ...]) -> bool:
    """Return true when an interface is explicitly selected for HA entities."""
    if name not in selected_names:
        return False
    if _is_internal_interface(name):
        return name in selected_names
    return True


def _is_internal_interface(name: str) -> bool:
    """Return true for Junos internal/system interface families."""
    base_name = name.split(".", 1)[0]
    return any(
        base_name == prefix or base_name.startswith(f"{prefix}-")
        for prefix in INTERNAL_INTERFACE_PREFIXES
    )


def _mbps_from_bps(value: str | None) -> float | None:
    """Return megabits per second from a Junos bits-per-second string."""
    bps = _int_from_text(value)
    if bps is None:
        return None
    return round(bps / 1_000_000, 3)


def _int_from_text(value: str | None) -> int | None:
    """Return an integer from a text value, tolerating commas."""
    if value is None:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _alarm_count(alarm_xml: Any | None) -> int | None:
    """Return alarm count, or None when alarm RPC data is unavailable."""
    if alarm_xml is None:
        return None
    return len(_descendants(alarm_xml, "alarm-detail"))


def _active_flow_sessions(flow_xml: Any | None) -> int | None:
    """Return active SRX flow sessions from supported summary XML."""
    return _first_available(
        _first_int_any(
            flow_xml,
            (
                "active-sessions",
                "active-session-count",
                "active-flow-session-count",
            ),
        ),
        _first_int_matching(flow_xml, ("active", "session")),
    )


def _max_flow_sessions(flow_xml: Any | None) -> int | None:
    """Return maximum SRX flow sessions from supported summary XML."""
    return _first_available(
        _first_int_any(
            flow_xml,
            (
                "max-sessions",
                "max-session-count",
                "maximum-sessions",
                "maximum-session-count",
                "session-limit",
            ),
        ),
        _first_int_matching(flow_xml, ("max", "session")),
    )


def _ipsec_tunnel_counts(ipsec_xml: Any | None) -> IpsecTunnelCounts:
    """Return total, up, and down IPsec tunnel counts."""
    if ipsec_xml is None:
        return IpsecTunnelCounts(None, None, None)

    entries = _ipsec_entries(ipsec_xml)
    if not entries:
        return IpsecTunnelCounts(None, None, None)

    up = 0
    down = 0
    for entry in entries:
        state = (
            _first_text_any(
                entry,
                ("sa-block-state", "ipsec-sa-state", "state", "status"),
            )
            or ""
        ).lower()
        if state in {"up", "active", "established"}:
            up += 1
        else:
            down += 1
    return IpsecTunnelCounts(len(entries), up, down)


def _ipsec_entries(ipsec_xml: Any) -> list[Any]:
    """Return XML elements that represent IPsec tunnel/SA rows."""
    for name in (
        "ipsec-security-associations-block",
        "ipsec-security-association",
        "ipsec-sa",
    ):
        entries = _descendants(ipsec_xml, name)
        if entries:
            return entries
    return []


def _chassis_cluster_enabled(cluster_xml: Any | None) -> bool | None:
    """Return whether chassis cluster data is present."""
    if cluster_xml is None:
        return None
    if _descendants(cluster_xml, "chassis-cluster-status"):
        return True
    if _descendants(cluster_xml, "redundancy-group"):
        return True
    return None


def _chassis_cluster_rg_status(cluster_xml: Any | None) -> str | None:
    """Return a compact redundancy group status summary."""
    if cluster_xml is None:
        return None

    groups = _descendants(cluster_xml, "redundancy-group")
    if not groups:
        return _first_text_any(
            cluster_xml,
            ("cluster-status", "chassis-cluster-status", "status"),
        )

    summaries: list[str] = []
    for index, group in enumerate(groups):
        group_id = _first_text_any(
            group,
            ("redundancy-group-id", "group-id", "id", "name"),
        ) or str(index)
        status = _first_text_any(group, ("status", "state", "failover-mode"))
        primary = _first_text_any(
            group,
            ("primary-node", "primary", "master-node", "master"),
        )
        parts = [f"RG {group_id}"]
        if status:
            parts.append(status)
        if primary:
            parts.append(f"primary {primary}")
        summaries.append(": ".join((parts[0], ", ".join(parts[1:]))))
    return "; ".join(summaries)


def _log_missing_metrics(data: JunosData, re_xml: Any, uptime_xml: Any | None) -> None:
    """Log useful XML context when expected MVP metrics are missing."""
    missing = []
    if data.re_cpu_idle is None:
        missing.append("routing_engine_cpu_idle")
    if data.re_memory_usage is None:
        missing.append("routing_engine_memory_usage")
    if data.uptime is None:
        missing.append("uptime")

    if not missing:
        _LOGGER.debug(
            "Parsed Junos metrics: uptime=%s re_cpu_idle=%s re_memory_usage=%s",
            data.uptime,
            data.re_cpu_idle,
            data.re_memory_usage,
        )
        return

    _LOGGER.warning(
        "Missing Junos metrics %s. route-engine tags=%s uptime tags=%s",
        ", ".join(missing),
        _child_tag_summary(re_xml, "route-engine"),
        _tag_summary(uptime_xml),
    )


def _child_tag_summary(root: Any, parent_name: str) -> list[str]:
    """Return direct child tag names for the first matching parent."""
    parents = _descendants(root, parent_name)
    if not parents:
        return _tag_summary(root)
    return [_local_name(str(child.tag)) for child in list(parents[0])]


def _tag_summary(root: Any) -> list[str]:
    """Return a compact list of local XML tag names."""
    if root is None:
        return []
    tags: list[str] = []
    for node in root.iter():
        name = _local_name(str(node.tag))
        if name not in tags:
            tags.append(name)
        if len(tags) >= 40:
            break
    return tags


def _exception_message(err: Exception) -> str:
    """Return a useful PyEZ/ncclient/Paramiko error message."""
    original = getattr(err, "_orig", None)
    if original is not None:
        return f"{err.__class__.__name__}: {err}; original={original.__class__.__name__}: {original}"
    return f"{err.__class__.__name__}: {err}"
