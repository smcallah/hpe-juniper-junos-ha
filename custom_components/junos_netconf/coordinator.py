"""DataUpdateCoordinator for Junos NETCONF polling."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import JunosNetconfAuthError, JunosNetconfConnectionError
from .junos_client import JunosData, JunosPyEzClient

_LOGGER = logging.getLogger(__name__)


class JunosNetconfCoordinator(DataUpdateCoordinator[JunosData]):
    """Coordinate one read-only Junos NETCONF poll for all entities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: JunosPyEzClient,
    ) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client

    async def _async_update_data(self) -> JunosData:
        """Run blocking PyEZ collection in Home Assistant's executor."""
        try:
            return await self.hass.async_add_executor_job(self.client.get_data)
        except JunosNetconfAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except JunosNetconfConnectionError as err:
            raise UpdateFailed(str(err)) from err
