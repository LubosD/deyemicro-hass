"""DataUpdateCoordinator for Deye Microinverter."""

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .inverter import (
    DeyeModbus,
    REG_AC_CURRENT,
    REG_AC_FREQUENCY,
    REG_AC_VOLTAGE,
    REG_AC_VOLTAGE_FIRST,
    REG_AC_VOLTAGE_LAST,
    REG_POWER_GENERATION,
    REG_POWER_LIMIT,
    REG_YIELD_TODAY,
    REG_YIELD_TODAY_FIRST,
    REG_YIELD_TODAY_LAST,
    REG_YIELD_TOTAL,
    REG_YIELD_TOTAL_HIGH,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


class DeyeCoordinator(DataUpdateCoordinator[dict]):
    """Polls the inverter and caches the latest readings."""

    def __init__(self, hass: HomeAssistant, inverter: DeyeModbus) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Deye Microinverter",
            update_interval=SCAN_INTERVAL,
        )
        self.inverter = inverter

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with inverter: {err}") from err

    def _fetch(self) -> dict:
        power_gen_regs = self.inverter.read_registers(REG_POWER_GENERATION, REG_POWER_GENERATION)
        power_limit_regs = self.inverter.read_registers(REG_POWER_LIMIT, REG_POWER_LIMIT)
        yield_regs = self.inverter.read_registers(REG_YIELD_TODAY_FIRST, REG_YIELD_TODAY_LAST)
        ac_regs = self.inverter.read_registers(REG_AC_VOLTAGE_FIRST, REG_AC_VOLTAGE_LAST)

        if not power_gen_regs or not power_limit_regs or not yield_regs or not ac_regs:
            raise UpdateFailed(
                "No data from inverter — device may be unreachable or powered off"
            )

        return {
            "power_generation": int.from_bytes(power_gen_regs[REG_POWER_GENERATION], "big") / 10,
            "power_limit": int.from_bytes(power_limit_regs[REG_POWER_LIMIT], "big"),
            "yield_today": int.from_bytes(yield_regs[REG_YIELD_TODAY], "big") / 10,
            "yield_total": (
                (int.from_bytes(yield_regs[REG_YIELD_TOTAL_HIGH], "big") << 16)
                | int.from_bytes(yield_regs[REG_YIELD_TOTAL], "big")
            ) / 10,
            "ac_voltage": int.from_bytes(ac_regs[REG_AC_VOLTAGE], "big") / 10,
            "ac_current": int.from_bytes(ac_regs[REG_AC_CURRENT], "big") / 10,
            "ac_frequency": int.from_bytes(ac_regs[REG_AC_FREQUENCY], "big") / 100,
        }
