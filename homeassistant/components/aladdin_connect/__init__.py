"""The aladdin_connect component."""
import logging
from typing import Final

from aladdin_connect import AladdinConnectClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import DOMAIN

_LOGGER: Final = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    acc = AladdinConnectClient(username, password)
    try:
        if not await hass.async_add_executor_job(acc.login):
            raise ConfigEntryAuthFailed("Incorrect Password")
    except (TypeError, KeyError, NameError, ValueError) as ex:
        _LOGGER.error("%s", ex)
        raise ConfigEntryNotReady from ex
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = acc
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
