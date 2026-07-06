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

from .exceptions import JunosNetconfAuthError, JunosNetconfConnectionError

_LOGGER = logging.getLogger(__name__)


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
    ) -> None:
        """Store connection settings."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify_hostkey = verify_hostkey

    def get_data(self) -> JunosData:
        """Open a NETCONF session, collect read-only data, and close it."""
        dev = self._device()
        try:
            _LOGGER.debug("Opening Junos NETCONF session to %s:%s", self.host, self.port)
            dev.open()
            system_xml = self._optional_rpc(
                dev,
                "get-system-information",
                "get_system_information",
            )
            uptime_xml = self._optional_rpc(
                dev,
                "get-system-uptime-information",
                "get_system_uptime_information",
            )
            re_xml = self._optional_rpc(
                dev,
                "get-route-engine-information",
                "get_route_engine_information",
            )
            alarm_xml = self._optional_rpc(
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
            data = parse_junos_data(
                system_xml,
                re_xml,
                alarm_xml,
                uptime_xml=uptime_xml,
                flow_xml=flow_xml,
                ipsec_xml=ipsec_xml,
                cluster_xml=cluster_xml,
                fallback_host=self.host,
            )
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
    fallback_host: str,
) -> JunosData:
    """Parse the Junos operational XML into a small, stable data model."""
    ipsec_counts = _ipsec_tunnel_counts(ipsec_xml)
    return JunosData(
        hostname=_first_text_any(system_xml, ("host-name", "hostname")) or fallback_host,
        model=_first_text_any(system_xml, ("hardware-model", "model")),
        serial_number=_first_text_any(system_xml, ("serial-number",)),
        version=_first_text_any(system_xml, ("os-version", "junos-version")),
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


def _first_uptime(system_xml: Any, uptime_xml: Any | None, re_xml: Any) -> str | None:
    """Return uptime from system, uptime, or routing-engine XML."""
    return (
        _first_text_any(system_xml, ("up-time", "uptime"))
        or _first_text_any(uptime_xml, ("up-time", "uptime", "time-length"))
        or _first_text_any(re_xml, ("up-time", "uptime"))
    )


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
