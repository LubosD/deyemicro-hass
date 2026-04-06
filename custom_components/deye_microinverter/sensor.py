"""Sensor platform for Deye Microinverter."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL_NUMBER, DOMAIN
from .coordinator import DeyeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCoordinator = hass.data[DOMAIN][entry.entry_id]
    serial = entry.data[CONF_SERIAL_NUMBER]
    async_add_entities([
        DeyePowerGenerationSensor(coordinator, serial),
        DeyeYieldTodaySensor(coordinator, serial),
        DeyeYieldTotalSensor(coordinator, serial),
        DeyeAcVoltageSensor(coordinator, serial),
        DeyeAcCurrentSensor(coordinator, serial),
        DeyeAcFrequencySensor(coordinator, serial),
    ])


class DeyePowerGenerationSensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """Current AC output power reported by the inverter (register 86, unit 0.1 W)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_translation_key = "power_generation"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_power_generation"
        self._attr_name = "Power Generation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"Deye Microinverter {serial}",
            manufacturer="Deye",
            model="Microinverter",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["power_generation"]


class DeyeYieldTodaySensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """Energy yielded today (register 60, unit 0.1 kWh)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_translation_key = "yield_today"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_yield_today"
        self._attr_name = "Yield Today"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["yield_today"]


class DeyeYieldTotalSensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """Total energy yielded (register 62, unit 0.1 kWh)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_translation_key = "yield_total"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_yield_total"
        self._attr_name = "Total Yield"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["yield_total"]


class DeyeAcVoltageSensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """AC output voltage (register 73, unit 0.1 V)."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_translation_key = "ac_voltage"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_ac_voltage"
        self._attr_name = "AC Voltage"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["ac_voltage"]


class DeyeAcCurrentSensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """AC output current (register 74, unit 0.1 A)."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_translation_key = "ac_current"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_ac_current"
        self._attr_name = "AC Current"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["ac_current"]


class DeyeAcFrequencySensor(CoordinatorEntity[DeyeCoordinator], SensorEntity):
    """AC output frequency (register 79, unit 0.01 Hz)."""

    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
    _attr_translation_key = "ac_frequency"

    def __init__(self, coordinator: DeyeCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{serial}_ac_frequency"
        self._attr_name = "AC Frequency"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["ac_frequency"]
