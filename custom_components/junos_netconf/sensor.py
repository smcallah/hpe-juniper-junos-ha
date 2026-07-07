"""Sensor entities for read-only Junos NETCONF monitoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JunosNetconfCoordinator
from .junos_client import JunosData, JunosInterfaceState


@dataclass(frozen=True)
class JunosSensorDescription:
    """Description for a Junos sensor."""

    key: str
    name: str
    value_fn: Callable[[JunosData], float | int | str | None]
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | None = None
    optional: bool = False


DEVICE_SENSORS: tuple[JunosSensorDescription, ...] = (
    JunosSensorDescription("uptime", "Uptime", lambda data: data.uptime),
    JunosSensorDescription(
        "routing_engine_cpu_idle",
        "Routing Engine CPU Idle",
        lambda data: data.re_cpu_idle,
        PERCENTAGE,
        SensorStateClass.MEASUREMENT,
    ),
    JunosSensorDescription(
        "routing_engine_memory_usage",
        "Routing Engine Memory Usage",
        lambda data: data.re_memory_usage,
        PERCENTAGE,
        SensorStateClass.MEASUREMENT,
    ),
    JunosSensorDescription(
        "chassis_alarm_count",
        "Chassis Alarm Count",
        lambda data: data.chassis_alarm_count,
        None,
        SensorStateClass.MEASUREMENT,
    ),
)

SRX_SENSORS: tuple[JunosSensorDescription, ...] = (
    JunosSensorDescription(
        "active_flow_sessions",
        "Active Flow Sessions",
        lambda data: data.active_flow_sessions,
        None,
        SensorStateClass.MEASUREMENT,
        True,
    ),
    JunosSensorDescription(
        "max_flow_sessions",
        "Max Flow Sessions",
        lambda data: data.max_flow_sessions,
        None,
        SensorStateClass.MEASUREMENT,
        True,
    ),
    JunosSensorDescription(
        "ipsec_vpn_tunnel_count",
        "IPsec VPN Tunnel Count",
        lambda data: data.ipsec_tunnel_count,
        None,
        SensorStateClass.MEASUREMENT,
        True,
    ),
    JunosSensorDescription(
        "ipsec_tunnels_up",
        "IPsec Tunnels Up",
        lambda data: data.ipsec_tunnels_up,
        None,
        SensorStateClass.MEASUREMENT,
        True,
    ),
    JunosSensorDescription(
        "ipsec_tunnels_down",
        "IPsec Tunnels Down",
        lambda data: data.ipsec_tunnels_down,
        None,
        SensorStateClass.MEASUREMENT,
        True,
    ),
    JunosSensorDescription(
        "chassis_cluster_redundancy_group_status",
        "Chassis Cluster Redundancy Group Status",
        lambda data: data.chassis_cluster_redundancy_group_status,
        None,
        None,
        True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Junos NETCONF sensors."""
    coordinator: JunosNetconfCoordinator = entry.runtime_data
    descriptions = list(DEVICE_SENSORS)
    descriptions.extend(
        description
        for description in SRX_SENSORS
        if description.value_fn(coordinator.data) is not None
    )
    entities: list[SensorEntity] = [
        JunosSensor(coordinator, entry, description) for description in descriptions
    ]
    entities.extend(
        JunosInterfaceMetricSensor(coordinator, entry, interface.name, metric)
        for interface in coordinator.data.interfaces
        for metric in INTERFACE_METRICS
    )
    async_add_entities(entities)


class JunosSensor(CoordinatorEntity[JunosNetconfCoordinator], SensorEntity):
    """A read-only Junos sensor backed by DataUpdateCoordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JunosNetconfCoordinator,
        entry: ConfigEntry,
        description: JunosSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.description = description
        self._attr_unique_id = f"{_entry_uid(entry)}_{description.key}"
        self._attr_name = description.name
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> float | int | str | None:
        """Return the current sensor value."""
        return self.description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        return _device_info(self.coordinator.data, self.entry)


@dataclass(frozen=True)
class JunosInterfaceMetricDescription:
    """Description for selected interface metric sensors."""

    key: str
    name: str
    value_fn: Callable[[JunosInterfaceState], float | int | None]
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | None = None


INTERFACE_METRICS: tuple[JunosInterfaceMetricDescription, ...] = (
    JunosInterfaceMetricDescription(
        "rx_mbps",
        "RX Mbps",
        lambda interface: interface.rx_mbps,
        "Mbit/s",
        SensorStateClass.MEASUREMENT,
    ),
    JunosInterfaceMetricDescription(
        "tx_mbps",
        "TX Mbps",
        lambda interface: interface.tx_mbps,
        "Mbit/s",
        SensorStateClass.MEASUREMENT,
    ),
    JunosInterfaceMetricDescription(
        "input_errors",
        "Input Errors",
        lambda interface: interface.input_errors,
        None,
        SensorStateClass.TOTAL_INCREASING,
    ),
    JunosInterfaceMetricDescription(
        "output_errors",
        "Output Errors",
        lambda interface: interface.output_errors,
        None,
        SensorStateClass.TOTAL_INCREASING,
    ),
)


class JunosInterfaceMetricSensor(
    CoordinatorEntity[JunosNetconfCoordinator],
    SensorEntity,
):
    """Report a selected Junos interface metric."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JunosNetconfCoordinator,
        entry: ConfigEntry,
        interface_name: str,
        description: JunosInterfaceMetricDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.interface_name = interface_name
        self.description = description
        self._attr_name = f"{interface_name} {description.name}"
        self._attr_unique_id = (
            f"{_entry_uid(entry)}_interface_{_slug(interface_name)}_{description.key}"
        )
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> float | int | None:
        """Return the current interface metric value."""
        interface = self._interface()
        if interface is None:
            return None
        return self.description.value_fn(interface)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        return _device_info(self.coordinator.data, self.entry)

    def _interface(self) -> JunosInterfaceState | None:
        """Return this sensor's current interface state."""
        for interface in self.coordinator.data.interfaces:
            if interface.name == self.interface_name:
                return interface
        return None


def _entry_uid(entry: ConfigEntry) -> str:
    """Return the stable config-entry unique identifier."""
    return entry.unique_id or entry.entry_id


def _device_info(data: JunosData, entry: ConfigEntry) -> DeviceInfo:
    """Return Home Assistant device registry information."""
    return DeviceInfo(
        identifiers={(DOMAIN, _entry_uid(entry))},
        manufacturer="Juniper Networks / HPE",
        model=data.model,
        name=data.hostname,
        serial_number=data.serial_number,
        sw_version=data.version,
    )


def _slug(value: str) -> str:
    """Return a stable unique-id segment for Junos names."""
    return value.replace("/", "_").replace(".", "_").replace("-", "_")
