"""Constants for the NEP Local integration."""

from datetime import timedelta

DOMAIN = "nep_local"
CONF_HOST = "host"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MAX_CONCURRENT_REQUESTS = 4
TELEMETRY_FUTURE_TOLERANCE = timedelta(minutes=5)
TELEMETRY_MAX_AGE = timedelta(minutes=15)
MANUFACTURER = "Northern Electric Power"
MODEL = "BDG-256 Gateway"
