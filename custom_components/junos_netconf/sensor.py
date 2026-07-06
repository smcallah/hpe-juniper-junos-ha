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
from .junos_client import JunosData


@dataclass(frozen=True)
class JunosSensorDescription:
    """Description for a Junos sensor."""

    key: str
    name: str
    value_fn: Callable[[JunosData], int | str | None]
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | None = None


SENSORS: tuple[JunosSensorDescription, ...] = (
    JunosSensorDescription("hostname", "Hostname", lambda data: data.hostname),
    JunosSensorDescription("model", "Model", lambda data: data.model),
    JunosSensorDescription(
        "serial_number",
        "Serial Number",
        lambda data: data.serial_number,
    ),
    JunosSensorDescription(
        "junos_version",
        "Junos Version",
        lambda data: data.version,
    ),
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Junos NETCONF sensors."""
    coordinator: JunosNetconfCoordinator = entry.runtime_data
    async_add_entities(
        JunosSensor(coordinator, entry, description) for description in SENSORS
    )


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
    def native_value(self) -> int | str | None:
        """Return the current sensor value."""
        return self.description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, _entry_uid(self.entry))},
            manufacturer="Juniper Networks / HPE",
            model=data.model,
            name=data.hostname,
            serial_number=data.serial_number,
            sw_version=data.version,
        )


def _entry_uid(entry: ConfigEntry) -> str:
    """Return the stable config-entry unique identifier."""
    return entry.unique_id or entry.entry_id
