"""Deye Microinverter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL_NUMBER, DOMAIN, PLATFORMS
from .inverter import DeyeModbus


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Deye Microinverter from a config entry."""
    from homeassistant.const import CONF_HOST, CONF_PORT
    from homeassistant.exceptions import ConfigEntryNotReady
    from .coordinator import DeyeCoordinator

    inverter = DeyeModbus(
        ip_address=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        serial_number=int(entry.data[CONF_SERIAL_NUMBER]),
    )

    coordinator = DeyeCoordinator(hass, inverter)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Cannot reach inverter at {entry.data[CONF_HOST]}: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
