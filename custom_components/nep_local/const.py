"""Constants for the NEP Local integration."""

from datetime import timedelta

DOMAIN = "nep_local"
CONF_HOST = "host"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MANUFACTURER = "Northern Electric Power"
MODEL = "BDG-256 Gateway"
PLATFORMS = ["sensor"]
