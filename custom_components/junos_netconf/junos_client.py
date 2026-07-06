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
    chassis_alarm_count: int


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
            system_xml = dev.rpc.get_system_information()
            uptime_xml = self._optional_rpc(
                "get-system-uptime-information",
                dev.rpc.get_system_uptime_information,
            )
            re_xml = dev.rpc.get_route_engine_information()
            alarm_xml = dev.rpc.get_alarm_information()
            return parse_junos_data(
                system_xml,
                re_xml,
                alarm_xml,
                uptime_xml=uptime_xml,
                fallback_host=self.host,
            )
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
            try:
                dev.close()
            except Exception as err:  # Best effort cleanup; do not mask poll errors.
                _LOGGER.debug("Error closing Junos NETCONF session: %s", err)

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

    def _optional_rpc(self, rpc_name: str, rpc_call: Any) -> Any | None:
        """Run an optional read-only RPC without failing the whole poll."""
        try:
            return rpc_call()
        except (AttributeError, RpcError) as err:
            _LOGGER.debug("Optional Junos RPC %s failed: %s", rpc_name, err)
            return None


def parse_junos_data(
    system_xml: Any,
    re_xml: Any,
    alarm_xml: Any,
    *,
    uptime_xml: Any | None = None,
    fallback_host: str,
) -> JunosData:
    """Parse the Junos operational XML into a small, stable data model."""
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
        chassis_alarm_count=len(_descendants(alarm_xml, "alarm-detail")),
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


def _first_uptime(system_xml: Any, uptime_xml: Any | None, re_xml: Any) -> str | None:
    """Return uptime from system, uptime, or routing-engine XML."""
    return (
        _first_text_any(system_xml, ("up-time", "uptime"))
        or _first_text_any(uptime_xml, ("up-time", "uptime", "time-length"))
        or _first_text_any(re_xml, ("up-time", "uptime"))
    )


def _exception_message(err: Exception) -> str:
    """Return a useful PyEZ/ncclient/Paramiko error message."""
    original = getattr(err, "_orig", None)
    if original is not None:
        return f"{err.__class__.__name__}: {err}; original={original.__class__.__name__}: {original}"
    return f"{err.__class__.__name__}: {err}"
