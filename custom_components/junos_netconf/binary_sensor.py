"""Binary sensor entities for read-only Junos NETCONF monitoring."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JunosNetconfCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Junos NETCONF binary sensors."""
    coordinator: JunosNetconfCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JunosChassisAlarmBinarySensor(coordinator, entry)])


class JunosChassisAlarmBinarySensor(
    CoordinatorEntity[JunosNetconfCoordinator],
    BinarySensorEntity,
):
    """Report whether any chassis alarm is present."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_name = "Chassis Alarm Present"

    def __init__(self, coordinator: JunosNetconfCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.unique_id}_chassis_alarm_present"

    @property
    def is_on(self) -> bool:
        """Return true when one or more chassis alarms are present."""
        return self.coordinator.data.chassis_alarm_count > 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.unique_id or self.entry.entry_id)},
            manufacturer="Juniper Networks / HPE",
            model=data.model,
            name=data.hostname,
            serial_number=data.serial_number,
            sw_version=data.version,
        )
