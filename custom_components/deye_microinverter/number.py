"""Number platform for Deye Microinverter — active power limit control."""

import logging
from time import sleep

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL_NUMBER, DOMAIN
from .coordinator import DeyeCoordinator
from .inverter import REG_POWER_LIMIT, REG_POWER_LIMIT_G4

_LOGGER = logging.getLogger(__name__)

_WRITE_RETRIES = 10
_RETRY_DELAY_S = 1
_POST_WRITE_SETTLE_S = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCoordinator = hass.data[DOMAIN][entry.entry_id]
    serial = entry.data[CONF_SERIAL_NUMBER]
    async_add_entities([
        DeyePowerLimitNumber(coordinator, serial),
        DeyePowerLimitG4Number(coordinator, serial),
    ])


class DeyePowerLimitNumber(CoordinatorEntity[DeyeCoordinator], NumberEntity):
    """Active power limit for the inverter (register 40, unit %).

    Range 1–100 %. Writing retries up to 10 times to work around
    transient connection issues.
    """

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_power_limit"
        self._attr_name = "Power Limit"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"Deye Microinverter {serial}",
            manufacturer="Deye",
            model="Microinverter",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["power_limit"]

    async def async_set_native_value(self, value: float) -> None:
        target = int(value)
        success = await self.hass.async_add_executor_job(
            self._set_power_limit, target
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.warning(
                "Failed to set inverter power limit to %d%% after %d attempts",
                target,
                _WRITE_RETRIES,
            )

    def _set_power_limit(self, value: int) -> bool:
        """Blocking write with retries — intended to run in a thread-pool executor."""
        _LOGGER.debug("Setting inverter power limit to %d%%", value)
        for attempt in range(1, _WRITE_RETRIES + 1):
            try:
                if self.coordinator.inverter.write_register_uint(REG_POWER_LIMIT, value):
                    _LOGGER.debug(
                        "Power limit set to %d%% on attempt %d; waiting %ds for inverter to settle",
                        value,
                        attempt,
                        _POST_WRITE_SETTLE_S,
                    )
                    sleep(_POST_WRITE_SETTLE_S)
                    return True
            except Exception as err:
                _LOGGER.debug("Attempt %d/%d failed: %s", attempt, _WRITE_RETRIES, err)
            if attempt < _WRITE_RETRIES:
                sleep(_RETRY_DELAY_S)
        return False


class DeyePowerLimitG4Number(CoordinatorEntity[DeyeCoordinator], NumberEntity):
    """Active power limit for G4/newer inverters (register 53, unit %).

    Behaves identically to DeyePowerLimitNumber but targets register 53.
    The entity is unavailable when the inverter does not expose this register.
    """

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_power_limit_g4"
        self._attr_name = "Power Limit G4"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"Deye Microinverter {serial}",
            manufacturer="Deye",
            model="Microinverter",
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("power_limit_g4") is not None
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("power_limit_g4")

    async def async_set_native_value(self, value: float) -> None:
        target = int(value)
        success = await self.hass.async_add_executor_job(
            self._set_power_limit_g4, target
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.warning(
                "Failed to set inverter power limit G4 to %d%% after %d attempts",
                target,
                _WRITE_RETRIES,
            )

    def _set_power_limit_g4(self, value: int) -> bool:
        """Blocking write with retries — intended to run in a thread-pool executor."""
        _LOGGER.debug("Setting inverter power limit G4 to %d%%", value)
        for attempt in range(1, _WRITE_RETRIES + 1):
            try:
                if self.coordinator.inverter.write_register_uint(REG_POWER_LIMIT_G4, value):
                    _LOGGER.debug(
                        "Power limit G4 set to %d%% on attempt %d; waiting %ds for inverter to settle",
                        value,
                        attempt,
                        _POST_WRITE_SETTLE_S,
                    )
                    sleep(_POST_WRITE_SETTLE_S)
                    return True
            except Exception as err:
                _LOGGER.debug("Attempt %d/%d failed: %s", attempt, _WRITE_RETRIES, err)
            if attempt < _WRITE_RETRIES:
                sleep(_RETRY_DELAY_S)
        return False
