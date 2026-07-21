"""Sensor entities for NEP Local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NepConfigEntry, gateway_url
from .const import CONF_HOST, DOMAIN, MANUFACTURER, MODEL
from .coordinator import ModuleData, NepDataUpdateCoordinator
from .models import AggregateReading, InventoryModule, MinDatRecord, ModuleStatus


@dataclass(frozen=True, kw_only=True)
class NepGatewaySensorDescription(SensorEntityDescription):
    """Description for a gateway aggregate sensor."""

    value_fn: Callable[[AggregateReading], Any]


@dataclass(frozen=True, kw_only=True)
class NepModuleSensorDescription(SensorEntityDescription):
    """Description for a logical input sensor."""

    value_fn: Callable[[ModuleData], Any]
    requires_live: bool = False
    requires_telemetry: bool = False
    requires_live_or_telemetry: bool = False


@dataclass(frozen=True, kw_only=True)
class NepInverterSensorDescription(SensorEntityDescription):
    """Description for a physical inverter sensor."""

    value_fn: Callable[[tuple[MinDatRecord, ...]], Any]


def _first_telemetry_value(
    records: tuple[MinDatRecord, ...], attribute: str
) -> Any:
    """Return the first reported value for a shared inverter measurement."""
    return next(
        (
            value
            for record in records
            if (value := getattr(record, attribute)) is not None
        ),
        None,
    )


GATEWAY_SENSORS = (
    NepGatewaySensorDescription(
        key="power",
        translation_key="gateway_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda reading: reading.power_w,
    ),
    NepGatewaySensorDescription(
        key="today_energy",
        translation_key="gateway_today_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda reading: reading.today_wh,
    ),
    NepGatewaySensorDescription(
        key="lifetime_energy",
        translation_key="gateway_lifetime_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda reading: reading.total_wh,
    ),
)

MODULE_SENSORS = (
    NepModuleSensorDescription(
        key="power",
        translation_key="module_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        requires_live=True,
        value_fn=lambda data: data.reading.power_w if data.reading else None,
    ),
    NepModuleSensorDescription(
        key="today_energy",
        translation_key="module_today_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        requires_live_or_telemetry=True,
        value_fn=lambda data: (
            data.reading.today_wh
            if data.reading and data.reading.today_wh is not None
            else data.telemetry.energy_wh if data.telemetry else None
        ),
    ),
    NepModuleSensorDescription(
        key="lifetime_energy",
        translation_key="module_lifetime_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        requires_live=True,
        value_fn=lambda data: data.reading.total_wh if data.reading else None,
    ),
    NepModuleSensorDescription(
        key="dc_voltage",
        translation_key="module_dc_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        requires_telemetry=True,
        value_fn=lambda data: data.telemetry.voltage_dc_v if data.telemetry else None,
    ),
    NepModuleSensorDescription(
        key="current",
        translation_key="module_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        requires_telemetry=True,
        value_fn=lambda data: data.telemetry.current_a if data.telemetry else None,
    ),
    NepModuleSensorDescription(
        key="status",
        translation_key="module_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in ModuleStatus],
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_live=True,
        value_fn=lambda data: data.reading.status.value if data.reading else None,
    ),
    NepModuleSensorDescription(
        key="rssi",
        translation_key="module_rssi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        requires_telemetry=True,
        value_fn=lambda data: data.telemetry.rssi if data.telemetry else None,
    ),
    NepModuleSensorDescription(
        key="diagnostic_code",
        translation_key="module_diagnostic_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        requires_telemetry=True,
        value_fn=lambda data: (
            data.telemetry.diagnostic_code if data.telemetry else None
        ),
    ),
)

INVERTER_SENSORS = (
    NepInverterSensorDescription(
        key="ac_voltage",
        translation_key="inverter_ac_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda records: _first_telemetry_value(records, "voltage_ac_v"),
    ),
    NepInverterSensorDescription(
        key="frequency",
        translation_key="inverter_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda records: _first_telemetry_value(records, "frequency_hz"),
    ),
    NepInverterSensorDescription(
        key="temperature",
        translation_key="inverter_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda records: _first_telemetry_value(records, "temperature_c"),
    ),
)


async def async_setup_entry(
    hass,
    entry: NepConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors and add newly discovered channels after coordinator refreshes."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        NepGatewaySensor(coordinator, entry, description)
        for description in GATEWAY_SENSORS
    )
    known_modules: set[str] = set()
    known_inverters: set[str] = set()

    def add_discovered() -> None:
        new_modules = [
            module
            for module in coordinator.data.inventory.modules
            if module.raw_id not in known_modules
        ]
        if new_modules:
            known_modules.update(module.raw_id for module in new_modules)
            async_add_entities(
                NepModuleSensor(coordinator, entry, module, description)
                for module in new_modules
                for description in MODULE_SENSORS
            )

        new_inverters = {
            coordinator.data.inventory.physical_inverter_id(module)
            for module in coordinator.data.inventory.modules
        } - known_inverters
        if new_inverters:
            known_inverters.update(new_inverters)
            async_add_entities(
                NepInverterSensor(coordinator, entry, inverter_id, description)
                for inverter_id in sorted(new_inverters)
                for description in INVERTER_SENSORS
            )

    add_discovered()
    entry.async_on_unload(coordinator.async_add_listener(add_discovered))


class NepGatewaySensor(CoordinatorEntity[NepDataUpdateCoordinator], SensorEntity):
    """An aggregate sensor on the gateway device."""

    _attr_has_entity_name = True
    entity_description: NepGatewaySensorDescription

    def __init__(
        self,
        coordinator: NepDataUpdateCoordinator,
        entry: NepConfigEntry,
        description: NepGatewaySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.data.inventory.serial
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"NEP Gateway {serial}",
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=serial,
            configuration_url=gateway_url(entry.data[CONF_HOST]),
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.aggregate is not None

    @property
    def native_value(self):
        reading = self.coordinator.data.aggregate
        return self.entity_description.value_fn(reading) if reading else None


class NepModuleSensor(CoordinatorEntity[NepDataUpdateCoordinator], SensorEntity):
    """A sensor for one logical PV input, grouped under its physical inverter."""

    _attr_has_entity_name = True
    entity_description: NepModuleSensorDescription

    def __init__(
        self,
        coordinator: NepDataUpdateCoordinator,
        entry: NepConfigEntry,
        module: InventoryModule,
        description: NepModuleSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.module = module
        self.entity_description = description
        serial = coordinator.data.inventory.serial
        inverter_id = coordinator.data.inventory.physical_inverter_id(module)
        self._attr_unique_id = f"{serial}_{module.raw_id}_{description.key}"
        self._attr_translation_placeholders = {"channel": module.address}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_{inverter_id}")},
            name=f"NEP Inverter {inverter_id}",
            manufacturer=MANUFACTURER,
            model="Microinverter",
            serial_number=inverter_id,
            via_device=(DOMAIN, serial),
        )

    @property
    def _module_data(self) -> ModuleData | None:
        return self.coordinator.data.modules.get(self.module.raw_id)

    @property
    def available(self) -> bool:
        if not super().available or self._module_data is None:
            return False
        if self.entity_description.requires_live:
            return self._module_data.reading is not None
        if self.entity_description.requires_telemetry:
            return self._module_data.telemetry is not None
        if self.entity_description.requires_live_or_telemetry:
            return (
                self._module_data.reading is not None
                or self._module_data.telemetry is not None
            )
        return True

    @property
    def native_value(self):
        data = self._module_data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self.entity_description.key != "status" or self._module_data is None:
            return None
        reading = self._module_data.reading
        return (
            {"raw_status": reading.status_code}
            if reading and reading.status_code
            else None
        )


class NepInverterSensor(CoordinatorEntity[NepDataUpdateCoordinator], SensorEntity):
    """A shared measurement for one physical dual-input inverter."""

    _attr_has_entity_name = True
    entity_description: NepInverterSensorDescription

    def __init__(
        self,
        coordinator: NepDataUpdateCoordinator,
        entry: NepConfigEntry,
        inverter_id: str,
        description: NepInverterSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.inverter_id = inverter_id
        self.entity_description = description
        serial = coordinator.data.inventory.serial
        self._attr_unique_id = f"{serial}_{inverter_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_{inverter_id}")},
            name=f"NEP Inverter {inverter_id}",
            manufacturer=MANUFACTURER,
            model="Microinverter",
            serial_number=inverter_id,
            via_device=(DOMAIN, serial),
        )

    @property
    def _telemetry(self) -> tuple[MinDatRecord, ...]:
        inventory = self.coordinator.data.inventory
        return tuple(
            data.telemetry
            for module in inventory.modules
            if inventory.physical_inverter_id(module) == self.inverter_id
            and (data := self.coordinator.data.modules.get(module.raw_id)) is not None
            and data.telemetry is not None
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self._telemetry)

    @property
    def native_value(self):
        return self.entity_description.value_fn(self._telemetry)
