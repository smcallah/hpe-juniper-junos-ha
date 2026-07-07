"""Binary sensor entities for read-only Junos NETCONF monitoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
from .junos_client import JunosData


@dataclass(frozen=True)
class JunosBinarySensorDescription:
    """Description for a Junos binary sensor."""

    key: str
    name: str
    value_fn: Callable[[JunosData], bool | None]
    device_class: BinarySensorDeviceClass


SYSTEM_SERVICE_DESCRIPTIONS: tuple[JunosBinarySensorDescription, ...] = (
    JunosBinarySensorDescription(
        "service_ssh",
        "SSH Service Enabled",
        lambda data: "ssh" in data.system_services,
        BinarySensorDeviceClass.CONNECTIVITY,
    ),
    JunosBinarySensorDescription(
        "service_netconf_ssh",
        "NETCONF SSH Service Enabled",
        lambda data: "netconf_ssh" in data.system_services,
        BinarySensorDeviceClass.CONNECTIVITY,
    ),
    JunosBinarySensorDescription(
        "service_dhcp_local_server",
        "DHCP Local Server Enabled",
        lambda data: "dhcp_local_server" in data.system_services,
        BinarySensorDeviceClass.CONNECTIVITY,
    ),
    JunosBinarySensorDescription(
        "service_web_management_https",
        "HTTPS Web Management Enabled",
        lambda data: "web_management_https" in data.system_services,
        BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Junos NETCONF binary sensors."""
    coordinator: JunosNetconfCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        JunosChassisAlarmBinarySensor(coordinator, entry)
    ]
    if coordinator.data.chassis_cluster_enabled is not None:
        entities.append(JunosChassisClusterEnabledBinarySensor(coordinator, entry))
    entities.extend(
        JunosSystemServiceBinarySensor(coordinator, entry, description)
        for description in SYSTEM_SERVICE_DESCRIPTIONS
        if description.value_fn(coordinator.data)
    )
    entities.extend(
        JunosInterfaceEnabledBinarySensor(coordinator, entry, interface.name)
        for interface in coordinator.data.interfaces
    )
    async_add_entities(entities)


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
        self._attr_unique_id = f"{_entry_uid(entry)}_chassis_alarm_present"

    @property
    def is_on(self) -> bool | None:
        """Return true when one or more chassis alarms are present."""
        alarm_count = self.coordinator.data.chassis_alarm_count
        if alarm_count is None:
            return None
        return alarm_count > 0

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


class JunosChassisClusterEnabledBinarySensor(
    CoordinatorEntity[JunosNetconfCoordinator],
    BinarySensorEntity,
):
    """Report whether chassis cluster status is available/enabled."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Chassis Cluster Enabled"

    def __init__(self, coordinator: JunosNetconfCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{_entry_uid(entry)}_chassis_cluster_enabled"

    @property
    def is_on(self) -> bool | None:
        """Return true when chassis cluster status is supported and present."""
        return self.coordinator.data.chassis_cluster_enabled

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


class JunosSystemServiceBinarySensor(
    CoordinatorEntity[JunosNetconfCoordinator],
    BinarySensorEntity,
):
    """Report whether a configured Junos system service is enabled."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JunosNetconfCoordinator,
        entry: ConfigEntry,
        description: JunosBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.description = description
        self._attr_device_class = description.device_class
        self._attr_name = description.name
        self._attr_unique_id = f"{_entry_uid(entry)}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true when the configured service is enabled."""
        return self.description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        return _device_info(self.coordinator.data, self.entry)


class JunosInterfaceEnabledBinarySensor(
    CoordinatorEntity[JunosNetconfCoordinator],
    BinarySensorEntity,
):
    """Report whether a Junos interface is operationally up."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JunosNetconfCoordinator,
        entry: ConfigEntry,
        interface_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.interface_name = interface_name
        self._attr_name = f"{interface_name} Link Up"
        self._attr_unique_id = (
            f"{_entry_uid(entry)}_interface_{_slug(interface_name)}_up"
        )

    @property
    def is_on(self) -> bool | None:
        """Return true when the interface is operationally up."""
        for interface in self.coordinator.data.interfaces:
            if interface.name == self.interface_name:
                return interface.enabled
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information."""
        return _device_info(self.coordinator.data, self.entry)


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


def _entry_uid(entry: ConfigEntry) -> str:
    """Return the stable config-entry unique identifier."""
    return entry.unique_id or entry.entry_id
