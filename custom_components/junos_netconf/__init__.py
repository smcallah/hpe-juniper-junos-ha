"""Home Assistant custom integration for read-only Junos NETCONF monitoring."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_HOST,
    CONF_INTERFACE_ALLOWLIST,
    CONF_TIMEOUT,
    CONF_VERIFY_HOSTKEY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import JunosNetconfCoordinator
from .junos_client import JunosData, JunosPyEzClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Junos NETCONF from a config entry."""
    client = JunosPyEzClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        timeout=entry.data[CONF_TIMEOUT],
        verify_hostkey=entry.data[CONF_VERIFY_HOSTKEY],
        interface_allowlist=_interface_allowlist(entry),
    )
    coordinator = JunosNetconfCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    _register_device(hass, entry, coordinator.data)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Junos NETCONF config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _interface_allowlist(entry: ConfigEntry) -> tuple[str, ...]:
    """Return configured interface names from data/options."""
    raw_value = entry.options.get(
        CONF_INTERFACE_ALLOWLIST,
        entry.data.get(CONF_INTERFACE_ALLOWLIST, ""),
    )
    if not isinstance(raw_value, str):
        return ()
    names = raw_value.replace(",", " ").split()
    return tuple(dict.fromkeys(name.strip() for name in names if name.strip()))


def _register_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: JunosData,
) -> None:
    """Create or update the Junos device registry record from polled facts."""
    device_registry = dr.async_get(hass)
    unique_id = entry.unique_id or entry.entry_id
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, unique_id)},
        manufacturer="Juniper Networks / HPE",
        model=data.model,
        name=data.hostname,
        serial_number=data.serial_number,
        sw_version=data.version,
    )
