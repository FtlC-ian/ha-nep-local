"""Tests for NEP Local sensor metadata and availability."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower

from custom_components.nep_local.sensor import GATEWAY_SENSORS, MODULE_SENSORS


def test_energy_and_power_metadata_are_home_assistant_native() -> None:
    gateway = {description.key: description for description in GATEWAY_SENSORS}
    modules = {description.key: description for description in MODULE_SENSORS}

    assert gateway["power"].device_class is SensorDeviceClass.POWER
    assert gateway["power"].native_unit_of_measurement == UnitOfPower.WATT
    assert gateway["power"].state_class is SensorStateClass.MEASUREMENT
    assert gateway["today_energy"].native_unit_of_measurement == UnitOfEnergy.WATT_HOUR
    assert gateway["today_energy"].state_class is SensorStateClass.TOTAL_INCREASING
    assert gateway["lifetime_energy"].state_class is SensorStateClass.TOTAL
    assert modules["status"].device_class is SensorDeviceClass.ENUM
    assert "low_light" in modules["status"].options
